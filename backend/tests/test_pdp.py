"""
Tests for partial dependence (PDP) in the Explicability stage — pipeline.explain_plots.
Dedicated module (test_api.py is at the file-size budget). No network.
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app, SESSIONS  # noqa: E402
from stage_runner import run_stage  # noqa: E402

client = TestClient(app)


def _explain(dataset, config=None):
    sid = client.post(f"/api/session/start-demo/{dataset}").json()["session_id"]
    s = SESSIONS.get(sid)
    for stg in ("clean", "transform", "integrate", "separate", "model"):
        run_stage(s, stg, {})
    return run_stage(s, "explain", config or {})


def _pdp_captions(result):
    caps = [(p.get("caption", "") if isinstance(p, dict) else "") for p in result["plots"]]
    return [c for c in caps if "épendance partielle" in c]


def test_pdp_binary_classification():
    r = _explain("breastcancer.csv")
    pdps = _pdp_captions(r)
    assert len(pdps) >= 3                                   # >=3 1-D + a 2-D
    assert any("2D" in c for c in pdps)


def test_pdp_multiclass():
    r = _explain("Stars.csv")
    assert len(_pdp_captions(r)) >= 3


def test_pdp_regression():
    r = _explain("house_price_data.csv")
    pdps = _pdp_captions(r)
    assert len(pdps) >= 3
    assert any("2D" in c for c in pdps)


def test_pdp_toggle_off():
    r = _explain("breastcancer.csv", {"partial_dependence": False})
    assert _pdp_captions(r) == []                           # only SHAP plots remain


def test_pdp_schema_control_present():
    sid = client.post("/api/session/start-demo/breastcancer.csv").json()["session_id"]
    s = SESSIONS.get(sid)
    for stg in ("clean", "transform", "integrate", "separate", "model"):
        run_stage(s, stg, {})
    view = client.get(f"/api/session/{sid}/stage/explain").json()
    names = {c["name"] for c in view["schema"]}
    assert "partial_dependence" in names and "ice" in names


def _ice_captions(result):
    caps = [(p.get("caption", "") if isinstance(p, dict) else "") for p in result["plots"]]
    return [c for c in caps if "ICE" in c]


def test_ice_off_by_default_on_when_enabled():
    assert _ice_captions(_explain("breastcancer.csv")) == []            # off by default
    assert len(_ice_captions(_explain("breastcancer.csv", {"ice": True}))) == 1
