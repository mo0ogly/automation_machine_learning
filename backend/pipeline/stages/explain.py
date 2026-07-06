"""
explain.py — Stage : EXPLICABILITE (SHAP).

Explains the current model (tuned if available, else baseline) with SHAP:
a global importance bar (summary) and a single-prediction decomposition
(waterfall). Uses TreeExplainer for tree models and LinearExplainer for the
linear families (Linear / Ridge / Lasso / Logistic); other estimators get a
clear message. In multiclass problems the explained class is configurable
(default: the last / positive class). Supervised only.
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
from .. import explain_plots as pdp
from .base import number, toggle

STAGE_ID = "explain"
TITLE = "Explicabilité"
OBJECTIVE = "Comprendre les prédictions : importance globale (SHAP) et décomposition d'un cas (waterfall)."

_TREE_NAMES = ("DecisionTree", "RandomForest", "GradientBoosting", "XGB")
_LINEAR_NAMES = ("LinearRegression", "LogisticRegression", "Ridge", "Lasso")


def _is_tree(model) -> bool:
    return any(name in type(model).__name__ for name in _TREE_NAMES)


def _is_linear(model) -> bool:
    return any(type(model).__name__.startswith(name) for name in _LINEAR_NAMES)


def default_config(ctx):
    return {"sample_index": 0, "class_index": -1, "partial_dependence": True}


def config_schema(ctx):
    if ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return []
    controls = [number("sample_index", "Cas à expliquer (waterfall)", 0, 0, 100000,
                       "Indice de la ligne du jeu de test à décomposer.")]
    if ctx.problem_type == CLASSIFICATION:
        controls.append(number("class_index", "Classe expliquée (-1 = dernière)", -1, -1, 50,
                               "En multiclasse : indice de la classe dont on explique la "
                               "probabilité. -1 = dernière classe (positive en binaire)."))
    controls.append(toggle("partial_dependence", "Dépendance partielle (PDP)", True,
                           "Trace, pour les variables les plus influentes, la forme de l'effet "
                           "moyen sur la prédiction (1D) + une surface 2D pour la paire de tête "
                           "(révèle les interactions). Complète SHAP. En cas de doute, cliquez « IA »."))
    return controls


def diagnose(session):
    if session.ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return {"diagnostics": {"ready": False, "reason": "Explicabilité SHAP supervisée uniquement."}, "plots": []}
    model, origin = session.current_model()
    if model is None:
        return {"diagnostics": {"ready": False, "reason": "Entraînez un modèle d'abord."}, "plots": []}
    return {"diagnostics": {"ready": True, "model_origin": origin,
                            "shap_tree_supported": _is_tree(model),
                            "shap_linear_supported": _is_linear(model)}, "plots": []}


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

    if _is_tree(model):
        explainer_kind = "TreeExplainer"
    elif _is_linear(model):
        explainer_kind = "LinearExplainer"
    else:
        return ({
            "report": {"Modèle": origin, "SHAP": "non disponible"},
            "diagnostics": {"shap_supported": False},
            "log": ["Modèle non supporté par les explainers SHAP rapides."],
            "warnings": ["Choisissez un modèle à base d'arbres (RandomForest, Gradient Boosting, "
                         "XGBoost) ou linéaire (Linear/Ridge/Lasso/Logistic) pour l'explicabilité SHAP."],
            "plots": [message_plot("SHAP requiert un modèle à base d'arbres ou linéaire.")],
        }, {})

    try:
        if explainer_kind == "TreeExplainer":
            explainer = shap.TreeExplainer(model)
        else:
            explainer = shap.LinearExplainer(model, Xs)
        sv = explainer.shap_values(Xs)
    except Exception as e:
        return ({
            "report": {"SHAP": "erreur"}, "diagnostics": {"error": str(e)},
            "log": [f"SHAP a échoué : {e}"], "warnings": [],
            "plots": [message_plot("SHAP : " + str(e)[:120])],
        }, {})

    # Multiclass explainers return one array per class — pick the configured one.
    ci = int(cfg.get("class_index", -1))
    n_out = len(sv) if isinstance(sv, list) else (sv.shape[2] if getattr(sv, "ndim", 2) == 3 else 1)
    if ci < 0 or ci >= n_out:
        ci = n_out - 1
    sv_use = sv[ci] if isinstance(sv, list) else sv
    if isinstance(sv_use, np.ndarray) and sv_use.ndim == 3:
        sv_use = sv_use[:, :, ci]

    class_name = None
    if ctx.problem_type == CLASSIFICATION and n_out > 1:
        le = sep.artifacts.get("label_encoder")
        try:
            class_name = str(le.inverse_transform([ci])[0]) if le is not None else str(ci)
        except Exception:
            class_name = str(ci)

    plots = [_summary_plot(sv_use, Xs)]
    wf = _waterfall_plot(explainer, sv, Xs, int(cfg["sample_index"]), ci)
    if wf:
        plots.append(wf)

    mean_abs = np.abs(sv_use).mean(axis=0)
    order = np.argsort(mean_abs)[::-1][:8]
    top = [{"feature": str(Xs.columns[i]), "importance_shap": round(float(mean_abs[i]), 4)} for i in order]

    # Partial dependence: the SHAP-ranked top features drive the PDP selection, so
    # the analyst sees the SHAPE of the effect (1D) + the top pair's interaction (2D).
    if cfg.get("partial_dependence") and len(order):
        # In multiclass the PD output has one row per class → select the explained
        # class; binary / regression have a single output row (0).
        pdp_class = ci if (ctx.problem_type == CLASSIFICATION and n_out > 2) else 0
        plots += pdp.partial_dependence_plots(model, Xs, list(Xs.columns),
                                              [int(i) for i in order], ctx.problem_type, pdp_class)

    report = {"Modèle expliqué": origin, "Explainer": explainer_kind,
              "Variable la plus influente": top[0]["feature"] if top else "—"}
    if class_name is not None:
        report["Classe expliquée"] = class_name
    result = {
        "report": report,
        "diagnostics": {"shap_top_features": top, "model_origin": origin,
                        "explainer": explainer_kind, "explained_class": class_name},
        "log": [f"SHAP {explainer_kind} sur {len(Xs)} observations de test ({origin})."],
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


def _waterfall_plot(explainer, sv, Xs, idx, ci=-1) -> str:
    idx = max(0, min(idx, len(Xs) - 1))
    try:
        base = explainer.expected_value
        if isinstance(base, (list, np.ndarray)) and np.ndim(base) > 0:
            flat = np.ravel(base)
            base = flat[ci] if -len(flat) <= ci < len(flat) else flat[-1]
        row = sv[ci][idx] if isinstance(sv, list) else (sv[idx] if sv.ndim == 2 else sv[idx, :, ci])
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
