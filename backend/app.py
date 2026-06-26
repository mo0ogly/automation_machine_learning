"""
app.py — ML Automator API (staged, expert-in-the-loop).

The ML construction is exposed as six replayable stages:

    Nettoyage -> Transformation -> Integration -> Separation -> Model -> Evaluation

For each stage the expert can: read deterministic diagnostics, ask the Groq
agent for a refinement recommendation, adjust the config, and run / re-run that
single stage. Re-running a stage invalidates downstream stages (see session.py).
"""

import io
import random

import env_loader  # noqa: F401  — loads backend/.env on import
import pandas as pd
import joblib
from fastapi import FastAPI, UploadFile, File, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from pipeline import SESSIONS
from pipeline import diagnostics as dg
from pipeline import explanations
from pipeline import plotting
from pipeline import scoring
from pipeline.registry import get_stage, stage_meta, all_stage_meta, DATA_STAGE_IDS
from pipeline.stages.base import to_native
import llm_agent
import routes_ai
import dataset_cards
from pydantic import BaseModel
from rl import GridWorld, train_qlearning, summarise
from rl import plots as rl_plots

app = FastAPI(title="ML Automator — Staged Pipeline API")

DATA_DIR = Path(__file__).parent.parent / "data"
EXPORT_DIR = Path(__file__).parent / "exports"

# Demo datasets that must be treated as unsupervised anomaly detection (no target).
_ANOMALY_DEMOS = {"transactions.csv"}
# Columns dropped at load for a clean demo: a non-predictive key, and a second
# target that would leak (cyber_risk ships both risk_score and risk_label).
_DEMO_DROP = {"cyber_risk.csv": ["asset_id", "risk_score"]}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Multi-provider AI-backend management (catalog, CRUD, key, test). See routes_ai.py.
app.include_router(routes_ai.router)


# ── basic / meta ────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/agent-status")
def get_agent_status():
    return llm_agent.agent_status()


@app.post("/api/agent/model")
def set_agent_model(body: dict = Body(default={})):
    """Switch the agent's LLM model at runtime (from the UI dropdown)."""
    model = body.get("model", "")
    if not llm_agent.set_model(model):
        raise HTTPException(status_code=400, detail=f"Modèle inconnu : {model}")
    return llm_agent.agent_status()


@app.get("/api/demo-datasets")
def list_demo_datasets():
    return {"datasets": [
        {"name": "cyber_risk.csv", "type": "Classification multiclasse",
         "description": "Risque cyber — priorisation d'actifs (4 niveaux, synthétique)"},
        {"name": "house_price_data.csv", "type": "Régression",
         "description": "Prix immobiliers — biens & variables"},
        {"name": "breastcancer.csv", "type": "Classification binaire",
         "description": "Diagnostic — bénin / malin"},
        {"name": "Stars.csv", "type": "Classification multiclasse",
         "description": "Type d'étoile — 6 classes"},
        {"name": "client_data.csv", "type": "Clustering",
         "description": "Segmentation clients"},
        {"name": "transactions.csv", "type": "Détection d'anomalies",
         "description": "Transactions — anomalies / fraude (non supervisé)"},
    ]}


@app.get("/api/dataset-card/{name}")
def dataset_card(name: str):
    """Rich data card for a demo dataset (summary, schema, target, ML notes, source)."""
    card = dataset_cards.get(name)
    if card is None:
        raise HTTPException(status_code=404, detail="Pas de fiche pour ce jeu de données.")
    return card


# ── session lifecycle ───────────────────────────────────────────────────
def _read_csv(file_bytes: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV illisible : {e}")


def _session_payload(session) -> dict:
    ctx = session.ctx
    return to_native({
        "session_id": session.id,
        "filename": session.filename,
        "context": ctx.to_dict(),
        "overview": dg.overview(session.raw_df, ctx.target_col),
        "stages": all_stage_meta(),
        "status": session.stage_status(),
        "agent": llm_agent.agent_status(),
    })


@app.post("/api/session/start")
async def session_start(file: UploadFile = File(...)):
    df = _read_csv(await file.read())
    session = SESSIONS.create(file.filename, df)
    return _session_payload(session)


@app.post("/api/session/start-demo/{dataset_name}")
def session_start_demo(dataset_name: str):
    csv_path = DATA_DIR / dataset_name
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' introuvable.")
    df = _read_csv(csv_path.read_bytes())
    drop = [c for c in _DEMO_DROP.get(dataset_name, []) if c in df.columns]
    if drop:  # remove a non-predictive key / a leaking second target before detection
        df = df.drop(columns=drop)
    session = SESSIONS.create(dataset_name, df)
    if dataset_name in _ANOMALY_DEMOS:  # dedicated unsupervised anomaly-detection demo
        from pipeline.context import ANOMALY
        session.ctx.problem_type = ANOMALY
        session.ctx.target_col = None
        SESSIONS.save(session)  # ctx overridden after create -> re-persist
    return _session_payload(session)


@app.get("/api/session/{session_id}")
def session_info(session_id: str):
    session = _require_session(session_id)
    return _session_payload(session)


# ── per-stage helpers ───────────────────────────────────────────────────
def _require_session(session_id: str):
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session inconnue ou expirée.")
    return session


def _stage_schema_default(session, stage_id):
    """Resolve (schema, default_config, input_df, input_error) for a stage."""
    stage = get_stage(stage_id)
    ctx = session.ctx
    if stage_id in DATA_STAGE_IDS:
        df_in, err = session.input_df_for(stage_id)
        base_df = df_in if df_in is not None else session.raw_df
        return stage.config_schema(base_df, ctx), stage.default_config(base_df, ctx), df_in, err
    return stage.config_schema(ctx), stage.default_config(ctx), None, None


def _diagnostics_for(session, stage_id, df_in, input_error):
    stage = get_stage(stage_id)
    if stage_id in DATA_STAGE_IDS and df_in is None:
        return {"diagnostics": {"ready": False, "reason": input_error}, "plots": []}
    # Serialise figure generation — pyplot global state is not thread-safe.
    with plotting.PLOT_LOCK:
        if stage_id in DATA_STAGE_IDS:
            return stage.diagnose(df_in, session.ctx)
        return stage.diagnose(session)


@app.get("/api/session/{session_id}/stage/{stage_id}")
def stage_view(session_id: str, stage_id: str):
    session = _require_session(session_id)
    if get_stage(stage_id) is None:
        raise HTTPException(status_code=404, detail=f"Étape '{stage_id}' inconnue.")
    schema, default, df_in, err = _stage_schema_default(session, stage_id)
    diag = _diagnostics_for(session, stage_id, df_in, err)
    run = session.get_run(stage_id)
    return to_native({
        "meta": stage_meta(stage_id),
        "explanation": explanations.for_stage(stage_id, session.ctx),
        "supervised": session.ctx.supervised,
        "schema": schema,
        "default_config": default,
        "current_config": run.config if run else default,
        "status": {"ran": run is not None, "stale": bool(run.stale) if run else False},
        "input_error": err,
        "diagnostics": diag.get("diagnostics", {}),
        "diagnose_plots": diag.get("plots", []),
        "result": run.result if run else None,
    })


@app.post("/api/session/{session_id}/stage/{stage_id}/recommend")
def stage_recommend(session_id: str, stage_id: str, body: dict = Body(default={})):
    session = _require_session(session_id)
    if get_stage(stage_id) is None:
        raise HTTPException(status_code=404, detail=f"Étape '{stage_id}' inconnue.")
    schema, default, df_in, err = _stage_schema_default(session, stage_id)
    if stage_id in DATA_STAGE_IDS and df_in is None:
        raise HTTPException(status_code=409, detail=err)
    diag = _diagnostics_for(session, stage_id, df_in, err)
    current = {**default, **(body.get("config") or {})}
    rec = llm_agent.recommend(stage_meta(stage_id), session.ctx.problem_type,
                              diag.get("diagnostics", {}), schema, current, session.journal_summary())
    text = rec.get("summary") or (rec.get("rationale") or [""])[0]
    if text:
        session.add_insight(stage_id, "affinage", "Affinage proposé", text,
                            rec.get("source", "llm"), rec.get("model"))
        SESSIONS.save(session)  # journal mutated -> persist
    return to_native(rec)


def _run_stage(session, stage_id, config):
    stage = get_stage(stage_id)
    ctx = session.ctx
    if stage_id in DATA_STAGE_IDS:
        df_in, err = session.input_df_for(stage_id)
        if err:
            raise HTTPException(status_code=409, detail=err)
        with plotting.PLOT_LOCK:  # serialise pyplot (not thread-safe)
            out = stage.run(df_in, config, ctx)
        if isinstance(out, tuple) and len(out) == 3:
            df_out, result, artifacts = out
        else:
            df_out, result = out
            artifacts = None
        session.record(stage_id, config, result, output_df=df_out, artifacts=artifacts)
        return result
    # model / evaluate operate on session artefacts
    try:
        with plotting.PLOT_LOCK:  # serialise pyplot (not thread-safe)
            result, artifacts = stage.run(session, config)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    session.record(stage_id, config, result, output_df=None, artifacts=artifacts)
    return result


@app.post("/api/session/{session_id}/stage/{stage_id}/run")
def stage_run(session_id: str, stage_id: str, body: dict = Body(default={})):
    session = _require_session(session_id)
    if get_stage(stage_id) is None:
        raise HTTPException(status_code=404, detail=f"Étape '{stage_id}' inconnue.")
    result = _run_stage(session, stage_id, body.get("config") or {})
    SESSIONS.save(session)  # stage recorded + downstream invalidated -> persist
    return to_native({"stage_id": stage_id, "result": result, "status": session.stage_status()})


@app.post("/api/session/{session_id}/stage/{stage_id}/interpret")
def stage_interpret(session_id: str, stage_id: str, body: dict = Body(default={})):
    """AI interpretation/conclusion of a stage's results (natural language)."""
    session = _require_session(session_id)
    if get_stage(stage_id) is None:
        raise HTTPException(status_code=404, detail=f"Étape '{stage_id}' inconnue.")
    run = session.get_run(stage_id)
    if run is None or run.result is None:
        raise HTTPException(status_code=409, detail="Exécutez l'étape avant de demander une interprétation.")
    payload = {"report": run.result.get("report"), "diagnostics": run.result.get("diagnostics")}
    out = llm_agent.interpret(stage_meta(stage_id)["title"], session.ctx.problem_type,
                              payload, session.journal_summary())
    if out.get("verdict") or out.get("interpretation"):
        session.add_insight(stage_id, "interpretation", "Interprétation du résultat",
                            out.get("verdict") or out.get("interpretation"),
                            out.get("source", "llm"), out.get("model"))
        SESSIONS.save(session)  # journal mutated -> persist
    return to_native(out)


def _cap(v, n=12):
    return v[:n] if isinstance(v, list) else v


def _assist_focus(topic, diag, result, schema):
    """Resolve the compact data subset the assistant should explain for `topic`."""
    if topic.startswith("param:"):  # per-field config helper -> give that field's descriptor
        fname = topic.split(":", 1)[1]
        field = next((c for c in (schema or []) if c.get("name") == fname), None)
        if field:
            keep = ("name", "label", "help", "type", "options", "min", "max", "step", "default")
            return {"parametre": {k: field[k] for k in keep if k in field}}
    if topic == "decision":
        out = []
        for t in [c for c in schema if c.get("type") == "column_table"]:
            rows = t.get("columns") or []
            drop = [r for r in rows if r.get("recommended") == "retirer"]
            out.append({"table": t.get("label"), "n_total": len(rows), "n_reco_retirer": len(drop),
                        "exemples_retirer": [{k: r.get(k) for k in ("column", "reason")} for r in drop[:8]]})
        if out:
            return {"decisions": out}
    if topic in diag:
        return {topic: _cap(diag[topic])}
    rdiag = (result or {}).get("diagnostics") or {}
    if topic in rdiag:
        return {topic: _cap(rdiag[topic])}
    if topic == "result" and result:
        return {"report": result.get("report"), "diagnostics": {k: _cap(v) for k, v in rdiag.items()}}
    # Unmatched topic (e.g. a per-graph "graphe: <titre>"): give diag + result context.
    out = {}
    if diag:
        out["diagnostics"] = {k: _cap(v) for k, v in diag.items()}
    if result:
        out["result"] = {"report": result.get("report"),
                         "diagnostics": {k: _cap(v) for k, v in rdiag.items()}}
    return out


@app.post("/api/session/{session_id}/stage/{stage_id}/assist")
def stage_assist(session_id: str, stage_id: str, body: dict = Body(default={})):
    """Specialized AI helper for a sub-step element; journalled into session memory."""
    session = _require_session(session_id)
    if get_stage(stage_id) is None:
        raise HTTPException(status_code=404, detail=f"Étape '{stage_id}' inconnue.")
    topic = str(body.get("topic") or "diagnostics")
    label = str(body.get("label") or topic)
    level = str(body.get("level") or session.level).lower()
    if level in ("novice", "expert"):
        session.level = level
    schema, default, df_in, err = _stage_schema_default(session, stage_id)
    diag = _diagnostics_for(session, stage_id, df_in, err).get("diagnostics", {})
    run = session.get_run(stage_id)
    focus = _assist_focus(topic, diag, run.result if run else None, schema)
    current = {**default, **(body.get("config") or {})}
    out = llm_agent.assist(stage_meta(stage_id)["title"], session.ctx.problem_type,
                           topic, focus, session.journal_summary(), session.level,
                           schema, current)
    entry = session.add_insight(stage_id, topic, label,
                                out.get("explanation") or out.get("takeaway"),
                                out.get("source", "llm"), out.get("model"))
    SESSIONS.save(session)  # level + journal mutated -> persist
    return to_native({**out, "insight_id": entry["id"], "stage": stage_id, "topic": topic, "label": label})


@app.get("/api/session/{session_id}/journal")
def session_journal(session_id: str):
    session = _require_session(session_id)
    return to_native({"insights": session.insights, "level": session.level})


@app.post("/api/session/{session_id}/journal")
def session_journal_add(session_id: str, body: dict = Body(default={})):
    """Record an expert decision (e.g. an applied AI action) into the journal/memory."""
    session = _require_session(session_id)
    entry = session.add_insight(
        str(body.get("stage") or ""), str(body.get("topic") or "action"),
        str(body.get("label") or "Décision"), body.get("text") or "",
        str(body.get("source") or "user"), None)
    SESSIONS.save(session)  # expert decision journalled -> persist
    return to_native({"insight_id": entry["id"], "insights": session.insights})


@app.post("/api/session/{session_id}/level")
def session_level(session_id: str, body: dict = Body(default={})):
    session = _require_session(session_id)
    lvl = str(body.get("level") or "").lower()
    if lvl in ("novice", "expert"):
        session.level = lvl
        SESSIONS.save(session)  # level changed -> persist
    return to_native({"level": session.level})


@app.post("/api/session/{session_id}/autorun")
def session_autorun(session_id: str):
    """Run the core pipeline with default config (quick end-to-end pass).

    The optional refinement stages (`tune` = GridSearch, `explain` = SHAP) are
    skipped here — they are expensive and run on demand from the UI.
    """
    session = _require_session(session_id)
    from pipeline.registry import STAGE_IDS
    core = [s for s in STAGE_IDS if s not in ("tune", "explain")]
    ran = []
    for sid in core:
        try:
            _run_stage(session, sid, {})
            ran.append(sid)
        except HTTPException as e:
            return to_native({"ran": ran, "stopped_at": sid, "reason": e.detail,
                              "status": session.stage_status()})
    final = session.get_run("evaluate")
    return to_native({"ran": ran, "skipped": ["tune", "explain"], "status": session.stage_status(),
                      "metrics": (final.result.get("metrics") if final else None)})


# ── reinforcement learning (3rd paradigm — separate from the 8-stage pipeline) ──
class RLTrainRequest(BaseModel):
    size: int = 5
    episodes: int = 300
    alpha: float = 0.1
    gamma: float = 0.95
    epsilon: float = 1.0
    obstacles: list = []
    traps: list = []
    n_traps: int = 0
    n_goals: int = 1


def _clean_cells(cells, size, exclude):
    """Keep only in-grid (row, col) cells that aren't the start/goal/each other."""
    out = []
    for cell in (cells or []):
        try:
            r, c = int(cell[0]), int(cell[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if 0 <= r < size and 0 <= c < size and (r, c) not in exclude:
            out.append((r, c))
    return out


@app.post("/api/rl/train")
def rl_train(req: RLTrainRequest):
    """Train a tabular Q-learning agent on a GridWorld; return metrics + plots."""
    size = max(3, min(10, int(req.size)))
    episodes = max(20, min(2000, int(req.episodes)))
    alpha = min(max(float(req.alpha), 0.01), 1.0)
    gamma = min(max(float(req.gamma), 0.5), 0.999)
    epsilon = min(max(float(req.epsilon), 0.0), 1.0)
    n_traps = max(0, min(5, int(req.n_traps)))
    n_goals = max(1, min(3, int(req.n_goals)))

    start, default_goal = (0, 0), (size - 1, size - 1)
    reserved = {start, default_goal}
    obstacles = _clean_cells(req.obstacles, size, reserved)
    reserved |= set(obstacles)
    explicit_traps = _clean_cells(req.traps, size, reserved)
    reserved |= set(explicit_traps)

    # Deterministic placement of extra goals/traps on free cells (seeded, reproducible).
    rng = random.Random(42)
    free = [(r, c) for r in range(size) for c in range(size) if (r, c) not in reserved]
    rng.shuffle(free)
    goals = {default_goal}
    while len(goals) < n_goals and free:
        goals.add(free.pop())
    traps = list(explicit_traps)
    free = [cell for cell in free if cell not in goals]
    while len(traps) < len(explicit_traps) + n_traps and free:
        traps.append(free.pop())

    env = GridWorld(size=size, obstacles=obstacles, traps=traps, goals=goals)
    with plotting.PLOT_LOCK:  # serialise pyplot (not thread-safe)
        result = train_qlearning(env, episodes=episodes, alpha=alpha, gamma=gamma, epsilon=epsilon)
        figs = rl_plots.all_plots(result, env)
    return to_native({
        "metrics": summarise(result, env),
        "plots": figs,
        "config": {"size": size, "episodes": episodes, "alpha": alpha, "gamma": gamma,
                   "epsilon": epsilon, "n_traps": n_traps, "n_goals": n_goals},
        "env": {"size": size, "start": list(env.start),
                "goals": [list(g) for g in env.goals],
                "obstacles": [list(o) for o in obstacles], "traps": [list(t) for t in traps]},
    })


# Q-learning hyperparameters + help text, consumed by the per-slider AI helper.
_RL_FIELDS = [
    {"name": "size", "label": "Taille de la grille", "type": "range", "min": 3, "max": 10, "step": 1, "default": 5,
     "help": "Côté du labyrinthe GridWorld (N×N). Plus grand = espace d'états plus vaste, donc plus long à apprendre."},
    {"name": "episodes", "label": "Nombre d'épisodes", "type": "range", "min": 20, "max": 2000, "step": 20, "default": 300,
     "help": "Nombre de parties d'entraînement. Plus d'épisodes = la table Q converge mieux (mais c'est plus long)."},
    {"name": "alpha", "label": "Taux d'apprentissage (alpha)", "type": "range", "min": 0.01, "max": 1.0, "step": 0.01, "default": 0.1,
     "help": "Vitesse de mise à jour de Q : haut = apprend vite mais instable ; bas = lent mais stable."},
    {"name": "gamma", "label": "Facteur d'actualisation (gamma)", "type": "range", "min": 0.5, "max": 0.999, "step": 0.001, "default": 0.95,
     "help": "Poids des récompenses futures : proche de 1 = vision long terme ; plus bas = privilégie le gain immédiat."},
    {"name": "epsilon", "label": "Exploration initiale (epsilon)", "type": "range", "min": 0.0, "max": 1.0, "step": 0.05, "default": 1.0,
     "help": "Part d'actions aléatoires au départ (exploration vs exploitation). Décroît au fil de l'entraînement."},
    {"name": "n_goals", "label": "Nombre de buts", "type": "range", "min": 1, "max": 3, "step": 1, "default": 1,
     "help": "Nombre de cases-objectif récompensées. Plusieurs buts = plusieurs solutions optimales possibles."},
    {"name": "n_traps", "label": "Nombre de pièges", "type": "range", "min": 0, "max": 5, "step": 1, "default": 0,
     "help": "Cases pénalisantes qui terminent l'épisode. Plus de pièges = environnement plus risqué à naviguer."},
]
_RL_FIELDS_BY_NAME = {f["name"]: f for f in _RL_FIELDS}


@app.post("/api/rl/explain")
def rl_explain(body: dict = Body(default={})):
    """Explain one Q-learning hyperparameter (reuses the session-free assist agent)."""
    param = str(body.get("param") or "")
    field = _RL_FIELDS_BY_NAME.get(param)
    if field is None:
        raise HTTPException(status_code=404, detail=f"Paramètre RL inconnu : {param}")
    level = str(body.get("level") or "novice").lower()
    out = llm_agent.assist("Apprentissage par renforcement (Q-learning)", "reinforcement",
                           "param:" + param, {"parametre": field}, "", level, _RL_FIELDS,
                           body.get("config") or {})
    return to_native({**out, "param": param})


# ── exploitation : le modèle en action ────────────────────────────────────
def _require_trained(session_id: str):
    session = _require_session(session_id)
    if session.get_run("separate") is None or session.get_run("model") is None:
        raise HTTPException(status_code=409, detail="Entraînez le modèle (Séparation + Modélisation) d'abord.")
    return session


@app.get("/api/session/{session_id}/serving-schema")
def serving_schema(session_id: str):
    """Dynamic, dataset-agnostic input form: one control per ORIGINAL column."""
    return to_native(scoring.serving_schema(_require_trained(session_id)))


@app.post("/api/session/{session_id}/predict")
def predict(session_id: str, body: dict = Body(default={})):
    """Predict from friendly RAW inputs (re-applies the training transforms)."""
    session = _require_trained(session_id)
    row = body.get("features") if isinstance(body.get("features"), dict) else body
    try:
        return to_native(scoring.predict_one(session, row or {}))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/session/{session_id}/predict/sensitivity")
def predict_sensitivity(session_id: str, body: dict = Body(default={})):
    """Sweep one feature across its range -> the model's response curve."""
    session = _require_trained(session_id)
    feature = body.get("feature")
    if not feature:
        raise HTTPException(status_code=422, detail="Champ 'feature' requis.")
    try:
        return to_native(scoring.sensitivity(session, body.get("base") or {}, feature,
                                             int(body.get("points") or 21)))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/api/session/{session_id}/predict/tornado")
def predict_tornado(session_id: str, body: dict = Body(default={})):
    """Local one-at-a-time impact of each top feature on THIS prediction."""
    session = _require_trained(session_id)
    try:
        return to_native(scoring.tornado(session, body.get("base") or {}, int(body.get("top_k") or 8)))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


def _model_summary(session) -> dict:
    """Factual model dossier handed to the executive / expert AI personas."""
    ev, mdl, sep = session.get_run("evaluate"), session.get_run("model"), session.get_run("separate")
    schema = scoring.serving_schema(session)
    report = ev.result.get("report", {}) if ev else {}
    diag = ev.result.get("diagnostics", {}) if ev else {}
    return {
        "problem_type": session.ctx.problem_type,
        "target": session.ctx.target_col,
        "algorithm": (mdl.result.get("diagnostics", {}).get("algorithm") if mdl else None),
        "n_features": len(sep.artifacts.get("feature_names", [])) if sep else None,
        "n_rows": int(len(session.raw_df)),
        "metrics": report,
        "overfit": diag.get("controle_surapprentissage") if isinstance(diag, dict) else None,
        "per_class": diag.get("rapport_par_classe") if isinstance(diag, dict) else None,
        "top_features": [f["name"] for f in schema["fields"][:8]],
        "leakage": bool(sep.result.get("diagnostics", {}).get("leakage_candidates")) if sep else False,
        "target_stats": schema.get("target_stats"),
    }


@app.post("/api/session/{session_id}/analyze")
def analyze(session_id: str, body: dict = Body(default={})):
    """AI analysis of the trained model, as an executive brief or an expert review."""
    session = _require_trained(session_id)
    persona = "expert" if str(body.get("persona") or "").lower() == "expert" else "executive"
    ms = _model_summary(session)
    fn = llm_agent.expert_review if persona == "expert" else llm_agent.executive_brief
    out = fn(ms, session.journal_summary())
    try:  # surface the analysis in the Copilot journal
        session.add_insight("exploit", "analyze:" + persona,
                            "Revue expert" if persona == "expert" else "Synthèse exécutive",
                            out.get("points", []), out.get("source", "llm"), out.get("model"))
        SESSIONS.save(session)
    except Exception:
        pass
    return to_native({**out, "persona": persona, "model_summary": ms})


@app.get("/api/session/{session_id}/download-model")
def download_model(session_id: str):
    session = _require_session(session_id)
    sep, mdl = session.get_run("separate"), session.get_run("model")
    if sep is None or mdl is None:
        raise HTTPException(status_code=409, detail="Aucun modèle entraîné à exporter.")
    EXPORT_DIR.mkdir(exist_ok=True)
    path = EXPORT_DIR / f"expert_model_{session.id}.pkl"
    joblib.dump({
        "model": mdl.artifacts["model"],
        "feature_names": sep.artifacts.get("feature_names"),
        "target_col": sep.artifacts.get("target_col"),
        "problem_type": session.ctx.problem_type,
        "label_encoder": sep.artifacts.get("label_encoder"),
        "stage_recipe": {sid: r.config for sid, r in session.runs.items()},
    }, path)
    return FileResponse(path, filename="expert_model.pkl", media_type="application/octet-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
