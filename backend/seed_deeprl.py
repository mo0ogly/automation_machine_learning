"""
seed_deeprl.py — train and save one Deep RL agent per SOC/NOC preset so a
fresh install ships with ready-made agents in the "My agents" registry
(GET /api/rl/deep/registry), instead of that menu starting empty until an
analyst manually trains + saves one.

Idempotent: a preset is skipped if an agent named "[exemple] <preset_id>"
already exists in the registry — safe to re-run on every `mlauto up`.

Talks to the backend over its own HTTP API (train -> poll job -> save),
the same path the UI follows, rather than calling rl.deep internals directly.

Scope: cyber_defense (SOC) + noc_ops (NOC) presets only. classic_control
presets are reference/demo environments, not part of the SOC/NOC cockpit,
so they are left for manual training.

SAC and RecurrentPPO presets are excluded: measured at ~8 steps/s regardless
of env (vs. ~300-800 steps/s for DQN/PPO/MaskablePPO on the same hardware),
so their 40k-80k-timestep presets would take ~80-90 min each instead of
1-4 min — a per-step slowdown, not just "a slower algorithm", most likely
PyTorch/BLAS thread contention on tiny SAC/LSTM networks. Confirmed via a
solo timing run (isolated from any concurrent job) on 2026-07-07; not
investigated further here. Re-enable once that perf issue is root-caused.
"""

import fcntl
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
EXAMPLE_PREFIX = "[exemple] "
SEEDED_GROUPS = {"cyber_defense", "noc_ops"}
EXCLUDED_ALGOS = {"SAC", "RecurrentPPO"}  # see module docstring — perf issue, not scope
POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 600.0
LOCK_PATH = Path("/tmp/seed_deeprl.lock")


def _already_seeded(agents, preset_id) -> bool:
    target = EXAMPLE_PREFIX + preset_id
    return any(a["name"] == target for a in agents)


def _seed_one(client: httpx.Client, preset: dict) -> bool:
    preset_id = preset["id"]
    r = client.post("/api/rl/deep/train", json={
        "env_id": preset["env_id"], "algo": preset["algo"], "config": preset["config"],
    })
    r.raise_for_status()
    job_id = r.json()["job_id"]

    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        r = client.get(f"/api/rl/deep/job/{job_id}")
        r.raise_for_status()
        job = r.json()
        status = job.get("status")
        if status == "done":
            break
        if status in ("error", "cancelled"):
            print(f"  [ECHEC] {preset_id} — job {status} : {job.get('error')}")
            return False
        time.sleep(POLL_INTERVAL_S)
    else:
        print(f"  [ECHEC] {preset_id} — timeout après {POLL_TIMEOUT_S:.0f}s")
        return False

    r = client.post("/api/rl/deep/save", json={"job_id": job_id, "name": EXAMPLE_PREFIX + preset_id})
    r.raise_for_status()
    metrics = job.get("result", {}).get("metrics") or {}
    print(f"  [OK] {preset_id} ({preset['env_id']}/{preset['algo']})  {metrics}")
    return True


def main() -> int:
    # Guards against two concurrent seed runs (e.g. `up` launched twice) racing
    # each other into duplicate registry entries — each run's own train/save
    # calls are already sequential, but two runs started close together would
    # both see the same empty registry and both seed the same presets.
    lock_file = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"Un autre seed_deeprl.py tourne déjà (verrou {LOCK_PATH}) — abandon.")
        return 1

    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        try:
            catalog = client.get("/api/rl/deep/catalog").json()
            agents = client.get("/api/rl/deep/registry").json()["agents"]
        except httpx.HTTPError as exc:
            print(f"Backend injoignable sur {BASE_URL} : {exc}")
            return 1

        presets = [p for p in catalog["presets"]
                   if p["group"] in SEEDED_GROUPS and p["algo"] not in EXCLUDED_ALGOS]

        failures = 0
        for preset in presets:
            if _already_seeded(agents, preset["id"]):
                print(f"  [deja fait] {preset['id']}")
                continue
            if not _seed_one(client, preset):
                failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
