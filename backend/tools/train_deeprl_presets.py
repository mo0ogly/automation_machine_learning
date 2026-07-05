"""
train_deeprl_presets.py — train every SOC/NOC Deep RL preset and save the
resulting agents into the "My agents" registry.

Populates the workbench with ready-made agents (one per cyber_defense / noc_ops
preset, full training budgets), so an analyst opens "Mes agents" and finds the
whole SOC/NOC fleet already trained, evaluable and exportable. Sequential on
purpose: parallel CPU trainings thrash each other and distort the metrics.

Run inside the backend container (idempotent — presets already saved under the
same name are skipped):

    docker compose -p mlauto exec -d -T backend python tools/train_deeprl_presets.py

Progress is appended to /data/deeprl_campaign.log (falls back to stdout).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rl.deep import presets, registry, train as trainer  # noqa: E402

# Registry display names, keyed by preset id (FR, matching the UI phrasing).
AGENT_NAMES = {
    "soc_triage_dqn": "SOC — Triage d'alertes (simple, DQN)",
    "soc_triage_ppo": "SOC — Triage d'alertes (robuste, PPO)",
    "soc_triage_maskable": "SOC — Triage d'alertes (budget garanti)",
    "incident_ppo": "SOC — Confinement d'incident",
    "threshold_sac": "SOC — Seuil IDS en continu",
    "soc_assign_maskable": "SOC — Affectation d'analystes",
    "soc_patch_maskable": "SOC — Priorisation de correctifs",
    "soc_invest_recurrent": "SOC — Investigation de cas",
    "noc_reroute_dqn": "NOC — Reroutage de trafic (simple, DQN)",
    "noc_reroute_maskable": "NOC — Reroutage (chemins garantis)",
    "noc_capacity_sac": "NOC — Capacité réseau en continu",
}

GROUPS = ("cyber_defense", "noc_ops")


def _logger() -> logging.Logger:
    log = logging.getLogger("deeprl_campaign")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    target = "/data/deeprl_campaign.log" if os.path.isdir("/data") else None
    handler = logging.FileHandler(target, encoding="utf-8") if target \
        else logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    log.addHandler(handler)
    return log


def main() -> int:
    log = _logger()
    todo = [p for p in presets.list_presets() if p["group"] in GROUPS]
    existing = {a["name"] for a in registry.list_agents()}
    log.info("Campagne presets SOC/NOC : %d presets, %d agents deja en registre",
             len(todo), len(existing))

    failures = 0
    for p in todo:
        name = AGENT_NAMES.get(p["id"], p["id"])
        if name in existing:
            log.info("SKIP %-22s (deja en registre : %s)", p["id"], name)
            continue
        log.info("TRAIN %-22s %s sur %s %s", p["id"], p["algo"], p["env_id"], p["config"])
        started = datetime.now()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                zip_path = str(Path(tmp) / "model.zip")
                result, _ = trainer.train(p["env_id"], p["algo"], dict(p["config"]),
                                          n_eval_episodes=20, save_path=zip_path)
                entry = registry.save_from_job(name, result, zip_path, dict(p["config"]))
            mins = (datetime.now() - started).total_seconds() / 60.0
            reward = (result.get("metrics") or {}).get("Récompense d'évaluation (moy.)")
            log.info("DONE  %-22s en %.1f min — recompense moy. %s, bat l'aleatoire : %s (agent %s)",
                     p["id"], mins, reward, result.get("beats_random"), entry["id"])
        except Exception as exc:  # log and keep going: one failure must not sink the fleet
            failures += 1
            log.error("FAIL  %-22s : %s", p["id"], exc)

    log.info("Campagne terminee : %d/%d entraines, %d echecs",
             len(todo) - failures, len(todo), failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
