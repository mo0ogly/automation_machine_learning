"""
Tests for the scheduled-batch operations endpoint (/batch-monitor): score a
batch + assess drift + return an actionable verdict, in one call. No network.
"""

import io
import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402

client = TestClient(app)
DATA = Path(__file__).resolve().parent.parent.parent / "data"


def _trained(name="kev_exploit.csv"):
    sid = client.post(f"/api/session/start-demo/{name}").json()["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    return sid


def _post_batch(sid, df):
    buf = io.BytesIO(); df.to_csv(buf, index=False); buf.seek(0)
    return client.post(f"/api/session/{sid}/batch-monitor", files={"file": ("b.csv", buf, "text/csv")})


def test_batch_monitor_scores_and_verdicts_ok_on_stable_batch():
    sid = _trained()
    df = pd.read_csv(DATA / "kev_exploit.csv").sample(200, random_state=1)
    j = _post_batch(sid, df).json()
    assert j["n_scored"] == 200
    assert j["action"] == "ok"
    assert j["drift"]["overall"] == "stable"
    assert "prediction" in j["csv"].splitlines()[0]        # scored CSV returned


def test_batch_monitor_flags_action_required_on_shifted_batch():
    sid = _trained()
    df = pd.read_csv(DATA / "kev_exploit.csv").sample(200, random_state=2).copy()
    num = df.select_dtypes("number").columns
    df[num] = df[num] * 3.0 + 50.0
    j = _post_batch(sid, df).json()
    assert j["action"] == "action_required"
    assert j["drift"]["overall"] == "major"


def test_batch_monitor_requires_trained_model():
    sid = client.post("/api/session/start-demo/breastcancer.csv").json()["session_id"]
    buf = io.BytesIO(b"a,b\n1,2\n3,4\n")
    r = client.post(f"/api/session/{sid}/batch-monitor", files={"file": ("x.csv", buf, "text/csv")})
    assert r.status_code == 409
