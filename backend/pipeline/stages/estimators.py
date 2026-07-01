"""
estimators.py — Shared supervised estimator factory + per-family hyperparameter grids.

Single source of truth for the candidate models compared on the Modelling
leaderboard AND tuned by the Fine-tuning stage, so the two stages can never
drift (an algorithm selectable in Modelling is always tunable in Fine-tuning).
"""

from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge, Lasso
from sklearn.tree import DecisionTreeRegressor, DecisionTreeClassifier
from sklearn.ensemble import (
    RandomForestRegressor, GradientBoostingRegressor,
    RandomForestClassifier, GradientBoostingClassifier,
)

try:
    from xgboost import XGBRegressor, XGBClassifier
    HAS_XGB = True
except ImportError:  # XGBoost optional — degrade gracefully if absent.
    HAS_XGB = False

from ..context import REGRESSION

REG_ALGOS = [("LinearRegression", "Régression linéaire"), ("Ridge", "Ridge (L2)"),
             ("Lasso", "Lasso (L1)"), ("DecisionTree", "Arbre de décision"),
             ("RandomForest", "Random Forest"), ("GradientBoosting", "Gradient Boosting")]
CLF_ALGOS = [("LogisticRegression", "Régression logistique"), ("DecisionTree", "Arbre de décision"),
             ("RandomForest", "Random Forest"), ("GradientBoosting", "Gradient Boosting")]
if HAS_XGB:
    REG_ALGOS.append(("XGBoost", "XGBoost"))
    CLF_ALGOS.append(("XGBoost", "XGBoost"))


def algo_options(ptype):
    """(value, label) pairs for the UI select, per problem type."""
    return REG_ALGOS if ptype == REGRESSION else CLF_ALGOS


def make_estimator(ptype, algo, n_estimators=100, max_depth=None, class_weight=None):
    """Build one estimator with the expert's base hyperparameters.

    ``class_weight`` ("balanced" | None) applies to the classifiers that support
    it (Logistic / DecisionTree / RandomForest); the boosting families ignore it.
    Returns ``None`` for an unknown algorithm name.
    """
    if ptype == REGRESSION:
        table = {
            "LinearRegression": lambda: LinearRegression(),
            "Ridge": lambda: Ridge(random_state=42),
            "Lasso": lambda: Lasso(random_state=42),
            "DecisionTree": lambda: DecisionTreeRegressor(max_depth=max_depth, random_state=42),
            "RandomForest": lambda: RandomForestRegressor(
                n_estimators=n_estimators, max_depth=max_depth, random_state=42),
            "GradientBoosting": lambda: GradientBoostingRegressor(
                n_estimators=n_estimators, max_depth=max_depth or 3, random_state=42),
        }
        if HAS_XGB:
            table["XGBoost"] = lambda: XGBRegressor(
                n_estimators=n_estimators, learning_rate=0.05,
                max_depth=max_depth or 6, random_state=42)
    else:
        cw = class_weight if class_weight in ("balanced",) else None
        table = {
            "LogisticRegression": lambda: LogisticRegression(
                max_iter=1000, class_weight=cw, random_state=42),
            "DecisionTree": lambda: DecisionTreeClassifier(
                max_depth=max_depth, class_weight=cw, random_state=42),
            "RandomForest": lambda: RandomForestClassifier(
                n_estimators=n_estimators, max_depth=max_depth, class_weight=cw, random_state=42),
            "GradientBoosting": lambda: GradientBoostingClassifier(
                n_estimators=n_estimators, max_depth=max_depth or 3, random_state=42),
        }
        if HAS_XGB:
            table["XGBoost"] = lambda: XGBClassifier(
                n_estimators=n_estimators, learning_rate=0.05,
                max_depth=max_depth or 6, random_state=42)
    build = table.get(algo)
    return build() if build else None


def candidate_models(ptype, n_estimators=100, max_depth=None, class_weight=None):
    """The full leaderboard pool, keyed by algorithm name."""
    out = {}
    for name, _label in algo_options(ptype):
        est = make_estimator(ptype, name, n_estimators, max_depth, class_weight)
        if est is not None:
            out[name] = est
    return out


# Cross-validated search spaces, one per family. Kept deliberately compact:
# a leaderboard-informed expert tunes ONE family, not the whole zoo.
PARAM_GRIDS = {
    "LinearRegression": {"fit_intercept": [True, False]},
    "Ridge": {"alpha": [0.1, 1.0, 10.0, 100.0]},
    "Lasso": {"alpha": [0.0005, 0.001, 0.01, 0.1, 1.0]},
    "LogisticRegression": {"C": [0.01, 0.1, 1.0, 10.0], "penalty": ["l2"]},
    "DecisionTree": {"max_depth": [None, 5, 10, 20], "min_samples_split": [2, 10, 30],
                     "min_samples_leaf": [1, 5, 15]},
    "RandomForest": {"n_estimators": [100, 200, 400], "max_depth": [None, 10, 20],
                     "min_samples_leaf": [1, 3, 8]},
    "GradientBoosting": {"learning_rate": [0.01, 0.05, 0.1], "n_estimators": [50, 100, 200],
                         "max_depth": [2, 3, 4]},
    "XGBoost": {"learning_rate": [0.01, 0.05, 0.1], "n_estimators": [100, 200, 400],
                "max_depth": [3, 6, 9], "subsample": [0.8, 1.0]},
}


def param_grid(algo):
    return dict(PARAM_GRIDS.get(algo, PARAM_GRIDS["GradientBoosting"]))
