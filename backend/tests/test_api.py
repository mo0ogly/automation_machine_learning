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
    assert all("rmse_test" in r and "r2_test" in r for r in lb)
    assert sum(1 for r in lb if r["recommended"]) == 1     # exactly one recommended
    rmses = [r["rmse_test"] for r in lb]
    assert rmses == sorted(rmses)                           # ranked by RMSE ascending
    assert view["diagnostics"]["recommended_model"] == lb[0]["model"]


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


# ── reinforcement learning (3rd paradigm) ──────────────────────────────────
def test_gridworld_step_mechanics():
    from rl import GridWorld
    env = GridWorld(size=3)
    assert env.reset() == 0                       # start top-left
    s, r, done = env.step(1)                       # right
    assert s == 1 and r == -1.0 and not done
    env.reset()
    s, _, _ = env.step(0)                          # up off-grid -> stay in place
    assert s == 0
    env.reset()
    done = False
    for a in (1, 1, 2, 2):                         # right, right, down, down -> goal (2,2)
        s, r, done = env.step(a)
    assert done and r == 10.0 and env.at_goal()


def test_gridworld_multi_goals_and_traps():
    from rl import GridWorld
    env = GridWorld(size=4, goals=[(0, 3), (3, 3)], traps=[(1, 1)])
    for a in (1, 1, 1):                            # right x3 along clear row 0 -> near goal (0,3)
        s, r, done = env.step(a)
    assert done and r == 10.0 and env.state == (0, 3)
    env.reset()
    env.step(2)                                   # down -> (1,0)
    s, r, done = env.step(1)                       # right -> trap (1,1)
    assert done and r == -10.0 and env.state == (1, 1)


def test_qlearning_converges():
    from rl import GridWorld, train_qlearning, summarise
    env = GridWorld(size=4)
    summary = summarise(train_qlearning(env, episodes=300, seed=0), env)
    assert float(summary["Récompense finale (moy.)"]) > float(summary["Récompense initiale (moy.)"])
    assert float(summary["Taux de réussite final"].rstrip('%')) >= 80


def test_rl_train_route():
    r = client.post("/api/rl/train", json={"size": 4, "episodes": 150})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "metrics" in body and len(body["plots"]) == 3
    assert all(p["img"].startswith("data:image") and "caption" in p for p in body["plots"])
    assert body["env"]["size"] == 4


def test_rl_train_clamps_bounds():
    r = client.post("/api/rl/train", json={"size": 99, "episodes": 5, "gamma": 9})
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert 3 <= cfg["size"] <= 10 and cfg["episodes"] >= 20 and cfg["gamma"] <= 0.999


def test_rl_train_with_traps_and_goals():
    """Enriched environment: extra goals + visible traps are placed and returned."""
    r = client.post("/api/rl/train", json={"size": 5, "episodes": 100, "n_traps": 3, "n_goals": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["env"]["goals"]) == 2
    assert len(body["env"]["traps"]) == 3
    assert body["config"]["n_traps"] == 3 and body["config"]["n_goals"] == 2


# ── session persistence (survive a backend restart) ────────────────────────
def _populated_session():
    """Run a full supervised pipeline through the app, return the live Session."""
    from pipeline import SESSIONS
    sid = _start_demo("breastcancer.csv")["session_id"]
    client.post(f"/api/session/{sid}/autorun")
    client.post(f"/api/session/{sid}/level", json={"level": "expert"})
    return SESSIONS.get(sid)


def test_persistence_roundtrip_preserves_model_and_state(tmp_path):
    """A fully-run session (fitted model, splits, journal) survives save->load
    through a fresh store — the SQLite mirror that outlives a backend restart."""
    from pipeline import SessionStore, SessionPersistence

    live = _populated_session()
    live.add_insight("model", "note", "Note", "garder ce modèle", source="user")
    db = str(tmp_path / "sessions.db")

    # Process 1: write-through to disk.
    SessionStore(persistence=SessionPersistence(db_path=db)).save(live)

    # Process 2 (simulated restart): brand-new store, cold cache, same DB file.
    store2 = SessionStore(persistence=SessionPersistence(db_path=db))
    assert live.id not in store2._sessions          # cold cache
    restored = store2.get(live.id)                  # rehydrated from SQLite
    assert restored is not None

    # Identity + context + level.
    assert restored.id == live.id and restored.filename == live.filename
    assert restored.ctx.problem_type == live.ctx.problem_type
    assert restored.level == "expert"
    # Journal memory preserved verbatim.
    assert [i["text"] for i in restored.insights] == [i["text"] for i in live.insights]
    # Recorded stages preserved, including a usable fitted model.
    assert set(restored.runs) == set(live.runs)
    model, origin = restored.current_model()
    assert model is not None and origin in ("baseline", "tuned")
    Xte = restored.get_run("separate").artifacts["X_test"]
    assert len(model.predict(Xte)) == len(Xte)      # rehydrated model still predicts
    # Raw frame intact.
    assert restored.raw_df.shape == live.raw_df.shape
    assert list(restored.raw_df.columns) == list(live.raw_df.columns)


def test_persistence_drop_removes_blob(tmp_path):
    """Dropping a session removes its blob from the durable mirror too."""
    from pipeline import SessionStore, SessionPersistence
    db = str(tmp_path / "sessions.db")
    store = SessionStore(persistence=SessionPersistence(db_path=db))
    live = _populated_session()
    store.save(live)
    assert live.id in SessionPersistence(db_path=db).load_all_ids()
    store.drop(live.id)
    assert live.id not in SessionPersistence(db_path=db).load_all_ids()


def test_persistence_disabled_is_pure_memory(tmp_path):
    """With persistence off, save is a no-op and a cold lookup misses."""
    from pipeline import SessionStore, SessionPersistence
    db = str(tmp_path / "off.db")
    store = SessionStore(persistence=SessionPersistence(db_path=db, enabled=False))
    live = _populated_session()
    store.save(live)                                 # no-op
    assert SessionStore(persistence=SessionPersistence(db_path=db)).get(live.id) is None


# ── multi-provider AI backends (catalog + store + routes) ──────────────────
def test_ai_providers_catalog():
    """The provider catalog drives the UI dropdowns (single source of truth)."""
    r = client.get("/api/ai/providers")
    assert r.status_code == 200, r.text
    provs = {p["id"]: p for p in r.json()["providers"]}
    assert "groq" in provs and "openai_compat" in provs
    assert provs["groq"]["models"]                      # groq has curated models
    assert provs["openai_compat"]["base_url"] == "required"  # needs an endpoint
    assert "env_present" in provs["groq"]               # UI shows ready providers


def test_ai_store_crud(tmp_path, monkeypatch):
    """The store: create / key (write-only) / resolve / openai_compat base_url / delete."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)   # no auto-seed, no env key
    from ai_store import AiStore
    store = AiStore(path=str(tmp_path / "ai.json"))
    assert store.list_backends() == []                  # nothing seeded without a key

    b = store.create({"id": "b1", "provider": "groq", "model": "llama-3.1-8b-instant"})
    assert b["active"] is True and b["key_configured"] is False
    r = store.resolve()
    assert r["api_base"].startswith("https://api.groq.com") and r["key"] is None
    store.set_secret("b1", "sk-test")
    assert store.list_backends()[0]["key_configured"] is True
    assert store.resolve()["key"] == "sk-test"          # resolvable internally only

    with pytest.raises(ValueError):                     # openai_compat needs a base_url
        store.create({"id": "b2", "provider": "openai_compat", "model": "llama3.1"})
    store.create({"id": "b2", "provider": "openai_compat", "model": "llama3.1",
                  "base_url": "http://localhost:11434/v1"})
    assert store.resolve("b2")["api_base"] == "http://localhost:11434/v1"

    store.delete("b1")
    assert [x["id"] for x in store.list_backends()] == ["b2"]
    assert store.active_id() == "b2"                    # active moved off the deleted one


def test_ai_backends_route_roundtrip():
    """Create / key (never returned) / activate / delete over HTTP."""
    client.delete("/api/ai/backends/rt-test")           # tolerate a stale leftover
    r = client.post("/api/ai/backends", json={"id": "rt-test", "provider": "openai_compat",
                                              "model": "llama3.1", "base_url": "http://localhost:11434/v1"})
    assert r.status_code == 200, r.text
    assert any(b["id"] == "rt-test" for b in client.get("/api/ai/backends").json()["backends"])

    sk = client.post("/api/ai/backends/rt-test/secret", json={"key": "sk-xyz"})
    assert sk.status_code == 200 and sk.json()["key_configured"] is True
    # The key is write-only: it never appears in any listing.
    listing = client.get("/api/ai/backends").json()["backends"]
    assert all("key" not in b and "secret" not in b for b in listing)

    act = client.post("/api/ai/active", json={"id": "rt-test"})
    assert act.status_code == 200 and act.json()["active"] == "rt-test"

    client.delete("/api/ai/backends/rt-test")           # cleanup -> active reverts
    assert not any(b["id"] == "rt-test" for b in client.get("/api/ai/backends").json()["backends"])
