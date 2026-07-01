"""
model.py — Stage 5 : MODELISATION.

Consumes the split artefacts produced by the Separation stage and fits a model.
Unlike the data stages, ``run`` operates on the *session* (it needs the split
arrays / full matrix), not on a dataframe.
"""

import numpy as np

from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier, IsolationForest
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.neighbors import NearestNeighbors, LocalOutlierFactor
from sklearn.model_selection import cross_validate
from sklearn.metrics import r2_score, accuracy_score

from ..context import REGRESSION, CLASSIFICATION, CLUSTERING, ANOMALY
from ..plotting import style_plot, fig_to_base64, message_plot
from . import estimators as est_factory
from .base import select, toggle, rng, number

STAGE_ID = "model"
TITLE = "Modélisation"
OBJECTIVE = "Entraîner le modèle sur le jeu d'entraînement avec les hyperparamètres choisis."


def default_config(ctx):
    if ctx.problem_type == REGRESSION:
        algo = "RandomForest"
    elif ctx.problem_type == CLASSIFICATION:
        algo = "RandomForest"
    else:
        algo = "KMeans"
    return {"algorithm": algo, "n_estimators": 100, "max_depth": 0, "n_clusters": 0,
            "cluster_algo": "kmeans", "eps": 0.5, "min_samples": 5,
            "anomaly_algo": "iforest", "contamination": 0.05,
            "class_weight_balanced": False}


def config_schema(ctx):
    if ctx.problem_type in (REGRESSION, CLASSIFICATION):
        algos = est_factory.algo_options(ctx.problem_type)
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
    controls = [
        select("algorithm", "Algorithme", algos, "RandomForest", "Modèle entraîné."),
        rng("n_estimators", "Nombre d'arbres", 10, 500, 10, 100, "Pour Random Forest / Gradient Boosting."),
        number("max_depth", "Profondeur max (0 = illimité)", 0, 0, 40, "Limite la profondeur des arbres."),
    ]
    if ctx.problem_type == CLASSIFICATION:
        controls.append(toggle(
            "class_weight_balanced", "Pondérer les classes (déséquilibre)", False,
            "class_weight='balanced' : sur-pondère les classes rares (Logistic / Arbre / "
            "Random Forest). Utile si une classe domine fortement."))
    return controls


def _cv_folds(ptype, y_tr):
    """Fold count for the leaderboard: 5, bounded by the rarest class / sample size."""
    n = len(y_tr)
    if ptype == CLASSIFICATION:
        _, counts = np.unique(y_tr, return_counts=True)
        return max(2, min(5, int(counts.min()), n - 1))
    return max(2, min(5, n - 1))


def _leaderboard(art, ptype, n_est, max_depth, class_weight=None):
    """Rank every candidate model by k-fold cross-validation ON THE TRAIN SET ONLY.

    The held-out test set is never touched here — it stays virgin for the final
    Evaluation. The expert reads CV RMSE/R² (or Accuracy/F1) mean ± std per model
    and picks the best family before fine-tuning.
    """
    X_tr, y_tr = art["X_train"], art["y_train"]
    cv = _cv_folds(ptype, y_tr)
    if ptype == REGRESSION:
        scoring = {"rmse": "neg_root_mean_squared_error", "r2": "r2"}
    else:
        scoring = {"accuracy": "accuracy", "f1": "f1_weighted"}
    rows = []
    for name, est in est_factory.candidate_models(ptype, n_est, max_depth, class_weight).items():
        try:
            res = cross_validate(est, X_tr, y_tr, cv=cv, scoring=scoring,
                                 return_train_score=True, n_jobs=-1)
            if ptype == REGRESSION:
                rmse = -res["test_rmse"]
                r2_cv, r2_train = float(res["test_r2"].mean()), float(res["train_r2"].mean())
                rows.append({"model": name,
                             "rmse_cv": round(float(rmse.mean()), 3),
                             "rmse_cv_std": round(float(rmse.std()), 3),
                             "r2_cv": round(r2_cv, 4), "r2_train": round(r2_train, 4),
                             "overfit": round(r2_train - r2_cv, 4)})
            else:
                acc_cv = float(res["test_accuracy"].mean())
                acc_train = float(res["train_accuracy"].mean())
                rows.append({"model": name,
                             "accuracy_cv": round(acc_cv, 4),
                             "accuracy_cv_std": round(float(res["test_accuracy"].std()), 4),
                             "f1_cv": round(float(res["test_f1"].mean()), 4),
                             "accuracy_train": round(acc_train, 4),
                             "overfit": round(acc_train - acc_cv, 4)})
        except Exception:
            continue
    if ptype == REGRESSION:
        rows.sort(key=lambda r: r["rmse_cv"])             # lower CV RMSE is better
    else:
        rows.sort(key=lambda r: r["accuracy_cv"], reverse=True)
    best = rows[0]["model"] if rows else None
    for r in rows:
        r["recommended"] = (r["model"] == best)
    return rows, best, cv


def _cached_leaderboard(session, sep, ptype, n_est, max_depth, class_weight):
    """Leaderboard memoised in the separate-run artefacts (a replayed Separation
    produces fresh artefacts, so the cache invalidates naturally). Avoids re-running
    the full CV on every view of the Modelling stage."""
    key = f"{ptype}|{n_est}|{max_depth}|{class_weight}|{len(sep.artifacts['X_train'])}"
    cache = sep.artifacts.setdefault("_leaderboard_cache", {})
    if key not in cache:
        cache[key] = _leaderboard(sep.artifacts, ptype, n_est, max_depth, class_weight)
    return cache[key]


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
    cw = "balanced" if cfg.get("class_weight_balanced") else None
    rows, best, cv = _cached_leaderboard(session, sep, ptype, int(cfg["n_estimators"]),
                                         int(cfg["max_depth"]) or None, cw)
    info = {"ready": True, "mode": "supervised", "train_size": int(len(art["X_train"])),
            "n_features": len(art["feature_names"]), "leaderboard": rows, "recommended_model": best,
            "cv_folds": cv, "leakage_free": art.get("preprocessor") is not None,
            "primary_metric": (f"RMSE (CV {cv} plis, train)" if ptype == REGRESSION
                               else f"Accuracy (CV {cv} plis, train)")}
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
    cw = "balanced" if cfg.get("class_weight_balanced") else None
    model = est_factory.make_estimator(ptype, algo, n_est, max_depth, cw)
    if model is None:  # unknown algorithm name → safe default (don't rely on estimator truthiness)
        fallback = RandomForestRegressor if ptype == REGRESSION else RandomForestClassifier
        model = fallback(n_estimators=n_est, random_state=42)
        algo = "RandomForest"

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
                   "max_depth": max_depth or "illimité",
                   **({"Pondération classes": "balanced"} if cw else {}),
                   score_label: train_score},
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
    plots = [_elbow_plot(ks, inertias, k)] if inertias else [message_plot(f"{name} K={k}.")]
    if algo == "agglomerative":
        dendro = _dendrogram_plot(X, k)   # la lecture native du hiérarchique
        if dendro:
            plots.append(dendro)
    result = {
        "report": {"Algorithme": name, "Clusters (K)": k, "Observations": int(len(X))},
        "diagnostics": {"algorithm": name, "k": k},
        "log": [f"{name} entraîné avec K={k} sur {len(X)} observations.",
                "Lecture métier des clusters → voir l'Évaluation (profils + projection PCA)."],
        "warnings": [],
        "plots": plots,
    }
    return result, artifacts


def _dendrogram_plot(X, k, max_rows=300):
    """Ward dendrogram (truncated to the last 30 merges) — the native reading of
    hierarchical clustering: cutting at K clusters happens where the vertical
    distances are largest. Sampled beyond ``max_rows`` to stay legible/fast."""
    import matplotlib.pyplot as plt
    try:
        from scipy.cluster.hierarchy import dendrogram, linkage
    except ImportError:
        return None
    style_plot()
    Xv = X.to_numpy() if hasattr(X, "to_numpy") else np.asarray(X)
    n = len(Xv)
    if n < 3:
        return None
    sampled = n > max_rows
    if sampled:
        idx = np.random.RandomState(42).choice(n, max_rows, replace=False)
        Xv = Xv[idx]
    try:
        Z = linkage(Xv, method="ward")
    except Exception:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    dendrogram(Z, ax=ax, truncate_mode="lastp", p=30, no_labels=True,
               above_threshold_color="#0f3460")
    title = "Dendrogramme (Ward) — fusions hiérarchiques"
    if sampled:
        title += f" (échantillon de {max_rows})"
    ax.set_title(title)
    ax.set_ylabel("Distance de fusion")
    ax.set_xlabel(f"Regroupements (troncature aux 30 dernières fusions) — K choisi = {k}")
    fig.tight_layout()
    return fig_to_base64(fig)


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
    metric_key = "r2_cv" if ptype == REGRESSION else "accuracy_cv"
    title = ("R² (validation croisée, train) par modèle" if ptype == REGRESSION
             else "Accuracy (validation croisée, train) par modèle")
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
