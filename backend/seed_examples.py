"""
seed_examples.py — replay the pipeline (autorun) on every demo dataset so a
fresh install ships with a ready-made, trained example session per dataset.

Idempotent: a dataset is skipped if a session named "[exemple] <dataset>"
with a trained model already exists — safe to re-run on every `mlauto up`.

Talks to the backend over its own HTTP API (same code path as the UI) rather
than calling pipeline internals directly, so it never drifts from what a real
user click does.
"""

import sys

import httpx

BASE_URL = "http://localhost:8000"
EXAMPLE_PREFIX = "[exemple] "

# Every demo dataset from GET /api/demo-datasets.
DATASETS = [
    "cyber_risk.csv",
    "phishing.csv",
    "spam.csv",
    "cve_severity.csv",
    "kev_exploit.csv",
    "prompt_injection.csv",
    "prompt_injection_technique.csv",
    "prompt_injection_mixed.csv",
    "house_price_data.csv",
    "breastcancer.csv",
    "Stars.csv",
    "client_data.csv",
    "transactions.csv",
]


def _already_seeded(sessions, dataset_name) -> bool:
    target = EXAMPLE_PREFIX + dataset_name
    return any(s["filename"] == target and s["summary"].get("model")
               for s in sessions)


def _seed_one(client: httpx.Client, dataset_name: str) -> bool:
    r = client.post(f"/api/session/start-demo/{dataset_name}")
    r.raise_for_status()
    session_id = r.json()["session_id"]

    r = client.post(f"/api/session/{session_id}/autorun")
    r.raise_for_status()
    result = r.json()

    if result.get("stopped_at"):
        print(f"  [ECHEC] {dataset_name} — bloqué à '{result['stopped_at']}' : {result['reason']}")
        client.delete(f"/api/session/{session_id}")
        return False

    client.patch(f"/api/session/{session_id}", json={"filename": EXAMPLE_PREFIX + dataset_name})
    metrics = result.get("metrics") or {}
    print(f"  [OK] {dataset_name} -> session {session_id}  {metrics}")
    return True


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        try:
            sessions = client.get("/api/sessions").json()["sessions"]
        except httpx.HTTPError as exc:
            print(f"Backend injoignable sur {BASE_URL} : {exc}")
            return 1

        failures = 0
        for name in DATASETS:
            if _already_seeded(sessions, name):
                print(f"  [deja fait] {name}")
                continue
            if not _seed_one(client, name):
                failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
