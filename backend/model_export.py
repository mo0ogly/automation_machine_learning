"""
model_export.py — Turnkey, self-contained Python bundle for a trained session.

A bare ``model.pkl`` is not enough to reproduce predictions here: the model is
trained on the TRANSFORMED feature space, and the serving layer re-derives that
transform from the original training frame (see ``pipeline/scoring.py``). So a
usable export must ship: the fitted model, the original training data, the stage
configs, AND the exact transform code.

``build_bundle(session)`` returns a ``.zip`` (in memory) laid out as:

    model.joblib        fitted model (+ label encoder, cluster artefacts)
    training_data.csv   the original frame the transforms re-fit on
    config.json         problem type, target, stage configs, feature names, classes
    aegis_pipeline/     the genuine serving code (clean/transform/integrate/scoring)
    predict.py          turnkey CLI: score a raw CSV -> enriched CSV
    requirements.txt    pinned versions (this env) for byte-faithful reproduction
    README.md           usage

Fidelity by construction: the bundle reuses the project's own pipeline modules
rather than a re-implementation, so it can never drift from server behaviour.
"""

from __future__ import annotations

import io
import json
import zipfile
from importlib import metadata
from pathlib import Path

import joblib

from pipeline.context import CLUSTERING, ANOMALY

_PIPELINE_DIR = Path(__file__).parent / "pipeline"

# Exact subset the serving path needs (scoring -> clean/transform/integrate and
# their leaf deps). Verified import chain: none of these pulls shap/xgboost/registry.
_MODULES = ["context.py", "diagnostics.py", "typology.py", "eda_plots.py",
            "plotting.py", "scoring.py"]
_STAGE_MODULES = ["base.py", "clean.py", "transform.py", "integrate.py"]

# Base runtime deps for the serving chain; the model's own lib is appended below.
_BASE_REQS = ["scikit-learn", "pandas", "numpy", "scipy", "joblib", "matplotlib"]


def _requirements(model) -> str:
    libs = list(_BASE_REQS)
    mod = (type(model).__module__ or "")
    if mod.startswith("xgboost"):
        libs.append("xgboost")
    elif mod.startswith("lightgbm"):
        libs.append("lightgbm")
    lines = []
    for name in libs:
        try:
            lines.append(name + "==" + metadata.version(name))
        except Exception:  # not installed under that dist name -> leave unpinned
            lines.append(name)
    return "\n".join(lines) + "\n"


def _config(session) -> dict:
    ctx = session.ctx
    sep, mdl = session.get_run("separate"), session.get_run("model")
    le = sep.artifacts.get("label_encoder") if sep else None
    classes = None
    if le is not None and hasattr(le, "classes_"):
        classes = [str(c) for c in le.classes_]
    return {
        "filename": session.filename,
        "session_id": session.id,
        "created_at": getattr(session, "created_at", None),
        "problem_type": ctx.problem_type,
        "target": ctx.target_col,
        "supervised": bool(ctx.supervised),
        "feature_names": list((sep.artifacts.get("feature_names") if sep else []) or []),
        "classes": classes,
        "algorithm": (mdl.result.get("diagnostics", {}).get("algorithm") if mdl else None),
        "clean_cfg": dict((session.get_run("clean").config if session.get_run("clean") else {}) or {}),
        "transform_cfg": dict((session.get_run("transform").config if session.get_run("transform") else {}) or {}),
        "integrate_cfg": dict((session.get_run("integrate").config if session.get_run("integrate") else {}) or {}),
    }


def _model_payload(session) -> dict:
    """The fitted artefacts the predictor needs, kept minimal per problem type."""
    model, _origin = session.current_model()
    sep, mdl = session.get_run("separate"), session.get_run("model")
    payload = {"model": model,
               "label_encoder": sep.artifacts.get("label_encoder") if sep else None}
    # Centroid fallback (DBSCAN / Agglomerative) needs the training matrix + labels.
    if session.ctx.problem_type in (CLUSTERING, ANOMALY):
        if sep is not None and sep.artifacts.get("X_full") is not None:
            payload["X_full"] = sep.artifacts.get("X_full")
        if mdl is not None and mdl.artifacts.get("labels") is not None:
            payload["labels"] = mdl.artifacts.get("labels")
    return payload


def _read_template(name: str) -> str:
    return (Path(__file__).parent / "export_templates" / name).read_text(encoding="utf-8")


def build_bundle(session) -> bytes:
    """Assemble the turnkey .zip for a trained session and return its bytes."""
    cfg = _config(session)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. Fitted model + artefacts.
        mbuf = io.BytesIO()
        joblib.dump(_model_payload(session), mbuf, compress=3)
        z.writestr("model.joblib", mbuf.getvalue())

        # 2. Original training data (the transforms re-fit on it).
        z.writestr("training_data.csv", session.raw_df.to_csv(index=False))

        # 3. Config.
        z.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2, default=str))

        # 4. The genuine serving code, as a self-contained package. The two
        #    __init__.py are written empty so importing aegis_pipeline.scoring
        #    never pulls the heavy registry/explain (shap) chain.
        z.writestr("aegis_pipeline/__init__.py", "")
        z.writestr("aegis_pipeline/stages/__init__.py", "")
        for name in _MODULES:
            z.writestr("aegis_pipeline/" + name, (_PIPELINE_DIR / name).read_text(encoding="utf-8"))
        for name in _STAGE_MODULES:
            z.writestr("aegis_pipeline/stages/" + name,
                       (_PIPELINE_DIR / "stages" / name).read_text(encoding="utf-8"))

        # 5. Turnkey predictor + deps + docs.
        z.writestr("predict.py", _read_template("predict.py"))
        z.writestr("requirements.txt", _requirements(_model_payload(session)["model"]))
        z.writestr("README.md", _read_template("README.md"))
    return buf.getvalue()
