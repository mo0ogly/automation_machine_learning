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
from pipeline import monitoring  # noqa: E402

client = TestClient(app)


# --- attribute_cause: pure root-cause attribution from the drift signals -----

def _fdrift(n_features=6, n_major=0, n_moderate=0, verdict="stable", worst=None):
    return {"features": [], "n_features": n_features, "n_major": n_major,
            "n_moderate": n_moderate, "verdict": verdict, "worst": worst}

_STABLE_PRED = {"kind": "categorical", "level": "none"}
_STABLE_REPRO = {"available": True, "deterministic": True, "consistent": True}


def test_cause_pipeline_corruption_is_primary():
    """A reproducibility failure is an infrastructure cause and outranks any drift."""
    fd = _fdrift(n_major=2, n_moderate=2, verdict="major")  # also broad
    repro = {"available": True, "deterministic": False}
    out = monitoring.attribute_cause(fd, _STABLE_PRED, repro)
    assert out["primary"]["cause"] == "pipeline_corruption"
    assert out["primary"]["severity"] == "major"
    # The broad-drift cause is still reported, just not primary.
    assert "upstream_ingestion" in [c["cause"] for c in out["causes"]]


def test_cause_broad_drift_reads_as_upstream():
    fd = _fdrift(n_features=6, n_major=2, n_moderate=2, verdict="major")
    out = monitoring.attribute_cause(fd, _STABLE_PRED, _STABLE_REPRO)
    assert out["primary"]["cause"] == "upstream_ingestion"


def test_cause_localized_drift_reads_as_data_quality():
    fd = _fdrift(n_features=6, n_major=1, verdict="major", worst={"feature": "age", "psi": 0.5})
    out = monitoring.attribute_cause(fd, _STABLE_PRED, _STABLE_REPRO)
    assert out["primary"]["cause"] == "localized_data_quality"


def test_cause_prediction_drift_without_input_drift_is_concept_shift():
    fd = _fdrift(verdict="stable")
    pd = {"kind": "categorical", "level": "major"}
    out = monitoring.attribute_cause(fd, pd, _STABLE_REPRO)
    assert out["primary"]["cause"] == "concept_shift"


def test_cause_stable_has_no_primary():
    out = monitoring.attribute_cause(_fdrift(), _STABLE_PRED, _STABLE_REPRO)
    assert out["available"] is True
    assert out["primary"] is None
    assert out["causes"] == []


def test_cause_environment_change_outranks_data_drift():
    """A library/platform change is infrastructure: it ranks above data causes."""
    fd = _fdrift(n_major=1, verdict="major", worst={"feature": "age", "psi": 0.5})
    env = {"available": True, "changed": True,
           "diffs": [{"field": "sklearn", "from": "1.4.2", "to": "1.5.0"}]}
    out = monitoring.attribute_cause(fd, _STABLE_PRED, _STABLE_REPRO, env)
    assert out["primary"]["cause"] == "environment_change"
    assert any("sklearn" in e for e in out["primary"]["evidence"])
    # The localized data-quality cause is still reported, just below.
    assert "localized_data_quality" in [c["cause"] for c in out["causes"]]


def test_cause_env_change_folds_into_pipeline_corruption():
    """When reproducibility is broken, the env diff is the concrete culprit, not a
    separate cause."""
    env = {"available": True, "changed": True,
           "diffs": [{"field": "numpy", "from": "1.26", "to": "2.0"}]}
    repro = {"available": True, "deterministic": False}
    out = monitoring.attribute_cause(_fdrift(), _STABLE_PRED, repro, env)
    assert out["primary"]["cause"] == "pipeline_corruption"
    assert any("numpy" in e for e in out["primary"]["evidence"])
    assert "environment_change" not in [c["cause"] for c in out["causes"]]


# --- environment fingerprint --------------------------------------------------

def test_fingerprint_compare_detects_and_clears():
    from pipeline import environment
    fp = environment.capture_fingerprint()
    assert fp["python"] and isinstance(fp["libraries"], dict)
    assert environment.compare_fingerprints(fp, fp)["changed"] is False
    moved = {**fp, "libraries": {**fp["libraries"], "numpy": "0.0.0-test"}}
    cmp = environment.compare_fingerprints(fp, moved)
    assert cmp["changed"] is True
    assert any(d["field"] == "numpy" for d in cmp["diffs"])


# --- psi / ks / prediction_drift: the pure primitives under the report --------

def test_psi_identical_is_near_zero():
    x = list(range(100))
    assert monitoring.psi(x, x) < 1e-6


def test_psi_grows_with_shift():
    ref = list(range(100))
    assert monitoring.psi(ref, [v + 80 for v in ref]) > monitoring.psi(ref, [v + 5 for v in ref]) > 0.0


def test_psi_degenerate_samples_return_zero():
    assert monitoring.psi([], [1, 2, 3]) == 0.0
    assert monitoring.psi([1], [1, 2]) == 0.0          # < 2 reference points
    assert monitoring.psi([5, 5, 5, 5], [5, 5]) == 0.0  # single reference bin


def test_ks_identical_not_significant():
    x = list(range(50))
    stat, p = monitoring.ks(x, x)
    assert stat == 0.0 and p > monitoring.KS_ALPHA


def test_ks_disjoint_samples_are_significant():
    stat, p = monitoring.ks(list(range(50)), list(range(100, 150)))
    assert stat > 0.9 and p < monitoring.KS_ALPHA


def test_ks_degenerate_returns_no_signal():
    assert monitoring.ks([1], [1, 2, 3]) == (0.0, 1.0)


def test_prediction_drift_regression_reports_psi_and_means():
    from pipeline.context import REGRESSION
    ref = [float(v) for v in range(100)]
    out = monitoring.prediction_drift(ref, [v + 50 for v in ref], REGRESSION)
    assert out["kind"] == "regression"
    assert out["psi"] > 0.0
    assert out["cur_mean"] > out["ref_mean"]


# --- Benjamini-Hochberg multiple-comparison control on KS ---------------------

def test_bh_reject_nothing_when_all_null():
    assert monitoring._bh_reject([0.9, 0.8, 0.7, 0.6], 0.05) == [False] * 4


def test_bh_reject_only_the_significant():
    pv = [0.001, 0.002, 0.003] + [0.5] * 7
    rej = monitoring._bh_reject(pv, 0.05)
    assert rej[:3] == [True, True, True]
    assert not any(rej[3:])


def test_bh_ignores_none_and_nan():
    rej = monitoring._bh_reject([None, float("nan"), 0.0001], 0.05)
    assert rej[2] is True and rej[0] is False and rej[1] is False


def test_bh_is_stricter_than_raw_alpha():
    """A p just under alpha survives a raw threshold but not BH among many tests."""
    pv = [0.04] + [0.9] * 30
    assert pv[0] < 0.05                                  # would pass a raw per-feature test
    assert monitoring._bh_reject(pv, 0.05)[0] is False   # BH rejects it (FDR control)


def test_feature_drift_exposes_ks_availability_and_significance():
    import numpy as np, pandas as pd
    ref = pd.DataFrame({"a": np.arange(200.0), "b": np.zeros(200)})
    cur = pd.DataFrame({"a": np.arange(200.0) + 100, "b": np.zeros(200)})
    fd = monitoring.feature_drift(ref, cur, ["a", "b"])
    assert fd["ks_available"] is True
    assert all("ks_significant" in r for r in fd["features"])
    assert fd["n_features"] == 2


# --- attribute_cause: input/output interplay branches -------------------------

def test_cause_covariate_shift_when_inputs_and_outputs_both_drift():
    fd = _fdrift(n_features=6, n_major=1, verdict="major", worst={"feature": "x", "psi": 0.4})
    pd = {"kind": "categorical", "level": "moderate"}
    causes = [c["cause"] for c in monitoring.attribute_cause(fd, pd, _STABLE_REPRO)["causes"]]
    assert "covariate_shift" in causes


def test_cause_absorbed_input_drift_when_only_inputs_drift():
    fd = _fdrift(n_features=6, n_major=1, verdict="major", worst={"feature": "x", "psi": 0.4})
    causes = [c["cause"] for c in monitoring.attribute_cause(fd, _STABLE_PRED, _STABLE_REPRO)["causes"]]
    assert "absorbed_input_drift" in causes


# --- schema_diff + schema_mismatch cause --------------------------------------

def test_schema_diff_detects_missing_extra_and_ignores_target():
    d = monitoring.schema_diff(["a", "b", "c", "y"], ["a", "b", "z", "y"], target="y")
    assert d["changed"] is True
    assert d["missing"] == ["c"]
    assert d["extra"] == ["z"]


def test_schema_diff_clean_batch_is_unchanged():
    d = monitoring.schema_diff(["a", "b", "y"], ["b", "a", "y"], target="y")
    assert d == {"changed": False, "missing": [], "extra": []}


def test_cause_schema_mismatch_outranks_drift_topology():
    """A concrete raw-schema mismatch is an upstream cause above the drift heuristic."""
    fd = _fdrift(n_features=6, n_major=2, n_moderate=2, verdict="major")  # also broad
    schema = {"changed": True, "missing": ["heart_rate"], "extra": ["new_col"]}
    out = monitoring.attribute_cause(fd, _STABLE_PRED, _STABLE_REPRO, None, schema)
    assert out["primary"]["cause"] == "schema_mismatch"
    assert any("heart_rate" in e for e in out["primary"]["evidence"])
    assert "upstream_ingestion" in [c["cause"] for c in out["causes"]]  # still reported below


def test_cause_pipeline_corruption_still_outranks_schema_mismatch():
    """Infrastructure (repro break) outranks even a schema mismatch."""
    schema = {"changed": True, "missing": ["x"], "extra": []}
    repro = {"available": True, "deterministic": False}
    out = monitoring.attribute_cause(_fdrift(), _STABLE_PRED, repro, None, schema)
    assert out["primary"]["cause"] == "pipeline_corruption"
    assert "schema_mismatch" in [c["cause"] for c in out["causes"]]


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
    # Only continuous features are perturbed (one-hot columns are excluded).
    assert 1 <= j["n_continuous"] <= j["n_features"]
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
