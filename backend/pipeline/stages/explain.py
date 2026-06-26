"""
explain.py — Stage : EXPLICABILITE (SHAP).

Explains the current model (tuned if available, else baseline) with SHAP:
a global importance bar (summary) and a single-prediction decomposition
(waterfall), mirroring the J1 notebook. Uses TreeExplainer for tree models;
falls back to a clear message for non-tree models. Supervised only.
"""

import io
import base64

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap

from ..context import REGRESSION, CLASSIFICATION
from ..plotting import message_plot
from .base import number

STAGE_ID = "explain"
TITLE = "Explicabilité"
OBJECTIVE = "Comprendre les prédictions : importance globale (SHAP) et décomposition d'un cas (waterfall)."

_TREE_NAMES = ("DecisionTree", "RandomForest", "GradientBoosting", "XGB")


def _is_tree(model) -> bool:
    return any(name in type(model).__name__ for name in _TREE_NAMES)


def default_config(ctx):
    return {"sample_index": 0}


def config_schema(ctx):
    if ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return []
    return [number("sample_index", "Cas à expliquer (waterfall)", 0, 0, 100000,
                   "Indice de la ligne du jeu de test à décomposer.")]


def diagnose(session):
    if session.ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return {"diagnostics": {"ready": False, "reason": "Explicabilité SHAP supervisée uniquement."}, "plots": []}
    model, origin = session.current_model()
    if model is None:
        return {"diagnostics": {"ready": False, "reason": "Entraînez un modèle d'abord."}, "plots": []}
    return {"diagnostics": {"ready": True, "model_origin": origin, "shap_tree_supported": _is_tree(model)}, "plots": []}


def run(session, config):
    ctx = session.ctx
    if ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        raise ValueError("L'explicabilité SHAP ne s'applique qu'à l'apprentissage supervisé.")
    model, origin = session.current_model()
    sep = session.get_run("separate")
    if model is None or sep is None:
        raise ValueError("Un modèle entraîné (Modélisation) est requis avant l'explicabilité.")

    cfg = {**default_config(ctx), **(config or {})}
    feature_names = sep.artifacts.get("feature_names", [])
    X_test = sep.artifacts["X_test"]
    Xdf = X_test if isinstance(X_test, pd.DataFrame) else pd.DataFrame(X_test, columns=feature_names)
    Xs = Xdf.sample(min(150, len(Xdf)), random_state=42) if len(Xdf) > 150 else Xdf

    if not _is_tree(model):
        return ({
            "report": {"Modèle": origin, "SHAP": "non disponible"},
            "diagnostics": {"shap_supported": False},
            "log": ["Modèle non arborescent : SHAP TreeExplainer indisponible."],
            "warnings": ["Choisissez un modèle à base d'arbres (RandomForest, Gradient Boosting, XGBoost) pour l'explicabilité SHAP."],
            "plots": [message_plot("SHAP TreeExplainer requiert un modèle à base d'arbres.")],
        }, {})

    try:
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(Xs)
    except Exception as e:
        return ({
            "report": {"SHAP": "erreur"}, "diagnostics": {"error": str(e)},
            "log": [f"SHAP a échoué : {e}"], "warnings": [],
            "plots": [message_plot("SHAP : " + str(e)[:120])],
        }, {})

    # Classification TreeExplainer may return one array per class — use the last class.
    sv_use = sv[-1] if isinstance(sv, list) else sv
    if isinstance(sv_use, np.ndarray) and sv_use.ndim == 3:
        sv_use = sv_use[:, :, -1]

    plots = [_summary_plot(sv_use, Xs)]
    wf = _waterfall_plot(explainer, sv, Xs, int(cfg["sample_index"]))
    if wf:
        plots.append(wf)

    mean_abs = np.abs(sv_use).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][:8]
    top = [{"feature": str(Xs.columns[i]), "importance_shap": round(float(mean_abs[i]), 4)} for i in order]

    result = {
        "report": {"Modèle expliqué": origin, "Variable la plus influente": top[0]["feature"] if top else "—"},
        "diagnostics": {"shap_top_features": top, "model_origin": origin},
        "log": [f"SHAP TreeExplainer sur {len(Xs)} observations de test ({origin})."],
        "warnings": [], "plots": plots,
    }
    return result, {}


# ── SHAP plots → captioned base64 (light background, SHAP draws dark text) ──
def _save_light(fig, caption="") -> dict:
    fig.patch.set_facecolor("white")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160, facecolor="white")
    buf.seek(0)
    out = "data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    # Captioned like every other plot so the UI offers a per-graph AI explainer.
    return {"img": out, "caption": caption, "topic": caption}


def _summary_plot(sv_use, Xs) -> str:
    plt.figure()
    try:
        shap.summary_plot(sv_use, Xs, plot_type="bar", show=False, max_display=12)
    except Exception:
        plt.close("all")
        return message_plot("SHAP summary indisponible.")
    fig = plt.gcf()
    fig.set_size_inches(8, 5)
    return _save_light(fig, "Importance SHAP des variables (impact moyen sur la prédiction)")


def _waterfall_plot(explainer, sv, Xs, idx) -> str:
    idx = max(0, min(idx, len(Xs) - 1))
    try:
        base = explainer.expected_value
        if isinstance(base, (list, np.ndarray)) and np.ndim(base) > 0:
            base = np.ravel(base)[-1]
        row = sv[-1][idx] if isinstance(sv, list) else (sv[idx] if sv.ndim == 2 else sv[idx, :, -1])
        expl = shap.Explanation(values=np.asarray(row), base_values=float(base),
                                data=Xs.iloc[idx].values, feature_names=list(Xs.columns))
        plt.figure()
        shap.plots.waterfall(expl, show=False, max_display=12)
        fig = plt.gcf()
        fig.set_size_inches(8, 5)
        return _save_light(fig, "Explication SHAP d'une prédiction individuelle (waterfall)")
    except Exception:
        plt.close("all")
        return None
