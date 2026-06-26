"""
model.py — Stage 5 : MODELISATION.

Consumes the split artefacts produced by the Separation stage and fits a model.
Unlike the data stages, ``run`` operates on the *session* (it needs the split
arrays / full matrix), not on a dataframe.
"""

import numpy as np

from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.tree import DecisionTreeRegressor, DecisionTreeClassifier
from sklearn.ensemble import (
    RandomForestRegressor, GradientBoostingRegressor,
    RandomForestClassifier, GradientBoostingClassifier, IsolationForest,
)
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.neighbors import NearestNeighbors, LocalOutlierFactor
from sklearn.metrics import r2_score, accuracy_score, f1_score, root_mean_squared_error

try:
    from xgboost import XGBRegressor, XGBClassifier
    _HAS_XGB = True
except ImportError:  # XGBoost optional — degrade gracefully if absent.
    _HAS_XGB = False

from ..context import REGRESSION, CLASSIFICATION, CLUSTERING, ANOMALY
from ..plotting import style_plot, fig_to_base64, message_plot
from .base import select, rng, number

STAGE_ID = "model"
TITLE = "Modélisation"
OBJECTIVE = "Entraîner le modèle sur le jeu d'entraînement avec les hyperparamètres choisis."

_REG_ALGOS = [("LinearRegression", "Régression linéaire"), ("DecisionTree", "Arbre de décision"),
              ("RandomForest", "Random Forest"), ("GradientBoosting", "Gradient Boosting")]
_CLF_ALGOS = [("LogisticRegression", "Régression logistique"), ("DecisionTree", "Arbre de décision"),
              ("RandomForest", "Random Forest"), ("GradientBoosting", "Gradient Boosting")]
if _HAS_XGB:
    _REG_ALGOS.append(("XGBoost", "XGBoost"))
    _CLF_ALGOS.append(("XGBoost", "XGBoost"))


def _candidate_models(ptype, n_est, max_depth):
    """The pool of models compared on the leaderboard and selectable by the expert."""
    if ptype == REGRESSION:
        models = {
            "LinearRegression": LinearRegression(),
            "DecisionTree": DecisionTreeRegressor(max_depth=max_depth, random_state=42),
            "RandomForest": RandomForestRegressor(n_estimators=n_est, max_depth=max_depth, random_state=42),
            "GradientBoosting": GradientBoostingRegressor(n_estimators=n_est,
                                                          max_depth=max_depth or 3, random_state=42),
        }
        if _HAS_XGB:
            models["XGBoost"] = XGBRegressor(n_estimators=n_est, learning_rate=0.05,
                                             max_depth=max_depth or 6, random_state=42)
    else:
        models = {
            "LogisticRegression": LogisticRegression(max_iter=1000, random_state=42),
            "DecisionTree": DecisionTreeClassifier(max_depth=max_depth, random_state=42),
            "RandomForest": RandomForestClassifier(n_estimators=n_est, max_depth=max_depth, random_state=42),
            "GradientBoosting": GradientBoostingClassifier(n_estimators=n_est,
                                                           max_depth=max_depth or 3, random_state=42),
        }
        if _HAS_XGB:
            models["XGBoost"] = XGBClassifier(n_estimators=n_est, learning_rate=0.05,
                                              max_depth=max_depth or 6, random_state=42)
    return models


def default_config(ctx):
    if ctx.problem_type == REGRESSION:
        algo = "RandomForest"
    elif ctx.problem_type == CLASSIFICATION:
        algo = "RandomForest"
    else:
        algo = "KMeans"
    return {"algorithm": algo, "n_estimators": 100, "max_depth": 0, "n_clusters": 0,
            "cluster_algo": "kmeans", "eps": 0.5, "min_samples": 5,
            "anomaly_algo": "iforest", "contamination": 0.05}


def config_schema(ctx):
    if ctx.problem_type == REGRESSION:
        algos = _REG_ALGOS
    elif ctx.problem_type == CLASSIFICATION:
        algos = _CLF_ALGOS
    elif ctx.problem_type == ANOMALY:
        return [
            select("anomaly_algo", "Détecteur d'anomalies",
                   [("iforest", "Isolation Forest"), ("lof", "Local Outlier Factor")], "iforest",
                   "Isolation Forest isole les points rares ; LOF compare la densité locale."),
            rng("contamination", "Taux d'anomalies attendu", 0.01, 0.3, 0.01, 0.05,
                "Proportion de points traités comme anomalies."),
        ]
    else:
        return [
            select("cluster_algo", "Algorithme de clustering",
                   [("kmeans", "KMeans"), ("agglomerative", "Agglomératif (hiérarchique)"),
                    ("dbscan", "DBSCAN (densité)")], "kmeans",
                   "KMeans / Agglomératif : partition en K groupes. DBSCAN : densité, K auto + détection de bruit."),
            number("n_clusters", "Nombre de clusters K (0 = auto)", 0, 0, 15,
                   "KMeans / Agglomératif. 0 estime K par la méthode du coude."),
            rng("eps", "DBSCAN — rayon eps", 0.1, 3.0, 0.1, 0.5,
                "Rayon de voisinage DBSCAN (voir le graphe k-distance pour le calibrer)."),
            number("min_samples", "DBSCAN — points minimum", 5, 2, 50,
                   "Points minimum pour former un cœur de densité (DBSCAN)."),
        ]
    return [
        select("algorithm", "Algorithme", algos, "RandomForest", "Modèle entraîné."),
        rng("n_estimators", "Nombre d'arbres", 10, 500, 10, 100, "Pour Random Forest / Gradient Boosting."),
        number("max_depth", "Profondeur max (0 = illimité)", 0, 0, 40, "Limite la profondeur des arbres."),
    ]


def _leaderboard(art, ptype, n_est, max_depth):
    """Fit every candidate model on train, score on the held-out test set, rank them.

    The expert reads RMSE/R² (or Accuracy/F1) per model and picks the best
    family before fine-tuning.
    """
    X_tr, y_tr, X_te, y_te = art["X_train"], art["y_train"], art["X_test"], art["y_test"]
    rows = []
    for name, est in _candidate_models(ptype, n_est, max_depth).items():
        try:
            est.fit(X_tr, y_tr)
            pred_te, pred_tr = est.predict(X_te), est.predict(X_tr)
            if ptype == REGRESSION:
                r2_te, r2_tr = float(r2_score(y_te, pred_te)), float(r2_score(y_tr, pred_tr))
                rows.append({"model": name, "rmse_test": round(float(root_mean_squared_error(y_te, pred_te)), 3),
                             "r2_test": round(r2_te, 4), "r2_train": round(r2_tr, 4),
                             "overfit": round(r2_tr - r2_te, 4)})
            else:
                acc_te, acc_tr = float(accuracy_score(y_te, pred_te)), float(accuracy_score(y_tr, pred_tr))
                rows.append({"model": name, "accuracy_test": round(acc_te, 4),
                             "f1_test": round(float(f1_score(y_te, pred_te, average="weighted")), 4),
                             "accuracy_train": round(acc_tr, 4), "overfit": round(acc_tr - acc_te, 4)})
        except Exception:
            continue
    if ptype == REGRESSION:
        rows.sort(key=lambda r: r["rmse_test"])           # lower RMSE is better
    else:
        rows.sort(key=lambda r: r["accuracy_test"], reverse=True)
    best = rows[0]["model"] if rows else None
    for r in rows:
        r["recommended"] = (r["model"] == best)
    return rows, best


def diagnose(session):
    sep = session.get_run("separate")
    if sep is None or sep.stale:
        return {"diagnostics": {"ready": False, "reason": "La séparation doit être exécutée d'abord."}, "plots": []}
    art = sep.artifacts
    if art.get("mode") == "unsupervised":
        X = art["X_full"]
        if session.ctx.problem_type == ANOMALY:
            return _diagnose_anomaly(X, art)
        ks, inertias = _inertia_curve(X)
        k_reco = _knee_k(ks, inertias) if inertias else 3
        info = {"ready": True, "mode": "clustering", "n_samples": int(len(X)),
                "n_features": len(art["feature_names"]), "k_recommande": k_reco,
                "algos": ["kmeans", "agglomerative", "dbscan"]}
        plots = []
        if inertias:
            plots.append(_elbow_plot(ks, inertias, k_reco))  # KMeans / Agglomératif
        plots.append(_kdistance_plot(X, 5))                  # aide au choix de eps (DBSCAN)
        return {"diagnostics": info, "plots": plots}

    ptype = session.ctx.problem_type
    cfg = default_config(session.ctx)
    rows, best = _leaderboard(art, ptype, int(cfg["n_estimators"]), int(cfg["max_depth"]) or None)
    info = {"ready": True, "mode": "supervised", "train_size": int(len(art["X_train"])),
            "n_features": len(art["feature_names"]), "leaderboard": rows, "recommended_model": best,
            "primary_metric": "RMSE (test)" if ptype == REGRESSION else "Accuracy (test)"}
    plots = [_leaderboard_plot(rows, ptype)] if rows else []
    return {"diagnostics": info, "plots": plots}


def run(session, config):
    sep = session.get_run("separate")
    if sep is None or sep.stale:
        raise ValueError("La séparation doit être exécutée (ou rejouée) avant la modélisation.")
    cfg = {**default_config(session.ctx), **(config or {})}
    art = sep.artifacts
    ptype = session.ctx.problem_type
    max_depth = int(cfg["max_depth"]) or None
    n_est = int(cfg["n_estimators"])

    if ptype == ANOMALY:
        return _fit_anomaly(session, art, cfg)
    if art.get("mode") == "unsupervised" or ptype == CLUSTERING:
        return _fit_clustering(session, art, cfg)

    X_train, y_train = art["X_train"], art["y_train"]
    algo = cfg["algorithm"]
    choices = _candidate_models(ptype, n_est, max_depth)
    model = choices.get(algo)
    if model is None:  # unknown algorithm name → safe default (don't rely on estimator truthiness)
        fallback = RandomForestRegressor if ptype == REGRESSION else RandomForestClassifier
        model = fallback(n_estimators=n_est, random_state=42)

    model.fit(X_train, y_train)
    train_pred = model.predict(X_train)
    if ptype == REGRESSION:
        train_score = round(float(r2_score(y_train, train_pred)), 4)
        score_label = "R² (train)"
    else:
        train_score = round(float(accuracy_score(y_train, train_pred)), 4)
        score_label = "Accuracy (train)"

    artifacts = {"model": model, "algorithm": algo}
    result = {
        "report": {"Algorithme": algo, "n_estimators": n_est if "Forest" in algo or "Boosting" in algo else "—",
                   "max_depth": max_depth or "illimité", score_label: train_score},
        "diagnostics": {"algorithm": algo, "train_score": train_score, "score_label": score_label},
        "log": [f"Modèle {algo} entraîné sur {len(X_train)} observations."],
        "warnings": ["Score d'entraînement uniquement — voir l'Évaluation pour la performance sur test."],
        "plots": [_importance_plot(model, art["feature_names"])],
    }
    return result, artifacts


def _fit_clustering(session, art, cfg):
    X = art["X_full"]
    algo = str(cfg.get("cluster_algo", "kmeans")).lower()

    if algo == "dbscan":
        eps = float(cfg.get("eps", 0.5))
        min_samples = int(cfg.get("min_samples", 5))
        model = DBSCAN(eps=eps, min_samples=min_samples)
        labels = model.fit_predict(X)
        n_noise = int((labels == -1).sum())
        n_found = int(len(set(labels)) - (1 if -1 in labels else 0))
        artifacts = {"model": model, "algorithm": "DBSCAN", "labels": labels, "k": n_found}
        result = {
            "report": {"Algorithme": "DBSCAN", "Clusters trouvés": n_found, "Points bruit": n_noise,
                       "eps": eps, "min_samples": min_samples, "Observations": int(len(X))},
            "diagnostics": {"algorithm": "DBSCAN", "k": n_found, "n_noise": n_noise},
            "log": [f"DBSCAN (eps={eps}, min_samples={min_samples}) : {n_found} clusters, "
                    f"{n_noise} points de bruit (label -1).",
                    "Lecture des clusters → voir l'Évaluation."],
            "warnings": (["DBSCAN n'a trouvé aucun cluster dense — ajuster eps / min_samples."]
                         if n_found == 0 else []),
            "plots": [_kdistance_plot(X, min_samples)],
        }
        return result, artifacts

    # KMeans / Agglomératif : partition en K groupes (K auto par la méthode du coude).
    ks, inertias = _inertia_curve(X)
    k = int(cfg.get("n_clusters", 0))
    if k <= 0:
        k = _knee_k(ks, inertias) if inertias else 3
    if algo == "agglomerative":
        model = AgglomerativeClustering(n_clusters=k)
        name = "Agglomératif (hiérarchique)"
    else:
        model = KMeans(n_clusters=k, n_init=10, random_state=42)
        name = "KMeans"
    labels = model.fit_predict(X)
    artifacts = {"model": model, "algorithm": name, "labels": labels, "k": k}
    result = {
        "report": {"Algorithme": name, "Clusters (K)": k, "Observations": int(len(X))},
        "diagnostics": {"algorithm": name, "k": k},
        "log": [f"{name} entraîné avec K={k} sur {len(X)} observations.",
                "Lecture métier des clusters → voir l'Évaluation (profils + projection PCA)."],
        "warnings": [],
        "plots": [_elbow_plot(ks, inertias, k)] if inertias else [message_plot(f"{name} K={k}.")],
    }
    return result, artifacts


def _kdistance_plot(X, min_samples):
    """k-distance plot: sorted distance to the k-th nearest neighbour — the 'elbow'
    of this curve is a good eps for DBSCAN (Ester et al., 1996)."""
    import matplotlib.pyplot as plt
    style_plot()
    k = max(2, int(min_samples))
    n = len(X)
    if n <= k:
        return message_plot("Trop peu d'observations pour le graphe k-distance.")
    nn = NearestNeighbors(n_neighbors=k).fit(X)
    dist, _ = nn.kneighbors(X)
    kth = np.sort(dist[:, -1])
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(range(n), kth, color="#e94560")
    ax.set_xlabel("Points triés")
    ax.set_ylabel(f"Distance au {k}e voisin")
    ax.set_title("Graphe k-distance — calibrer eps (DBSCAN)")
    fig.tight_layout()
    return fig_to_base64(fig)


def _diagnose_anomaly(X, art):
    """Pre-run view for anomaly detection: no elbow/silhouette, just the setup."""
    info = {"ready": True, "mode": "anomaly", "n_samples": int(len(X)),
            "n_features": len(art["feature_names"]), "algos": ["iforest", "lof"]}
    msg = message_plot("Détection d'anomalies : choisir un détecteur et le taux attendu, puis lancer.")
    return {"diagnostics": info, "plots": [msg]}


def _fit_anomaly(session, art, cfg):
    """Unsupervised outlier detection (Isolation Forest / LOF) on the full matrix."""
    X = art["X_full"]
    algo = str(cfg.get("anomaly_algo", "iforest")).lower()
    contamination = min(max(float(cfg.get("contamination", 0.05)), 0.001), 0.5)
    if algo == "lof":
        model = LocalOutlierFactor(n_neighbors=20, contamination=contamination)
        preds = model.fit_predict(X)                 # -1 = anomaly, 1 = normal
        scores = np.asarray(model.negative_outlier_factor_)  # lower = more abnormal
        name = "Local Outlier Factor"
    else:
        model = IsolationForest(n_estimators=200, contamination=contamination, random_state=42)
        preds = model.fit_predict(X)
        scores = np.asarray(model.decision_function(X))      # lower = more abnormal
        name = "Isolation Forest"
    preds = np.asarray(preds)
    n_anom = int((preds == -1).sum())
    rate = 100.0 * n_anom / max(1, len(X))
    artifacts = {"model": model, "algorithm": name, "predictions": preds,
                 "scores": scores, "contamination": contamination}
    result = {
        "report": {"Détecteur": name, "Anomalies": n_anom, "Normaux": int((preds == 1).sum()),
                   "Taux d'anomalies": f"{rate:.1f}%", "Observations": int(len(X))},
        "diagnostics": {"algorithm": name, "n_anomalies": n_anom, "contamination": contamination},
        "log": [f"{name} : {n_anom} anomalies sur {len(X)} observations (contamination={contamination}).",
                "Lecture des anomalies → voir l'Évaluation (scores, projection PCA, top anomalies)."],
        "warnings": [],
        "plots": [message_plot(name + " entraîné — voir l'Évaluation pour les scores et la projection.")],
    }
    return result, artifacts


def _inertia_curve(X):
    """Within-cluster inertia for K=2..10 (the elbow-method curve)."""
    ks = list(range(2, min(11, len(X))))
    inertias = [float(KMeans(n_clusters=k, n_init=10, random_state=42).fit(X).inertia_) for k in ks]
    return ks, inertias


def _knee_k(ks, inertias):
    if len(inertias) < 2:
        return 3
    drops = [inertias[i] - inertias[i + 1] for i in range(len(inertias) - 1)]
    return min(ks[int(np.argmax(drops))] + 1, 6)


def _estimate_k(X):
    ks, inertias = _inertia_curve(X)
    return _knee_k(ks, inertias) if inertias else 3


def _elbow_plot(ks, inertias, k):
    import matplotlib.pyplot as plt
    style_plot()
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(ks, inertias, "-o", color="#e94560", markeredgecolor="#0f3460")
    if k in ks:
        ax.axvline(k, color="#16c79a", ls="--", lw=1.5)
        ax.annotate(f"K choisi = {k}", (k, inertias[ks.index(k)]), color="#16c79a",
                    xytext=(6, 6), textcoords="offset points", fontsize=9)
    ax.set_xlabel("Nombre de clusters K")
    ax.set_ylabel("Inertie intra-cluster")
    ax.set_title("Méthode du coude — choix de K")
    fig.tight_layout()
    return fig_to_base64(fig)


def _leaderboard_plot(rows, ptype):
    """Bar chart comparing the test performance of every candidate model."""
    import matplotlib.pyplot as plt
    style_plot()
    if not rows:
        return message_plot("Pas de modèle à comparer.")
    metric_key = "r2_test" if ptype == REGRESSION else "accuracy_test"
    title = "R² (test) par modèle" if ptype == REGRESSION else "Accuracy (test) par modèle"
    names = [r["model"] for r in rows][::-1]
    vals = [r[metric_key] for r in rows][::-1]
    colors = ["#16c79a" if r["recommended"] else "#0f3460" for r in rows][::-1]
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.45 * len(names) + 1)))
    ax.barh(names, vals, color=colors, edgecolor="#e94560")
    ax.set_title(title)
    ax.set_xlabel(metric_key)
    fig.tight_layout()
    return fig_to_base64(fig)


def _importance_plot(model, feature_names):
    import matplotlib.pyplot as plt
    style_plot()
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        coef = getattr(model, "coef_", None)
        if coef is not None:
            importances = np.abs(np.ravel(coef))
    if importances is None or len(importances) != len(feature_names):
        return message_plot("Pas d'importance de variables pour ce modèle (voir Évaluation).")
    order = np.argsort(importances)[-12:]
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.35 * len(order) + 1)))
    ax.barh([feature_names[i] for i in order], [importances[i] for i in order],
            color="#e94560", edgecolor="#0f3460")
    ax.set_title("Importance des variables (top 12)")
    fig.tight_layout()
    return fig_to_base64(fig)
