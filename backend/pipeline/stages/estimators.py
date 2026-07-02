"""
estimators.py — Shared supervised estimator factory + per-family hyperparameter grids.

Single source of truth for the candidate models compared on the Modelling
leaderboard AND tuned by the Fine-tuning stage, so the two stages can never
drift (an algorithm selectable in Modelling is always tunable in Fine-tuning).
"""

from sklearn.linear_model import (
    LinearRegression, LogisticRegression, Ridge, Lasso, ElasticNet,
)
from sklearn.tree import DecisionTreeRegressor, DecisionTreeClassifier
from sklearn.ensemble import (
    RandomForestRegressor, GradientBoostingRegressor,
    RandomForestClassifier, GradientBoostingClassifier,
)
from sklearn.svm import SVC, SVR
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.naive_bayes import GaussianNB

try:
    from xgboost import XGBRegressor, XGBClassifier
    HAS_XGB = True
except ImportError:  # XGBoost optional — degrade gracefully if absent.
    HAS_XGB = False

from ..context import REGRESSION

REG_ALGOS = [("LinearRegression", "Régression linéaire"), ("Ridge", "Ridge (L2)"),
             ("Lasso", "Lasso (L1)"), ("ElasticNet", "ElasticNet (L1+L2)"),
             ("KNN", "k plus proches voisins"), ("SVM", "Machine à vecteurs de support (SVM)"),
             ("DecisionTree", "Arbre de décision"),
             ("RandomForest", "Random Forest"), ("GradientBoosting", "Gradient Boosting")]
CLF_ALGOS = [("LogisticRegression", "Régression logistique"),
             ("NaiveBayes", "Naïve Bayes (gaussien)"),
             ("KNN", "k plus proches voisins"), ("SVM", "Machine à vecteurs de support (SVM)"),
             ("DecisionTree", "Arbre de décision"),
             ("RandomForest", "Random Forest"), ("GradientBoosting", "Gradient Boosting")]
if HAS_XGB:
    REG_ALGOS.append(("XGBoost", "XGBoost"))
    CLF_ALGOS.append(("XGBoost", "XGBoost"))

# Short, analyst-facing descriptions surfaced next to each algorithm choice and
# fed to the per-choice AI helper — so a non-expert understands the trade-off.
ALGO_HELP = {
    "LinearRegression": "Modèle linéaire simple et interprétable ; base de comparaison.",
    "Ridge": "Régression linéaire régularisée (L2) : réduit le surapprentissage quand les variables sont corrélées.",
    "Lasso": "Régression linéaire régularisée (L1) : met à zéro les variables inutiles (sélection automatique).",
    "ElasticNet": "Compromis Ridge + Lasso : régularise ET sélectionne ; utile quand beaucoup de variables corrélées.",
    "LogisticRegression": "Classifieur linéaire interprétable, probabilités calibrées ; bonne base.",
    "NaiveBayes": "Rapide, robuste en haute dimension ; suppose les variables indépendantes (approximation).",
    "KNN": "Prédit d'après les voisins les plus proches ; sans hypothèse de forme, mais sensible à l'échelle et lent à grande taille.",
    "SVM": "Frontière de décision à marge maximale ; puissant sur données bien mises à l'échelle, plus lent sur gros volumes.",
    "DecisionTree": "Arbre de règles lisible ; tend à surapprendre seul (à élaguer).",
    "RandomForest": "Forêt d'arbres : robuste et performant par défaut sur données tabulaires.",
    "GradientBoosting": "Arbres séquentiels : souvent le plus précis, mais plus sensible aux réglages.",
    "XGBoost": "Boosting optimisé : très performant, nombreux hyperparamètres à régler.",
}


def algo_options(ptype):
    """(value, label) pairs for the UI select, per problem type."""
    return REG_ALGOS if ptype == REGRESSION else CLF_ALGOS


def make_estimator(ptype, algo, n_estimators=100, max_depth=None, class_weight=None,
                   for_scoring=False):
    """Build one estimator with the expert's base hyperparameters.

    ``class_weight`` ("balanced" | None) applies to the classifiers that support
    it (Logistic / DecisionTree / RandomForest / SVM); the other families ignore it.
    ``for_scoring`` builds a cheaper SVM (no probability calibration) for the
    leaderboard cross-validation, where only class predictions are scored — the
    final chosen model is rebuilt with ``for_scoring=False`` so ``predict_proba``
    (ROC / PR / operational SOC view) works. Returns ``None`` for an unknown name.
    """
    if ptype == REGRESSION:
        table = {
            "LinearRegression": lambda: LinearRegression(),
            "Ridge": lambda: Ridge(random_state=42),
            "Lasso": lambda: Lasso(random_state=42),
            "ElasticNet": lambda: ElasticNet(random_state=42),
            "KNN": lambda: KNeighborsRegressor(n_neighbors=5),
            "SVM": lambda: SVR(),
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
            "NaiveBayes": lambda: GaussianNB(),
            "KNN": lambda: KNeighborsClassifier(n_neighbors=5),
            # probability=True so predict_proba works (ROC/PR + operational SOC view);
            # skipped for the leaderboard CV (for_scoring) where it isn't needed and is slow.
            "SVM": lambda: SVC(probability=not for_scoring, class_weight=cw, random_state=42),
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
    """The full leaderboard pool, keyed by algorithm name (cheap SVM for CV)."""
    out = {}
    for name, _label in algo_options(ptype):
        est = make_estimator(ptype, name, n_estimators, max_depth, class_weight, for_scoring=True)
        if est is not None:
            out[name] = est
    return out


# Cross-validated search spaces, one per family. Kept deliberately compact:
# a leaderboard-informed expert tunes ONE family, not the whole zoo.
PARAM_GRIDS = {
    "LinearRegression": {"fit_intercept": [True, False]},
    "Ridge": {"alpha": [0.1, 1.0, 10.0, 100.0]},
    "Lasso": {"alpha": [0.0005, 0.001, 0.01, 0.1, 1.0]},
    "ElasticNet": {"alpha": [0.001, 0.01, 0.1, 1.0], "l1_ratio": [0.1, 0.5, 0.9]},
    "LogisticRegression": {"C": [0.01, 0.1, 1.0, 10.0], "penalty": ["l2"]},
    "NaiveBayes": {"var_smoothing": [1e-11, 1e-9, 1e-7, 1e-5]},
    "KNN": {"n_neighbors": [3, 5, 11, 21], "weights": ["uniform", "distance"]},
    "SVM": {"C": [0.1, 1.0, 10.0], "kernel": ["rbf", "linear"], "gamma": ["scale", "auto"]},
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


def algo_help(algo):
    """Analyst-facing one-liner for an algorithm (for the AI helper / UI)."""
    return ALGO_HELP.get(algo, "")
