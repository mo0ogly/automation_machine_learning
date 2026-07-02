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


def _stability(sid, analysis):
    r = client.post(f"/api/session/{sid}/stability/{analysis}")
    assert r.status_code == 200, r.text
    return r.json()


def test_stability_analyses_classification():
    """All five advanced analyses run on a trained binary classifier."""
    sid = _trained_session()

    num = _stability(sid, "numerical")
    assert num["available"] is True
    assert 0.0 <= num["precision_flip_rate"] <= 1.0
    assert num["verdict"] in ("stable", "sensible", "instable")

    mar = _stability(sid, "margin")
    assert mar["available"] is True
    fr = mar["fractions"]
    assert 0.0 <= fr["0.01"] <= fr["0.05"] <= fr["0.1"] <= 1.0  # nested bands

    chu = _stability(sid, "churn")
    assert chu["available"] is True
    assert 0.0 <= chu["mean_churn"] <= 1.0
    assert len(chu["rates"]) == 5

    con = _stability(sid, "conformal")
    assert con["available"] is True
    assert 0.7 <= con["coverage"] <= 1.0          # target 90%, finite-sample slack
    assert 0.0 <= con["ambiguous"] <= 1.0

    smo = _stability(sid, "smoothing")
    assert smo["available"] is True
    assert 0.0 <= smo["certified_fraction"] <= 1.0
    # Every analysis ships exactly one figure and a display contract.
    for rep in (num, mar, chu, con, smo):
        assert len(rep["plots"]) == 1
        assert rep["summary"] and all("label" in r and "value" in r for r in rep["summary"])


def test_stability_analyses_anomaly():
    """Margin, conformal p-values and numerical jitter on an anomaly detector."""
    sid = _trained_session("transactions.csv")
    mar = _stability(sid, "margin")
    assert mar["available"] is True
    con = _stability(sid, "conformal")
    assert con["available"] is True
    assert 0.0 <= con["alert_rate"] <= 0.2        # guarantee: ~alpha under exchangeability
    num = _stability(sid, "numerical")
    assert num["available"] is True


def test_stability_deterministic_and_unknown_analysis():
    sid = _trained_session()
    a = _stability(sid, "smoothing")
    b = _stability(sid, "smoothing")
    assert a["certified_fraction"] == b["certified_fraction"]  # fixed seed
    r = client.post(f"/api/session/{sid}/stability/quantum")
    assert r.status_code == 404
