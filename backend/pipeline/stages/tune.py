"""
tune.py — Stage : FINE-TUNING (GridSearchCV).

Refines the chosen algorithm's hyperparameters by cross-validated grid search on
the training split, mirroring the J1 notebook's GridSearchCV step. The resulting
tuned model supersedes the baseline for Evaluation and Explicability
(``session.current_model()``). Supervised only.
"""

import numpy as np

from sklearn.model_selection import GridSearchCV
from sklearn.ensemble import (
    GradientBoostingRegressor, GradientBoostingClassifier,
    RandomForestRegressor, RandomForestClassifier,
)
from sklearn.metrics import r2_score, accuracy_score

from ..context import REGRESSION, CLASSIFICATION
from ..plotting import style_plot, fig_to_base64, message_plot
from .base import select, number

STAGE_ID = "tune"
TITLE = "Fine-tuning"
OBJECTIVE = "Recherche des hyperparamètres optimaux par validation croisée (GridSearchCV)."

_GRIDS = {
    "GradientBoosting": {"learning_rate": [0.01, 0.05, 0.1], "n_estimators": [50, 100, 200]},
    "RandomForest": {"n_estimators": [100, 200, 400], "max_depth": [None, 10, 20]},
}


def default_config(ctx):
    return {"algorithm": "GradientBoosting", "cv": 3}


def config_schema(ctx):
    if ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return []
    return [
        select("algorithm", "Algorithme à optimiser",
               [("GradientBoosting", "Gradient Boosting"), ("RandomForest", "Random Forest")],
               "GradientBoosting", "Grille d'hyperparamètres testée par validation croisée."),
        number("cv", "Plis de validation croisée (cv)", 3, 2, 10, "Nombre de folds."),
    ]


def diagnose(session):
    if session.ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return {"diagnostics": {"ready": False, "reason": "Fine-tuning supervisé uniquement (pas de clustering)."}, "plots": []}
    mrun = session.get_run("model")
    if mrun is None or mrun.stale:
        return {"diagnostics": {"ready": False, "reason": "Entraînez d'abord un modèle baseline."}, "plots": []}
    return {"diagnostics": {"ready": True, "baseline_algorithm": mrun.artifacts.get("algorithm")}, "plots": []}


def run(session, config):
    ctx = session.ctx
    if ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        raise ValueError("Le fine-tuning ne s'applique qu'à l'apprentissage supervisé.")
    sep = session.get_run("separate")
    if sep is None or sep.stale:
        raise ValueError("La séparation doit être exécutée avant le fine-tuning.")
    mrun = session.get_run("model")
    if mrun is None or mrun.stale:
        raise ValueError("Entraînez un modèle baseline avant le fine-tuning.")

    cfg = {**default_config(ctx), **(config or {})}
    art = sep.artifacts
    X_train, y_train = art["X_train"], art["y_train"]
    X_test, y_test = art["X_test"], art["y_test"]
    algo, cv = cfg["algorithm"], int(cfg["cv"])
    grid = _GRIDS.get(algo, _GRIDS["GradientBoosting"])

    if ctx.problem_type == REGRESSION:
        base = (GradientBoostingRegressor(random_state=42) if algo == "GradientBoosting"
                else RandomForestRegressor(random_state=42))
        scoring, scorer, label = "r2", r2_score, "R² (test)"
    else:
        base = (GradientBoostingClassifier(random_state=42) if algo == "GradientBoosting"
                else RandomForestClassifier(random_state=42))
        scoring, scorer, label = "accuracy", accuracy_score, "Accuracy (test)"

    gs = GridSearchCV(base, grid, scoring=scoring, cv=cv, n_jobs=-1)
    gs.fit(X_train, y_train)
    best = gs.best_estimator_

    tuned_score = round(float(scorer(y_test, best.predict(X_test))), 4)
    base_model = mrun.artifacts.get("model")
    base_score = round(float(scorer(y_test, base_model.predict(X_test))), 4) if base_model is not None else None
    gain = round(tuned_score - base_score, 4) if base_score is not None else None

    artifacts = {"model": best, "algorithm": f"{algo} (tuned)", "best_params": dict(gs.best_params_)}
    plots = [_cv_plot(gs)]
    result = {
        "report": {
            "Algorithme": algo,
            "Meilleurs paramètres": ", ".join(f"{k}={v}" for k, v in gs.best_params_.items()),
            label: tuned_score,
            "Baseline": base_score if base_score is not None else "—",
            "Gain": (f"+{gain}" if (gain is not None and gain >= 0) else gain),
        },
        "diagnostics": {"best_params": dict(gs.best_params_), "tuned_score": tuned_score,
                        "baseline_score": base_score, "cv": cv, "scoring": scoring},
        "log": [f"GridSearchCV {algo} ({cv} plis) : meilleurs params {dict(gs.best_params_)}.",
                f"{label} : baseline {base_score} → tuned {tuned_score}."],
        "warnings": ([] if (gain is None or gain >= 0)
                     else ["Le modèle tuné ne dépasse pas la baseline sur le test (sur-ajustement de la grille ?)."]),
        "plots": plots,
    }
    return result, artifacts


def _cv_plot(gs):
    import matplotlib.pyplot as plt
    style_plot()
    means = gs.cv_results_["mean_test_score"]
    params = gs.cv_results_["params"]
    order = np.argsort(means)[::-1][:10]
    labels = [", ".join(f"{k}={v}" for k, v in params[i].items()) for i in order]
    fig, ax = plt.subplots(figsize=(8, max(2.6, 0.4 * len(order) + 1)))
    best_idx = int(np.argmax(means))
    colors = ["#e94560" if i == best_idx else "#0f3460" for i in order]
    ax.barh(labels[::-1], [means[i] for i in order][::-1], color=colors[::-1], edgecolor="#eee")
    ax.set_title("Score CV par combinaison d'hyperparamètres (top 10)")
    ax.set_xlabel(gs.scoring)
    fig.tight_layout()
    return fig_to_base64(fig)
