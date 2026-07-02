"""
Tests for the jitter (prediction-stability) protocol — pipeline/monitoring.py.

The drift-report endpoint tests live in test_api.py (which is at the file-size
budget); the jitter protocol added later gets its own module.
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

client = TestClient(app)


def _trained_session(name="breastcancer.csv"):
    r = client.post(f"/api/session/start-demo/{name}")
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    return sid


def test_jitter_protocol_endpoint():
    """The jitter protocol returns a deterministic flip-rate curve + verdict."""
    sid = _trained_session()
    r = client.post(f"/api/session/{sid}/jitter")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["available"] is True
    assert j["verdict"] in ("stable", "sensible", "instable")
    assert len(j["curve"]) == 5
    # Flip rate is a proper rate and does not decrease as noise grows 100x.
    rates = [c["flip_rate"] for c in j["curve"]]
    assert all(0.0 <= x <= 1.0 for x in rates)
    assert rates[-1] >= rates[0]
    assert len(j["plots"]) == 1
    # Fixed seed -> a second run reproduces the exact same curve.
    r2 = client.post(f"/api/session/{sid}/jitter")
    assert [c["flip_rate"] for c in r2.json()["curve"]] == rates


def test_jitter_requires_trained_model():
    r = client.post("/api/session/start-demo/breastcancer.csv")
    sid = r.json()["session_id"]
    r = client.post(f"/api/session/{sid}/jitter")
    assert r.status_code == 409
