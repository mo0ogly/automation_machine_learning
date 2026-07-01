"""
tune.py — Stage : FINE-TUNING (recherche d'hyperparamètres par validation croisée).

Refines the hyperparameters of the algorithm the expert actually chose at the
Modelling stage (any supervised family: linear, tree, forest, boosting, XGBoost)
by cross-validated search on the TRAIN split — grid or randomised. The held-out
test set is never consulted here: the tuned-vs-baseline comparison uses the
cross-validation score (and the validation carve-out when one exists), keeping
the test set virgin for the Evaluation stage. The resulting tuned model
supersedes the baseline for Evaluation and Explicability
(``session.current_model()``). Supervised only.
"""

import numpy as np

from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, cross_val_score
from sklearn.metrics import r2_score, accuracy_score

from ..context import REGRESSION, CLASSIFICATION
from ..plotting import style_plot, fig_to_base64
from . import estimators as est_factory
from .base import select, number

STAGE_ID = "tune"
TITLE = "Fine-tuning"
OBJECTIVE = "Recherche des hyperparamètres optimaux par validation croisée (grille ou aléatoire)."

_AUTO = ""  # sentinel: tune the algorithm chosen at the Modelling stage


def default_config(ctx):
    return {"algorithm": _AUTO, "cv": 3, "search": "grid", "n_iter": 20}


def config_schema(ctx):
    if ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return []
    algos = [(_AUTO, "Auto — algorithme du baseline")] + list(est_factory.algo_options(ctx.problem_type))
    return [
        select("algorithm", "Algorithme à optimiser", algos, _AUTO,
               "Par défaut, l'algorithme entraîné à l'étape Modélisation. Chaque famille a sa "
               "propre grille d'hyperparamètres."),
        select("search", "Stratégie de recherche",
               [("grid", "Grille exhaustive (GridSearchCV)"),
                ("random", "Aléatoire (RandomizedSearchCV)")], "grid",
               "La recherche aléatoire échantillonne n_iter combinaisons — plus rapide sur les grandes grilles."),
        number("n_iter", "Combinaisons testées (recherche aléatoire)", 20, 5, 200,
               "Utilisé uniquement par la recherche aléatoire."),
        number("cv", "Plis de validation croisée (cv)", 3, 2, 10, "Nombre de folds."),
    ]


def diagnose(session):
    if session.ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return {"diagnostics": {"ready": False, "reason": "Fine-tuning supervisé uniquement (pas de clustering)."}, "plots": []}
    mrun = session.get_run("model")
    if mrun is None or mrun.stale:
        return {"diagnostics": {"ready": False, "reason": "Entraînez d'abord un modèle baseline."}, "plots": []}
    baseline = mrun.artifacts.get("algorithm")
    return {"diagnostics": {"ready": True, "baseline_algorithm": baseline,
                            "grid": est_factory.param_grid(baseline) if baseline else None,
                            "tunable": list(est_factory.PARAM_GRIDS.keys())}, "plots": []}


def _grid_size(grid) -> int:
    size = 1
    for values in grid.values():
        size *= max(1, len(values))
    return size


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
    cv = int(cfg["cv"])

    # Resolve the family: the expert's explicit choice, else the Modelling baseline.
    baseline_algo = str(mrun.artifacts.get("algorithm") or "")
    algo = str(cfg.get("algorithm") or "").strip() or baseline_algo
    base = est_factory.make_estimator(ctx.problem_type, algo)
    if base is None:
        raise ValueError(f"Algorithme « {algo} » inconnu du fine-tuning. "
                         f"Familles disponibles : {', '.join(est_factory.PARAM_GRIDS)}.")
    grid = est_factory.param_grid(algo)

    if ctx.problem_type == REGRESSION:
        scoring, scorer, label = "r2", r2_score, "R²"
    else:
        scoring, scorer, label = "accuracy", accuracy_score, "Accuracy"

    search_kind = str(cfg.get("search", "grid"))
    if search_kind == "random" and _grid_size(grid) > int(cfg["n_iter"]):
        gs = RandomizedSearchCV(base, grid, n_iter=int(cfg["n_iter"]), scoring=scoring,
                                cv=cv, n_jobs=-1, random_state=42)
        search_label = f"aléatoire ({int(cfg['n_iter'])} tirages)"
    else:
        gs = GridSearchCV(base, grid, scoring=scoring, cv=cv, n_jobs=-1)
        search_label = f"grille exhaustive ({_grid_size(grid)} combinaisons)"
    gs.fit(X_train, y_train)
    best = gs.best_estimator_
    tuned_cv = round(float(gs.best_score_), 4)

    # Baseline comparison on the SAME folds — the test set is never consulted here.
    base_model = mrun.artifacts.get("model")
    base_cv = None
    if base_model is not None:
        try:
            base_cv = round(float(cross_val_score(base_model, X_train, y_train,
                                                  cv=cv, scoring=scoring, n_jobs=-1).mean()), 4)
        except Exception:
            base_cv = None
    gain = round(tuned_cv - base_cv, 4) if base_cv is not None else None

    # Validation carve-out (if the expert reserved one at Separation): an untouched
    # comparison set that is neither in the CV folds nor the final test set.
    val_scores = None
    if art.get("X_val") is not None and art.get("y_val") is not None:
        X_val, y_val = art["X_val"], art["y_val"]
        try:
            val_scores = {
                "tuned": round(float(scorer(y_val, best.predict(X_val))), 4),
                "baseline": (round(float(scorer(y_val, base_model.predict(X_val))), 4)
                             if base_model is not None else None),
            }
        except Exception:
            val_scores = None

    artifacts = {"model": best, "algorithm": f"{algo} (tuned)", "best_params": dict(gs.best_params_)}
    report = {
        "Algorithme": algo + (" (baseline)" if algo == baseline_algo else ""),
        "Recherche": search_label,
        "Meilleurs paramètres": ", ".join(f"{k}={v}" for k, v in gs.best_params_.items()),
        f"{label} (CV {cv} plis)": tuned_cv,
        "Baseline (CV)": base_cv if base_cv is not None else "—",
        "Gain (CV)": (f"+{gain}" if (gain is not None and gain >= 0) else gain),
    }
    if val_scores is not None:
        report[f"{label} (validation)"] = (f"{val_scores['tuned']} (baseline "
                                           f"{val_scores['baseline']})")
    log = [f"Recherche {search_label} sur {algo} ({cv} plis) : meilleurs params {dict(gs.best_params_)}.",
           f"{label} CV : baseline {base_cv} → tuned {tuned_cv}.",
           "Le jeu de test n'a pas été utilisé — verdict final à l'étape Évaluation."]
    diagnostics = {"best_params": dict(gs.best_params_), "tuned_score": tuned_cv,
                   "baseline_score": base_cv, "cv": cv, "scoring": scoring,
                   "search": search_kind, "algorithm": algo, "validation_scores": val_scores}
    result = {
        "report": report,
        "diagnostics": diagnostics,
        "log": log,
        "warnings": ([] if (gain is None or gain >= 0)
                     else ["Le modèle tuné ne dépasse pas la baseline en validation croisée "
                           "(grille inadaptée ou baseline déjà optimale ?)."]),
        "plots": [_cv_plot(gs)],
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
    ax.set_xlabel(str(gs.scoring))
    fig.tight_layout()
    return fig_to_base64(fig)
