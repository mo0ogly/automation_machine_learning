"""
Tests for class-imbalance handling — pipeline/resampling.py + the model-stage
``imbalance`` option. Dedicated module (test_api.py is at the file-size budget).
No network.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app, SESSIONS  # noqa: E402
from pipeline import resampling as rs  # noqa: E402
from pipeline.stages import model as model_stage  # noqa: E402
from stage_runner import run_stage  # noqa: E402

client = TestClient(app)
DATA = Path(__file__).resolve().parent.parent.parent / "data"


def _imbalanced_xy():
    rng = np.random.RandomState(0)
    X = np.vstack([rng.normal(0, 1, (200, 4)), rng.normal(2, 1, (20, 4))])
    y = np.array([0] * 200 + [1] * 20)
    return pd.DataFrame(X, columns=list("abcd")), y


# ── pure module ─────────────────────────────────────────────────────────────
def test_resampling_balances_classes():
    X, y = _imbalanced_xy()
    for method in ("oversample", "smote"):
        Xr, yr = rs.resample(X, y, method)
        d = rs.class_distribution(yr)
        assert d["0"] == d["1"] == 200
        assert isinstance(Xr, pd.DataFrame) and list(Xr.columns) == list("abcd")
    Xu, yu = rs.resample(X, y, "undersample")
    du = rs.class_distribution(yu)
    assert du["0"] == du["1"] == 20


def test_smote_deterministic_and_regression_untouched():
    X, y = _imbalanced_xy()
    a = rs.smote(X, y)[0]
    b = rs.smote(X, y)[0]
    assert np.array_equal(np.asarray(a), np.asarray(b))
    yf = np.random.RandomState(1).normal(0, 1, len(y))   # continuous target
    Xr, _yr = rs.resample(X, yf, "smote")
    assert len(Xr) == len(X)                             # not resampled


def test_smote_creates_no_out_of_range_synthetic():
    """SMOTE interpolates -> synthetic minority rows stay within the convex hull
    range of the real minority rows (no extrapolation)."""
    X, y = _imbalanced_xy()
    Xr, yr = rs.smote(X, y)
    minority = X.to_numpy()[y == 1]
    synth = Xr.to_numpy()[np.asarray(yr) == 1]
    assert synth.min() >= minority.min() - 1e-9
    assert synth.max() <= minority.max() + 1e-9


# ── model-stage integration ─────────────────────────────────────────────────
def _train_kev(imbalance):
    sid = client.post("/api/session/start-demo/kev_exploit.csv").json()["session_id"]
    session = SESSIONS.get(sid)
    for stg in ("clean", "transform", "integrate", "separate"):
        run_stage(session, stg, {})
    run_stage(session, "model", {"algorithm": "RandomForest", "imbalance": imbalance})
    ev = run_stage(session, "evaluate", {})
    return session, ev


def test_model_schema_exposes_imbalance_for_classification():
    sid = client.post("/api/session/start-demo/kev_exploit.csv").json()["session_id"]
    view = client.get(f"/api/session/{sid}/stage/model").json()
    ctrl = next((c for c in view["schema"] if c["name"] == "imbalance"), None)
    assert ctrl is not None
    assert {"none", "class_weight", "oversample", "undersample", "smote"} <= {o["value"] for o in ctrl["options"]}


def test_smote_records_before_after_and_improves_rare_recall():
    """SMOTE rebalances the training set and lifts positive-class recall on the
    heavily imbalanced KEV target."""
    s_none, ev_none = _train_kev("none")
    s_smote, ev_smote = _train_kev("smote")
    resamp = s_smote.get_run("model").result["diagnostics"]["resampling"]
    assert resamp["method"] == "smote"
    assert resamp["after"]["1"] > resamp["before"]["1"]          # minority upsampled
    assert resamp["after"]["0"] == resamp["after"]["1"]          # balanced
    r_none = ev_none["diagnostics"]["operational"]["current"]["recall"]
    r_smote = ev_smote["diagnostics"]["operational"]["current"]["recall"]
    assert r_smote > r_none                                       # catches more rare positives


def test_imbalance_none_has_no_resampling():
    session, _ev = _train_kev("none")
    assert "resampling" not in session.get_run("model").result["diagnostics"]


def test_class_weight_flows_to_report():
    sid = client.post("/api/session/start-demo/kev_exploit.csv").json()["session_id"]
    session = SESSIONS.get(sid)
    for stg in ("clean", "transform", "integrate", "separate"):
        run_stage(session, stg, {})
    r = run_stage(session, "model", {"algorithm": "LogisticRegression", "imbalance": "class_weight"})
    assert r["report"].get("Déséquilibre") == "pondération (balanced)"
