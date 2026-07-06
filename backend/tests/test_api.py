"""
End-to-end tests for the staged ML Automator API.

These never hit the network: the per-stage agent is exercised through its
deterministic heuristic fallback (GROQ_API_KEY removed for that test).
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402
import llm_agent  # noqa: E402

client = TestClient(app)


def test_health_check():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_agent_status_shape():
    r = client.get("/api/agent-status")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "groq"
    assert "configured" in body and "model" in body


def _start_demo(name):
    r = client.post(f"/api/session/start-demo/{name}")
    assert r.status_code == 200, r.text
    return r.json()


def test_session_start_and_detection():
    body = _start_demo("breastcancer.csv")
    assert body["context"]["problem_type"] == "classification"
    assert len(body["stages"]) == 8  # clean..separate + model/tune/evaluate/explain
    assert body["status"][0]["stage_id"] == "clean"
    assert body["stages"][-1]["stage_id"] == "explain"


def test_stage_view_has_schema_and_diagnostics():
    sid = _start_demo("breastcancer.csv")["session_id"]
    r = client.get(f"/api/session/{sid}/stage/clean")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["title"] == "Nettoyage"
    assert isinstance(body["schema"], list) and body["schema"]
    assert "overview" in body["diagnostics"]
    assert body["diagnose_plots"]  # at least one base64 plot


def test_run_clean_returns_counts():
    sid = _start_demo("breastcancer.csv")["session_id"]
    r = client.post(f"/api/session/{sid}/stage/clean/run", json={"config": {}})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert "counts" in result and result["counts"]["rows_out"] > 0


def test_downstream_invalidation_on_replay():
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/stage/clean/run", json={"config": {}})
    client.post(f"/api/session/{sid}/stage/transform/run", json={"config": {}})
    # Re-run clean -> transform must become stale.
    r = client.post(f"/api/session/{sid}/stage/clean/run", json={"config": {}})
    status = {s["stage_id"]: s for s in r.json()["status"]}
    assert status["transform"]["stale"] is True


def test_autorun_classification():
    sid = _start_demo("breastcancer.csv")["session_id"]
    r = client.post(f"/api/session/{sid}/autorun")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ran"][-1] == "evaluate", body
    assert "Accuracy" in body["metrics"]
    # classification metrics: precision/recall + per-class report
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    rep = ev["result"]["report"]
    assert "Précision (pondéré)" in rep and "Rappel (pondéré)" in rep
    per_class = ev["result"]["diagnostics"]["rapport_par_classe"]
    assert per_class and all(
        {"classe", "précision", "rappel", "f1", "support"} <= set(row) for row in per_class)


def test_autorun_multiclass_stars():
    """Multiclass classification end-to-end (Stars.csv — 6 classes)."""
    body = _start_demo("Stars.csv")
    assert body["context"]["problem_type"] == "classification"
    sid = body["session_id"]
    run = client.post(f"/api/session/{sid}/autorun").json()
    assert run["ran"][-1] == "evaluate", run
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    per_class = ev["result"]["diagnostics"]["rapport_par_classe"]
    classes = [r["classe"] for r in per_class if "avg" not in str(r["classe"])]
    assert len(classes) == 6


def test_autorun_regression():
    sid = _start_demo("house_price_data.csv")["session_id"]
    body = client.post(f"/api/session/{sid}/autorun").json()
    assert body["ran"][-1] == "evaluate", body
    assert "R²" in body["metrics"]


def test_autorun_clustering_business_labels():
    body = _start_demo("client_data.csv")
    assert body["context"]["problem_type"] == "clustering"
    assert body["context"]["supervised"] is False
    sid = body["session_id"]
    run = client.post(f"/api/session/{sid}/autorun").json()
    assert run["ran"][-1] == "evaluate", run
    assert "Silhouette" in run["metrics"]
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    summary = ev["result"]["diagnostics"]["cluster_summary"]
    assert len(summary) >= 2
    # cluster reading: real average values + majority categoricals + label
    assert all("label_metier" in r and "moyennes" in r and "majoritaires" in r for r in summary)
    assert all(r["moyennes"] for r in summary)                       # raw means present
    labels = {r["label_metier"] for r in summary}
    assert labels <= {"Premium fidèle", "Digital promo", "Famille pragmatique"}, labels
    assert any(r["majoritaires"].get("canal_prefere") for r in summary)


def test_clustering_elbow_in_model_view():
    """Modelling exposes the elbow-method curve + recommended K for clustering."""
    sid = _start_demo("client_data.csv")["session_id"]
    for stg in ("clean", "transform", "integrate", "separate"):
        client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
    view = client.get(f"/api/session/{sid}/stage/model").json()
    assert view["diagnostics"]["k_recommande"] >= 2
    assert view["diagnose_plots"] and "coude" in view["diagnose_plots"][0]["caption"].lower()


def _run_clustering_chain(sid, model_cfg):
    for stg in ("clean", "transform", "integrate", "separate"):
        r = client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
        assert r.status_code == 200, r.text
    r = client.post(f"/api/session/{sid}/stage/model/run", json={"config": model_cfg})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/session/{sid}/stage/evaluate/run", json={"config": {}})
    assert r.status_code == 200, r.text
    return client.get(f"/api/session/{sid}/stage/evaluate").json()


def test_clustering_agglomerative():
    """Non supervisé élargi : clustering agglomératif (hiérarchique) en K=3."""
    sid = _start_demo("client_data.csv")["session_id"]
    ev = _run_clustering_chain(sid, {"cluster_algo": "agglomerative", "n_clusters": 3})
    diag = ev["result"]["diagnostics"]
    assert "Agglom" in diag["algorithm"]
    assert diag["metrics"]["Clusters"] == 3
    assert len(diag["cluster_summary"]) == 3


def test_clustering_agglomerative_has_dendrogram():
    """The agglomerative run ships its native reading: the Ward dendrogram."""
    sid = _start_demo("client_data.csv")["session_id"]
    for stg in ("clean", "transform", "integrate", "separate"):
        client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
    m = client.post(f"/api/session/{sid}/stage/model/run",
                    json={"config": {"cluster_algo": "agglomerative", "n_clusters": 3}})
    assert m.status_code == 200, m.text
    assert len(m.json()["result"]["plots"]) >= 2   # elbow + dendrogram


def test_evaluate_reports_leakage_free_flag():
    """Evaluation flags that its scores come from the train-only preprocessor."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    assert ev["result"]["diagnostics"]["leakage_free"] is True


def test_clustering_dbscan_handles_noise():
    """DBSCAN (densité) : tourne, expose silhouette robuste et gère le bruit (label -1)."""
    sid = _start_demo("client_data.csv")["session_id"]
    ev = _run_clustering_chain(sid, {"cluster_algo": "dbscan", "eps": 0.8, "min_samples": 5})
    diag = ev["result"]["diagnostics"]
    assert diag["algorithm"] == "DBSCAN"
    assert "Silhouette" in diag["metrics"]
    assert isinstance(diag["cluster_summary"], list)


def test_clustering_kdistance_plot_in_model_view():
    """The model view offers a k-distance plot to calibrate DBSCAN's eps."""
    sid = _start_demo("client_data.csv")["session_id"]
    for stg in ("clean", "transform", "integrate", "separate"):
        client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
    view = client.get(f"/api/session/{sid}/stage/model").json()
    caps = " ".join(p["caption"].lower() for p in view["diagnose_plots"])
    assert "k-distance" in caps
    assert "dbscan" in view["diagnostics"]["algos"]


def test_evaluate_clustering_recovers_missing_labels():
    """Guard: DBSCAN/Agglomerative have no .predict(); if the stored labels are ever
    missing, evaluate falls back to the fitted model.labels_ instead of crashing."""
    from pipeline import SESSIONS
    sid = _start_demo("client_data.csv")["session_id"]
    for stg in ("clean", "transform", "integrate", "separate"):
        client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
    client.post(f"/api/session/{sid}/stage/model/run",
                json={"config": {"cluster_algo": "agglomerative", "n_clusters": 3}})
    SESSIONS.get(sid).get_run("model").artifacts["labels"] = None  # simulate the rare path
    r = client.post(f"/api/session/{sid}/stage/evaluate/run", json={"config": {}})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["diagnostics"]["metrics"]["Clusters"] == 3


def test_clustering_internal_indices():
    """Complementary internal validity indices: Davies-Bouldin + Calinski-Harabasz."""
    sid = _start_demo("client_data.csv")["session_id"]
    ev = _run_clustering_chain(sid, {"cluster_algo": "kmeans", "n_clusters": 3})
    m = ev["result"]["diagnostics"]["metrics"]
    assert "Davies-Bouldin" in m and "Calinski-Harabasz" in m
    assert m["Davies-Bouldin"] > 0 and m["Calinski-Harabasz"] > 0


def test_cluster_labels_override():
    """Cluster decision table: an expert name overrides the auto business label."""
    sid = _start_demo("client_data.csv")["session_id"]
    _run_clustering_chain(sid, {"cluster_algo": "kmeans", "n_clusters": 3})
    r = client.post(f"/api/session/{sid}/stage/evaluate/run",
                    json={"config": {"cluster_labels": {"0": "Mon segment VIP"}}})
    assert r.status_code == 200, r.text
    summary = r.json()["result"]["diagnostics"]["cluster_summary"]
    row0 = next(s for s in summary if s["cluster"] == 0)
    assert row0["label_metier"] == "Mon segment VIP"


def test_anomaly_demo_detected():
    """The transactions demo is treated as unsupervised anomaly detection (no target)."""
    body = _start_demo("transactions.csv")
    assert body["context"]["problem_type"] == "anomaly"
    assert body["context"]["supervised"] is False


def test_autorun_anomaly_detection():
    """End-to-end anomaly detection (Isolation Forest) — rate + top abnormal rows."""
    sid = _start_demo("transactions.csv")["session_id"]
    run = client.post(f"/api/session/{sid}/autorun").json()
    assert run["ran"][-1] == "evaluate", run
    assert run["metrics"]["Anomalies"] > 0
    diag = client.get(f"/api/session/{sid}/stage/evaluate").json()["result"]["diagnostics"]
    assert 0 < diag["anomaly_rate"] < 50
    assert diag["top_anomalies"] and "score" in diag["top_anomalies"][0]


def test_anomaly_lof_algorithm():
    """The expert can switch the detector to Local Outlier Factor."""
    sid = _start_demo("transactions.csv")["session_id"]
    for stg in ("clean", "transform", "integrate", "separate"):
        client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
    r = client.post(f"/api/session/{sid}/stage/model/run", json={"config": {"anomaly_algo": "lof"}})
    assert r.status_code == 200, r.text
    assert "Outlier" in r.json()["result"]["report"]["Détecteur"]
    ev = client.post(f"/api/session/{sid}/stage/evaluate/run", json={"config": {}})
    assert ev.status_code == 200, ev.text
    assert ev.json()["result"]["metrics"]["Anomalies"] >= 0


def test_tune_rejected_for_anomaly():
    sid = _start_demo("transactions.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    r = client.post(f"/api/session/{sid}/stage/tune/run", json={"config": {}})
    assert r.status_code == 409, r.text


def test_stage_view_has_explanation():
    sid = _start_demo("breastcancer.csv")["session_id"]
    sep = client.get(f"/api/session/{sid}/stage/separate").json()
    assert sep["supervised"] is True
    assert sep["explanation"]["track"] == "supervised"
    assert "supervision" in sep["explanation"] and sep["explanation"]["supervision"]


def test_predict_after_autorun():
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    r = client.post(f"/api/session/{sid}/predict", json={})
    assert r.status_code == 200, r.text
    assert "prediction" in r.json()


def test_recommend_heuristic_fallback(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    sid = _start_demo("breastcancer.csv")["session_id"]
    r = client.post(f"/api/session/{sid}/stage/clean/recommend", json={"config": {}})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["source"] == "heuristic-fallback"
    assert isinstance(rec["suggested_config"], dict)
    assert isinstance(rec["rationale"], list)


def test_ordinal_encoding_preserves_order():
    import pandas as pd
    from pipeline import typology as typ
    df = pd.DataFrame({"qualite": ["Po", "Fa", "TA", "Gd", "Ex"], "x": [1, 2, 3, 4, 5]})
    t = typ.classify(df, target_col=None)
    assert "qualite" in t["ordinale"]               # detected as ordinal
    enc = typ.encode_ordinal(df["qualite"], t["ordinale"]["qualite"])
    assert list(enc) == [1.0, 2.0, 3.0, 4.0, 5.0]   # Po<Fa<TA<Gd<Ex order preserved


def test_tune_and_explain_supervised():
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    t = client.post(f"/api/session/{sid}/stage/tune/run", json={"config": {"cv": 2}})
    assert t.status_code == 200, t.text
    assert "best_params" in t.json()["result"]["diagnostics"]
    e = client.post(f"/api/session/{sid}/stage/explain/run", json={"config": {}})
    assert e.status_code == 200, e.text
    assert e.json()["result"]["plots"]  # at least the SHAP summary plot


def test_tune_rejected_for_clustering():
    sid = _start_demo("client_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    t = client.post(f"/api/session/{sid}/stage/tune/run", json={"config": {}})
    assert t.status_code == 409  # fine-tuning is supervised-only


def test_integrate_feature_decision_table():
    """Integration exposes a per-feature keep/drop table; the expert's choice is honoured."""
    sid = _start_demo("house_price_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/stage/clean/run", json={"config": {}})
    client.post(f"/api/session/{sid}/stage/transform/run", json={"config": {}})
    view = client.get(f"/api/session/{sid}/stage/integrate").json()
    tables = [c for c in view["schema"] if c["type"] == "column_table"]
    assert tables, view["schema"]
    table = tables[0]
    assert table["name"] == "dropped_features"
    assert table["columns"]
    assert all({"column", "recommended", "reason"} <= set(r) for r in table["columns"])
    # The expert removes the first listed feature.
    victim = table["columns"][0]["column"]
    run = client.post(f"/api/session/{sid}/stage/integrate/run",
                      json={"config": {"dropped_features": [victim]}}).json()
    assert victim in run["result"]["diagnostics"]["dropped_features"]
    assert run["result"]["report"]["Retirées par l'expert"] == 1


def test_model_leaderboard_in_view():
    """Modelling exposes a ranked comparison of candidate models."""
    sid = _start_demo("house_price_data.csv")["session_id"]
    for stg in ("clean", "transform", "integrate", "separate"):
        r = client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
        assert r.status_code == 200, (stg, r.text)
    view = client.get(f"/api/session/{sid}/stage/model").json()
    lb = view["diagnostics"]["leaderboard"]
    assert len(lb) >= 3
    # Ranked by CROSS-VALIDATION on the train set — the test set stays virgin here.
    assert all("rmse_cv" in r and "rmse_cv_std" in r and "r2_cv" in r for r in lb)
    assert sum(1 for r in lb if r["recommended"]) == 1     # exactly one recommended
    rmses = [r["rmse_cv"] for r in lb]
    assert rmses == sorted(rmses)                           # ranked by CV RMSE ascending
    assert view["diagnostics"]["recommended_model"] == lb[0]["model"]
    assert view["diagnostics"]["cv_folds"] >= 2
    assert view["diagnostics"]["leakage_free"] is True      # train-only preprocessor active


def test_clean_categorical_values_and_extreme_rows():
    """Cleaning surfaces distinct categorical values + extreme rows."""
    sid = _start_demo("house_price_data.csv")["session_id"]
    view = client.get(f"/api/session/{sid}/stage/clean").json()
    cv = view["diagnostics"]["valeurs_categorielles"]
    assert cv and all({"colonne", "n_distinct", "valeurs"} <= set(r) for r in cv)
    ex = view["diagnostics"]["lignes_extremes"]
    assert ex and "SalePrice" in ex[0]                     # target projected into extreme rows
    sale = [r["SalePrice"] for r in ex]
    assert sale == sorted(sale, reverse=True)              # ranked by target descending


def test_transform_eda_plots_by_type():
    """Transformation surfaces univariate-by-type + bivariate plots."""
    sid = _start_demo("house_price_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/stage/clean/run", json={"config": {}})
    view = client.get(f"/api/session/{sid}/stage/transform").json()
    ad = view["diagnostics"]["analyse_descriptive"]
    assert ad["continues"] > 0 and ad["nominales"] > 0
    assert len(view["diagnose_plots"]) >= 4               # skew + univariate buckets + bivariate
    # plots are captioned objects {img, caption, topic}
    assert all(p["img"].startswith("data:image") and "caption" in p for p in view["diagnose_plots"])


def test_evaluate_overfitting_control():
    """Evaluation reports the train/test gap + 5-fold CV."""
    sid = _start_demo("house_price_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    ctrl = ev["result"]["diagnostics"]["controle_surapprentissage"]
    assert "R² (train)" in ctrl and "R² (test)" in ctrl
    assert "ecart_overfit" in ctrl and "CV R² (5 folds)" in ctrl
    assert "verdict" in ctrl


def test_evaluate_binary_has_roc_pr_auc():
    """Binary classification: probability metrics + ROC / PR curves on the test set."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    metrics = ev["result"]["metrics"]
    assert "ROC-AUC" in metrics and 0.5 <= metrics["ROC-AUC"] <= 1.0
    assert "PR-AUC (AP)" in metrics
    assert len(ev["result"]["plots"]) >= 4          # confusion + ROC + PR + overfit control


def test_evaluate_regression_has_mae():
    sid = _start_demo("house_price_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    metrics = ev["result"]["metrics"]
    assert "MAE" in metrics and metrics["MAE"] > 0
    assert "RMSE" in metrics


def test_tune_defaults_to_baseline_algorithm():
    """Fine-tuning with no explicit algorithm tunes the Modelling baseline family."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    t = client.post(f"/api/session/{sid}/stage/tune/run", json={"config": {"cv": 2}}).json()
    diag = t["result"]["diagnostics"]
    assert diag["algorithm"] == "RandomForest"      # the autorun baseline
    assert diag["baseline_score"] is not None       # compared on CV, not on the test set
    assert "best_params" in diag


def test_tune_supports_logistic_family():
    """Any leaderboard family is tunable — here LogisticRegression with its C grid."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    client.post(f"/api/session/{sid}/stage/model/run",
                json={"config": {"algorithm": "LogisticRegression"}})
    t = client.post(f"/api/session/{sid}/stage/tune/run", json={"config": {"cv": 2}})
    assert t.status_code == 200, t.text
    assert "C" in t.json()["result"]["diagnostics"]["best_params"]


def test_explain_supports_linear_models():
    """SHAP LinearExplainer covers the linear families (was tree-only before)."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    client.post(f"/api/session/{sid}/stage/model/run",
                json={"config": {"algorithm": "LogisticRegression"}})
    e = client.post(f"/api/session/{sid}/stage/explain/run", json={"config": {}})
    assert e.status_code == 200, e.text
    diag = e.json()["result"]["diagnostics"]
    assert diag["explainer"] == "LinearExplainer"
    assert diag["shap_top_features"]


def test_separate_stores_train_only_preprocessor():
    """The Separation artefacts carry the train-fitted preprocessor and predictions
    replay it (leakage-free serving path)."""
    from app import SESSIONS
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    session = SESSIONS.get(sid)
    pre = session.get_run("separate").artifacts.get("preprocessor")
    assert pre is not None and pre.fitted_
    assert list(pre.feature_names_) == list(session.get_run("separate").artifacts["feature_names"])
    r = client.post(f"/api/session/{sid}/predict", json={})
    assert r.status_code == 200 and "prediction" in r.json()


def test_operational_analysis_binary():
    """Binary classification exposes the full operational (SOC) analysis."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    ev = client.get(f"/api/session/{sid}/stage/evaluate").json()
    op = ev["result"]["diagnostics"]["operational"]
    assert op["applicable"] is True and op["mode"] == "binary"
    assert op["threshold_sweep"] and "recommended_thresholds" in op
    assert set(op["recommended_thresholds"]) >= {"min_cost", "max_fbeta", "youden", "fpr_1pct"}
    assert "calibration" in op and "ece" in op["calibration"]
    assert set(op["robust_metrics"]) == {"mcc", "balanced_accuracy", "cohen_kappa"}
    assert op["alert_budget"] and "precision_at_k" in op["alert_budget"][0]
    assert op["soc_playbook"]["sections"]


def test_operating_point_endpoint_recomputes():
    """The endpoint recomputes the operating point at a chosen threshold/cost."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    r = client.post(f"/api/session/{sid}/operating-point",
                    json={"threshold": 0.2, "cost_fn": 20, "cost_fp": 1})
    assert r.status_code == 200, r.text
    op = r.json()
    assert op["current"]["threshold"] == 0.2
    assert op["cost"]["cost_fn"] == 20


def test_operational_regression_tolerance_bands():
    sid = _start_demo("house_price_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    op = client.post(f"/api/session/{sid}/operating-point", json={}).json()
    assert op["mode"] == "regression" and op["tolerance_bands"]
    assert "within" in op["tolerance_bands"][0]


def test_operational_anomaly_alert_budget():
    sid = _start_demo("transactions.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    op = client.post(f"/api/session/{sid}/operating-point", json={}).json()
    assert op["mode"] == "anomaly" and op["budget_curve"]
    assert "alerts_per_1000" in op["budget_curve"][0]


def test_cyber_kev_dataset_imbalanced_detection():
    """The KEV demo loads as imbalanced binary and its operating point beats the
    naive 0.5 threshold (the whole point of the operational view)."""
    body = _start_demo("kev_exploit.csv")
    assert body["context"]["problem_type"] == "classification"
    assert body["context"]["target_col"] == "exploited"
    sid = body["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    op = client.post(f"/api/session/{sid}/operating-point", json={}).json()
    assert op["mode"] == "binary"
    # min-cost threshold is well below 0.5 on this imbalanced target.
    assert op["recommended_thresholds"]["min_cost"] < 0.5


def test_cyber_cve_multiclass_focus_rarest():
    """CVE severity loads as multiclass; the default OVR focus is the rarest class."""
    body = _start_demo("cve_severity.csv")
    assert body["context"]["target_col"] == "severity"
    sid = body["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    op = client.post(f"/api/session/{sid}/operating-point", json={}).json()
    assert op["mode"] == "multiclass_ovr"
    assert op["focus_class"] == "critical"


def test_cyber_phishing_and_spam_load():
    for name, target in (("phishing.csv", "is_phishing"), ("spam.csv", "is_spam")):
        body = _start_demo(name)
        assert body["context"]["target_col"] == target, name
        card = client.get(f"/api/dataset-card/{name}")
        assert card.status_code == 200 and card.json()["synthetic"] is True


def test_new_algorithms_in_leaderboard():
    """SVM, KNN, Naive Bayes are offered and cross-validated on the classification leaderboard."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    for stg in ("clean", "transform", "integrate", "separate"):
        client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
    view = client.get(f"/api/session/{sid}/stage/model").json()
    models = {r["model"] for r in view["diagnostics"]["leaderboard"]}
    assert {"SVM", "KNN", "NaiveBayes", "LogisticRegression"} <= models
    assert all(r.get("help") for r in view["diagnostics"]["leaderboard"])   # AI-friendly descriptions
    # SVM config schema exposes the algorithm choice with the new options.
    algos = next(c for c in view["schema"] if c["name"] == "algorithm")
    assert {"SVM", "KNN", "NaiveBayes"} <= {o["value"] for o in algos["options"]}


def test_svm_trains_with_probabilities():
    """A chosen SVM keeps predict_proba → ROC/PR + operational view stay available."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    client.post(f"/api/session/{sid}/stage/model/run", json={"config": {"algorithm": "SVM"}})
    ev = client.post(f"/api/session/{sid}/stage/evaluate/run", json={"config": {}}).json()
    metrics = ev["result"]["metrics"]
    assert "ROC-AUC" in metrics
    assert ev["result"]["diagnostics"]["operational"]["applicable"] is True


def test_elasticnet_regression_tunable():
    """ElasticNet is offered for regression and tunable with its own grid."""
    sid = _start_demo("house_price_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    client.post(f"/api/session/{sid}/stage/model/run", json={"config": {"algorithm": "ElasticNet"}})
    t = client.post(f"/api/session/{sid}/stage/tune/run", json={"config": {"cv": 2}})
    assert t.status_code == 200, t.text
    bp = t.json()["result"]["diagnostics"]["best_params"]
    assert "alpha" in bp or "l1_ratio" in bp


def test_univariate_feature_selection_reduces_features():
    """Univariate selection keeps k features, fit on the train split (leakage-free)."""
    from app import SESSIONS
    sid = _start_demo("breastcancer.csv")["session_id"]
    for stg in ("clean", "transform"):
        client.post(f"/api/session/{sid}/stage/{stg}/run", json={"config": {}})
    client.post(f"/api/session/{sid}/stage/integrate/run",
                json={"config": {"feature_selection": "univariate", "fs_score": "anova", "fs_k": 6}})
    client.post(f"/api/session/{sid}/stage/separate/run", json={"config": {}})
    art = SESSIONS.get(sid).get_run("separate").artifacts
    assert len(art["feature_names"]) == 6
    assert art["preprocessor"].selected_features_ is not None
    # Integrate exposes the selection controls only for supervised problems.
    view = client.get(f"/api/session/{sid}/stage/integrate").json()
    assert any(c["name"] == "feature_selection" for c in view["schema"])


def test_feature_selection_absent_for_clustering():
    sid = _start_demo("client_data.csv")["session_id"]
    view = client.get(f"/api/session/{sid}/stage/integrate").json()
    assert not any(c["name"] == "feature_selection" for c in view["schema"])


def _upload(name, content: bytes):
    import io
    return client.post("/api/session/start",
                       files={"file": (name, io.BytesIO(content), "text/csv")})


def test_ingestion_rejects_too_few_rows():
    r = _upload("tiny.csv", b"a,b\n1,2\n3,4\n")   # 2 data rows < MIN_ROWS
    assert r.status_code == 400
    assert "lignes" in r.json()["detail"].lower()


def test_ingestion_rejects_single_class_target():
    rows = "\n".join(f"{i},1" for i in range(40))
    r = _upload("mono.csv", ("x,y\n" + rows).encode())
    assert r.status_code == 400
    assert "seule valeur" in r.json()["detail"]


def test_ingestion_rejects_empty_columns():
    r = _upload("empty.csv", b"\n\n\n")
    assert r.status_code == 400


def test_data_quality_warnings_surfaced():
    """A usable-but-flawed dataset is accepted, with warnings in the payload."""
    import io
    # A constant column + a heavily-missing column, valid binary target.
    lines = ["const,mostly_missing,y"]
    for i in range(60):
        miss = "" if i < 50 else "1"
        lines.append(f"7,{miss},{i % 2}")
    body = ("\n".join(lines)).encode()
    r = _upload("flawed.csv", body)
    assert r.status_code == 200, r.text
    codes = {w["code"] for w in r.json()["data_quality"]}
    assert "constant_columns" in codes
    assert "heavy_missing" in codes


def test_clean_demo_has_no_fatal_and_payload_shape():
    body = _start_demo("breastcancer.csv")
    assert "data_quality" in body           # always present (list)
    assert isinstance(body["data_quality"], list)


def test_stage_failure_is_clean_error_not_500():
    """Running a model stage before separation yields a clean 409, never a 500."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    r = client.post(f"/api/session/{sid}/stage/model/run", json={"config": {}})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]                # actionable message present


def test_autorun_resilient_returns_status_on_stop():
    """Autorun always returns a structured status, never propagates a 500."""
    sid = _start_demo("breastcancer.csv")["session_id"]
    r = client.post(f"/api/session/{sid}/autorun")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "ran" in body and "status" in body


def test_monitoring_psi_and_ks():
    """PSI and KS separate identical from shifted distributions."""
    import numpy as np
    from pipeline import monitoring as mon
    rng = np.random.RandomState(0)
    a, b = rng.normal(0, 1, 800), rng.normal(0, 1, 800)
    shifted = rng.normal(1.5, 1, 800)
    assert mon.psi(a, b) < 0.1                    # same -> stable
    assert mon.psi(a, shifted) > 0.25            # shifted -> major
    assert mon.ks(a, shifted)[1] < 0.05          # KS rejects same-distribution


def test_monitoring_endpoint_stable_batch():
    """A batch drawn from the training data reports stable reproducibility."""
    import io
    import pandas as pd
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    df = pd.read_csv("../data/breastcancer.csv").sample(150, random_state=3)
    buf = io.BytesIO(); df.to_csv(buf, index=False); buf.seek(0)
    r = client.post(f"/api/session/{sid}/monitor",
                    files={"file": ("batch.csv", buf, "text/csv")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["available"] is True
    assert j["reproducibility"]["deterministic"] is True
    assert "data_drift" in j and "prediction_drift" in j
    assert len(j["plots"]) == 2


def test_monitoring_detects_shifted_batch():
    """A deliberately shifted batch triggers major data drift."""
    import io
    import numpy as np
    import pandas as pd
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    df = pd.read_csv("../data/breastcancer.csv").sample(150, random_state=4).copy()
    num = df.select_dtypes("number").columns
    df[num] = df[num] * 3.0 + 50.0            # strong distribution shift
    buf = io.BytesIO(); df.to_csv(buf, index=False); buf.seek(0)
    r = client.post(f"/api/session/{sid}/monitor",
                    files={"file": ("shifted.csv", buf, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["data_drift"]["n_major"] >= 1
    assert r.json()["overall"] == "major"


def test_monitoring_requires_trained_model():
    sid = _start_demo("breastcancer.csv")["session_id"]
    import io
    buf = io.BytesIO(b"a,b\n1,2\n3,4\n")
    r = client.post(f"/api/session/{sid}/monitor",
                    files={"file": ("x.csv", buf, "text/csv")})
    assert r.status_code == 409


def test_sanitize_config_column_table_filters_unknown_columns():
    schema = [{"name": "dropped_features", "type": "column_table",
               "columns": [{"column": "a"}, {"column": "b"}]}]
    out = llm_agent.sanitize_config(schema, {"dropped_features": ["a", "ghost", "b"]})
    assert out["dropped_features"] == ["a", "b"]  # hallucinated column rejected


def test_assist_records_journal_memory(monkeypatch):
    """A sub-step AI assist is journalled (memory) and the level toggle persists."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)  # deterministic heuristic path
    sid = _start_demo("house_price_data.csv")["session_id"]
    client.post(f"/api/session/{sid}/stage/clean/run", json={"config": {}})
    r = client.post(f"/api/session/{sid}/stage/transform/assist",
                    json={"topic": "typologie", "label": "Typologie"})
    assert r.status_code == 200, r.text
    a = r.json()
    assert isinstance(a["explanation"], list) and a["explanation"]
    assert a["stage"] == "transform" and a["topic"] == "typologie"
    j = client.get(f"/api/session/{sid}/journal").json()
    assert len(j["insights"]) == 1 and j["insights"][0]["topic"] == "typologie"
    client.post(f"/api/session/{sid}/level", json={"level": "expert"})
    assert client.get(f"/api/session/{sid}/journal").json()["level"] == "expert"


def test_sanitize_config_rejects_invalid():
    schema = [
        {"name": "scaler", "type": "select", "options": [{"value": "standard", "label": "x"}]},
        {"name": "test_size", "type": "range", "min": 0.1, "max": 0.5},
        {"name": "flag", "type": "toggle"},
    ]
    out = llm_agent.sanitize_config(schema, {
        "scaler": "INVALID", "test_size": 99, "flag": 1, "ghost_key": "drop me",
    })
    assert "scaler" not in out          # invalid option dropped
    assert out["test_size"] == 0.5      # clamped to max
    assert out["flag"] is True          # coerced to bool
    assert "ghost_key" not in out       # unknown key dropped
