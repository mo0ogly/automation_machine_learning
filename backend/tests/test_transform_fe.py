"""
Tests for the enriched transformation — shared feature_engineering module
(interactions + binning) and its leakage-free wiring through the preprocessor.
Dedicated module (test_api.py is at the file-size budget). No network.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app, SESSIONS  # noqa: E402
from pipeline import feature_engineering as fe  # noqa: E402
from stage_runner import run_stage  # noqa: E402

client = TestClient(app)


# ── shared module ───────────────────────────────────────────────────────────
def test_interactions_bounded_and_consistent():
    rng = np.random.RandomState(0)
    df = pd.DataFrame({"a": rng.normal(0, 5, 200), "b": rng.normal(0, 3, 200),
                       "c": rng.normal(0, 1, 200), "y": rng.randint(0, 2, 200)})
    base = fe.interaction_base(df, "y")
    _d, new = fe.apply_interactions(df.copy(), base, "both")
    assert 0 < len(new) <= fe.INTERACT_MAX_NEW
    # Same base -> identical column names on a different sample (train/test consistency).
    _dt, nt = fe.apply_interactions(df.sample(50, random_state=9).copy(), base, "both")
    assert nt == new


def test_binning_edges_fit_then_apply():
    rng = np.random.RandomState(1)
    df = pd.DataFrame({"a": rng.normal(0, 5, 300), "y": rng.randint(0, 2, 300)})
    edges = fe.fit_bin_edges(df, ["a"], 4, "quantile")
    _d, binned = fe.apply_bins(df.copy(), edges)
    assert binned == ["a_bin"]
    assert set(_d["a_bin"].unique()) <= {0, 1, 2, 3}


# ── leakage-free wiring ─────────────────────────────────────────────────────
def _prep(config_transform):
    sid = client.post("/api/session/start-demo/house_price_data.csv").json()["session_id"]
    s = SESSIONS.get(sid)
    run_stage(s, "clean", {})
    run_stage(s, "transform", config_transform)
    run_stage(s, "integrate", {})
    run_stage(s, "separate", {})
    return s.get_run("separate").artifacts


def test_interactions_and_binning_reach_the_model_matrix():
    art = _prep({"interactions": "both", "binning": "quantile", "n_bins": 4})
    feats = art["feature_names"]
    assert any("_x_" in f for f in feats)
    assert any("_div_" in f for f in feats)
    assert any(f.endswith("_bin") for f in feats)


def test_train_only_fit_keeps_train_test_columns_identical():
    art = _prep({"interactions": "products", "binning": "uniform", "n_bins": 5})
    pre = art["preprocessor"]
    assert pre.interaction_base_                      # base chosen on train
    assert pre.bin_edges_                             # edges fit on train
    assert list(art["X_train"].columns) == list(art["X_test"].columns)


def test_transform_schema_exposes_interactions_and_binning():
    sid = client.post("/api/session/start-demo/house_price_data.csv").json()["session_id"]
    s = SESSIONS.get(sid)
    run_stage(s, "clean", {})
    view = client.get(f"/api/session/{sid}/stage/transform").json()
    names = {c["name"] for c in view["schema"]}
    assert {"interactions", "binning", "n_bins"} <= names


def test_no_interactions_by_default():
    art = _prep({})
    assert not any("_x_" in f or "_div_" in f or f.endswith("_bin") for f in art["feature_names"])
