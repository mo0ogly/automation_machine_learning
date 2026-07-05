"""
evaluate.py — Stage 6 : EVALUATION.

Scores the fitted model on the held-out test set (or silhouette for clustering)
and renders the diagnostic plots an expert reads to decide whether to refine an
earlier stage or ship the model.
"""

import numpy as np
import pandas as pd

from sklearn.metrics import (
    mean_squared_error, mean_absolute_error, r2_score, accuracy_score, f1_score,
    precision_score, recall_score, classification_report,
    confusion_matrix, silhouette_score,
    davies_bouldin_score, calinski_harabasz_score,
    roc_auc_score, average_precision_score,
)
from sklearn.model_selection import cross_val_score
from sklearn.decomposition import PCA

from ..context import REGRESSION, CLASSIFICATION, ANOMALY
from ..plotting import style_plot, fig_to_base64, message_plot
from .. import evaluate_plots as adv
from .. import operational as opn
from .. import operational_plots as opn_plots
from .base import toggle, number

STAGE_ID = "evaluate"
TITLE = "Évaluation"
OBJECTIVE = "Mesurer la performance sur le jeu de test et produire les graphiques de diagnostic."


def default_config(ctx):
    return {"learning_curve": True, "cost_fn": opn.DEFAULT_COST_FN,
            "cost_fp": opn.DEFAULT_COST_FP}


def config_schema(ctx):
    if ctx.problem_type not in (REGRESSION, CLASSIFICATION):
        return []
    controls = [toggle("learning_curve", "Courbe d'apprentissage", True,
                       "Ré-entraîne le modèle sur des sous-échantillons croissants (CV) pour voir "
                       "si davantage de données amélioreraient la performance.")]
    if ctx.problem_type == CLASSIFICATION:
        controls += [
            number("cost_fn", "Coût d'une attaque manquée (FN)", opn.DEFAULT_COST_FN, 1, 1000,
                   "Coût opérationnel d'un faux négatif. Sert au seuil coût-minimal (vue opérationnelle SOC)."),
            number("cost_fp", "Coût d'une fausse alerte (FP)", opn.DEFAULT_COST_FP, 1, 1000,
                   "Coût opérationnel d'un faux positif (temps de triage analyste)."),
        ]
    return controls


def diagnose(session):
    model, origin = session.current_model()
    if model is None:
        return {"diagnostics": {"ready": False, "reason": "Le modèle doit être entraîné d'abord."}, "plots": []}
    return {"diagnostics": {"ready": True, "model_origin": origin}, "plots": []}


def run(session, config):
    model, origin = session.current_model()
    sep = session.get_run("separate")
    if model is None or sep is None:
        raise ValueError("Le modèle doit être entraîné (ou rejoué) avant l'évaluation.")
    mrun = session.get_run("tune") if origin == "tuned" else session.get_run("model")
    ptype = session.ctx.problem_type
    art = sep.artifacts

    if ptype == ANOMALY:
        return _evaluate_anomaly(session, art, mrun)
    if art.get("mode") == "unsupervised":
        return _evaluate_clustering(session, model, art, mrun, config)

    cfg = {**default_config(session.ctx), **(config or {})}
    X_test, y_test = art["X_test"], art["y_test"]
    y_pred = model.predict(X_test)
    style_plot()

    class_report = None
    if ptype == REGRESSION:
        mse = float(mean_squared_error(y_test, y_pred))
        metrics = {"R²": round(float(r2_score(y_test, y_pred)), 4),
                   "RMSE": round(float(np.sqrt(mse)), 2),
                   "MAE": round(float(mean_absolute_error(y_test, y_pred)), 2),
                   "MSE": round(mse, 2)}
        mape = _safe_mape(y_test, y_pred)
        if mape is not None:
            metrics["MAPE (%)"] = round(mape, 2)
        plots = [_pred_scatter(y_test, y_pred), _residual_plot(y_test, y_pred)]
    else:
        # Classification: accuracy + precision/recall + per-class report.
        metrics = {
            "Accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "Précision (pondéré)": round(float(precision_score(y_test, y_pred, average="weighted", zero_division=0)), 4),
            "Rappel (pondéré)": round(float(recall_score(y_test, y_pred, average="weighted", zero_division=0)), 4),
            "F1 (pondéré)": round(float(f1_score(y_test, y_pred, average="weighted")), 4),
        }
        le = art.get("label_encoder")
        labels = le.classes_ if le is not None else None
        class_report = _per_class_report(y_test, y_pred, le)
        plots = [_confusion_plot(y_test, y_pred, labels)]
        # Probability-based metrics: ROC-AUC / PR-AUC + curves (binary), OVR AUC (multiclass).
        plots += _proba_metrics(model, X_test, y_test, metrics)

    # Overfitting control: train vs test gap + 5-fold cross-validation.
    control, warn = _overfit_control(model, art, ptype)
    if control:
        plots.append(_overfit_plot(control, ptype))

    # Learning curve: would more data help? (opt-out via config, model re-fits inside)
    if cfg.get("learning_curve") and art.get("X_train") is not None:
        lc = adv.learning_curve_plot(model, art["X_train"], art["y_train"],
                                     "r2" if ptype == REGRESSION else "accuracy",
                                     "R²" if ptype == REGRESSION else "Accuracy")
        if lc:
            plots.append(lc)

    # Operational (SOC / threat-intel) analysis: thresholds, cost, calibration,
    # alert budget — adapted to the problem type. Recomputable live via /operating-point.
    op = opn.build_operational(session, threshold=0.5,
                               cost_fn=float(cfg.get("cost_fn", opn.DEFAULT_COST_FN)),
                               cost_fp=float(cfg.get("cost_fp", opn.DEFAULT_COST_FP)))
    if op.get("applicable"):
        plots += opn_plots.operational_plots(op)

    session.ctx.notes.append(f"eval:{metrics}")
    diagnostics = {"metrics": metrics, "n_test": int(len(y_test)),
                   "algorithm": mrun.artifacts.get("algorithm"),
                   # True when the split-first / train-only path built the matrices —
                   # clean statistics (imputation, outlier bounds) AND the feature
                   # preprocessor both fit on train: no preprocessing leakage at all.
                   "leakage_free": (art.get("preprocessor") is not None
                                    and art.get("clean_preprocessor") is not None),
                   "operational": op}
    if class_report:
        diagnostics["rapport_par_classe"] = class_report
    report = dict(metrics)
    if control:
        diagnostics["controle_surapprentissage"] = control
        report["Écart train−test"] = control["ecart_overfit"]
    result = {
        "report": report,
        "diagnostics": diagnostics,
        "log": [f"Évaluation sur {len(y_test)} observations de test."],
        "warnings": ([warn] if warn else []), "plots": plots, "metrics": metrics,
    }
    return result, {"metrics": metrics}


def _safe_mape(y_test, y_pred):
    """MAPE in %, only when every target is safely away from zero (else meaningless)."""
    y = np.asarray(y_test, dtype=float)
    if len(y) == 0 or np.min(np.abs(y)) < 1e-6:
        return None
    return float(np.mean(np.abs((y - np.asarray(y_pred, dtype=float)) / y)) * 100.0)


def _proba_metrics(model, X_test, y_test, metrics):
    """ROC-AUC / PR-AUC (+ curves for binary) when the model exposes probabilities.

    Mutates ``metrics`` in place and returns the extra plots.
    """
    if not hasattr(model, "predict_proba"):
        return []
    try:
        proba = model.predict_proba(X_test)
    except Exception:
        return []
    classes = np.unique(y_test)
    plots = []
    if proba.ndim == 2 and proba.shape[1] == 2 and len(classes) == 2:
        pos = classes[-1]
        pos_idx = list(getattr(model, "classes_", classes)).index(pos)
        p_pos = proba[:, pos_idx]
        try:
            auc_v = float(roc_auc_score(y_test, p_pos))
            ap_v = float(average_precision_score(y_test, p_pos, pos_label=pos))
        except Exception:
            return []
        metrics["ROC-AUC"] = round(auc_v, 4)
        metrics["PR-AUC (AP)"] = round(ap_v, 4)
        plots.append(adv.roc_plot(y_test, p_pos, auc_v, pos_label=pos))
        plots.append(adv.pr_plot(y_test, p_pos, ap_v, pos_label=pos))
    elif proba.ndim == 2 and proba.shape[1] > 2:
        auc_v = adv.roc_auc_multiclass(y_test, proba)
        if auc_v is not None:
            metrics["ROC-AUC (OVR pondéré)"] = round(auc_v, 4)
    return plots


def _per_class_report(y_test, y_pred, le):
    """Per-class precision / recall / F1 / support (classification_report)."""
    rep = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    rows = []
    for k, v in rep.items():
        if not isinstance(v, dict):  # skip the scalar 'accuracy' entry
            continue
        name = k
        if le is not None and str(k).isdigit():
            try:
                name = str(le.inverse_transform([int(k)])[0])
            except Exception:
                name = k
        rows.append({"classe": name, "précision": round(float(v.get("precision", 0)), 3),
                     "rappel": round(float(v.get("recall", 0)), 3),
                     "f1": round(float(v.get("f1-score", 0)), 3),
                     "support": int(v.get("support", 0))})
    return rows


def _overfit_control(model, art, ptype):
    """Train/test gap + 5-fold CV — the overfitting & robustness check."""
    X_tr, y_tr = art.get("X_train"), art.get("y_train")
    X_te, y_te = art.get("X_test"), art.get("y_test")
    if X_tr is None or X_te is None:
        return None, None
    scoring = "r2" if ptype == REGRESSION else "accuracy"
    score = r2_score if ptype == REGRESSION else accuracy_score
    label = "R²" if ptype == REGRESSION else "Accuracy"
    try:
        s_train = float(score(y_tr, model.predict(X_tr)))
        s_test = float(score(y_te, model.predict(X_te)))
        cv = cross_val_score(model, X_tr, y_tr, cv=5, scoring=scoring)
        cv_mean, cv_std = float(cv.mean()), float(cv.std())
    except Exception:
        return None, None
    gap = s_train - s_test
    control = {
        label + " (train)": round(s_train, 4),
        label + " (test)": round(s_test, 4),
        "ecart_overfit": round(gap, 4),
        "CV " + label + " (5 folds)": round(cv_mean, 4),
        "CV écart-type": round(cv_std, 4),
    }
    warn = None
    if gap > 0.1:
        control["verdict"] = "surapprentissage probable (écart > 0.1)"
        warn = (f"Surapprentissage probable : {label} train {s_train:.3f} vs test {s_test:.3f} "
                f"(écart {gap:.3f}). Envisager plus de régularisation ou moins de variables.")
    elif gap < -0.05:
        control["verdict"] = "test > train : variance d'échantillon, vérifier le découpage"
    else:
        control["verdict"] = "généralisation saine (écart faible)"
    return control, warn


def _evaluate_clustering(session, model, art, mrun, config=None):
    X = art["X_full"]
    feature_names = art.get("feature_names", list(getattr(X, "columns", [])))
    labels = mrun.artifacts.get("labels")
    if labels is None:
        # DBSCAN / AgglomerativeClustering have no .predict(); fall back to the fitted
        # labels_ (no re-fit) before resorting to predict/fit_predict. Guards against a
        # rare path where the stored labels are missing.
        labels = getattr(model, "labels_", None)
        if labels is None:
            labels = model.predict(X) if hasattr(model, "predict") else model.fit_predict(X)
    labels = np.asarray(labels)
    algo = mrun.artifacts.get("algorithm", "KMeans")
    style_plot()

    # DBSCAN marks outliers as label -1 ("noise"); exclude it from the cluster count
    # and from silhouette (which needs >= 2 real clusters).
    has_noise = bool((labels == -1).any())
    n_noise = int((labels == -1).sum())
    n_clusters = int(len(set(labels.tolist())) - (1 if has_noise else 0))

    eval_warnings = []
    extra_metrics = {}
    mask = labels != -1
    if n_clusters >= 2 and int(mask.sum()) > n_clusters:
        Xsub = X.iloc[mask] if isinstance(X, pd.DataFrame) else X[mask]
        lab = labels[mask]
        sil = float(silhouette_score(Xsub, lab))
        # Complementary internal validity indices (computed on the dense clusters):
        # Davies-Bouldin — lower is better ; Calinski-Harabasz — higher is better.
        extra_metrics["Davies-Bouldin"] = round(float(davies_bouldin_score(Xsub, lab)), 3)
        extra_metrics["Calinski-Harabasz"] = round(float(calinski_harabasz_score(Xsub, lab)), 1)
    else:
        sil = 0.0
        eval_warnings.append("Silhouette non calculable (moins de 2 clusters denses) — "
                             "ajuster les paramètres (DBSCAN : eps / min_samples).")

    Xv = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X, columns=feature_names)
    profiles, sizes, means = _cluster_profiles(Xv, labels)  # standardised σ — for the profile plot

    # Read each cluster in REAL units. We join the Cleaning output
    # (pre-scaling values, categoricals still text) to the cluster labels by position
    # (row order is preserved across clean→…→separate in the unsupervised track).
    clean_run = session.get_run("clean")
    raw_df = clean_run.output_df if clean_run is not None else None
    rows, num_cols = _cluster_profiles_raw(raw_df, labels, sizes)

    blabels = _business_labels(rows, num_cols, profiles)  # raw thresholds; σ fallback
    # Cluster decision table: an expert-provided name (config.cluster_labels) overrides
    # the auto label, generalising the business labels beyond the client dataset.
    overrides = (config or {}).get("cluster_labels") or {}
    summary = []
    for r in rows:
        name = overrides.get(str(r["cluster"]))
        label = str(name).strip() if name and str(name).strip() else blabels.get(r["cluster"], "—")
        summary.append({"cluster": r["cluster"], "taille": r["taille"], "label_metier": label,
                        "moyennes": r["means"], "majoritaires": r["majoritaires"]})

    metrics = {"Silhouette": round(sil, 3), "Clusters": n_clusters}
    metrics.update(extra_metrics)
    if has_noise:
        metrics["Points bruit"] = n_noise
    plots = [_cluster_scatter(X, labels, model), _profile_plot(means)]
    log = ["Silhouette = " + str(metrics["Silhouette"]) + " sur " + str(n_clusters) + " clusters"
           + (" (" + str(n_noise) + " points de bruit)" if has_noise else "") + "."]
    if blabels:
        log.append("Lecture métier : " + " · ".join(blabels[c] for c in sorted(blabels)))
    result = {
        "report": metrics,
        "diagnostics": {"metrics": metrics, "algorithm": algo,
                        "cluster_summary": summary,
                        "cluster_sizes": {str(k): int(v) for k, v in sizes.items()}},
        "log": log, "warnings": eval_warnings, "plots": plots, "metrics": metrics,
    }
    return result, {"metrics": metrics}


def _cluster_profiles(Xv, labels):
    """Mean of each feature per cluster (standardised units) + cluster sizes."""
    df = Xv.copy()
    df["__cluster__"] = list(labels)
    means = df.groupby("__cluster__").mean(numeric_only=True)
    sizes = df["__cluster__"].value_counts().to_dict()
    profiles = {int(c): {str(f): round(float(means.loc[c, f]), 2) for f in means.columns}
                for c in means.index}
    return profiles, {int(k): int(v) for k, v in sizes.items()}, means


def _cluster_profiles_raw(raw_df, labels, sizes, max_card=15):
    """Raw (pre-scaling) feature means + majority categorical per cluster."""
    labels = list(labels)
    if raw_df is None or len(raw_df) != len(labels):  # can't align → empty (generic labels follow)
        return ([{"cluster": int(c), "taille": int(sizes.get(c, 0)), "means": {}, "majoritaires": {}}
                 for c in sorted(sizes)], [])
    df = raw_df.reset_index(drop=True).copy()
    df["__cluster__"] = labels
    num_cols = [c for c in df.columns if c != "__cluster__" and pd.api.types.is_numeric_dtype(df[c])]
    cat_cols = [c for c in df.columns if c != "__cluster__" and not pd.api.types.is_numeric_dtype(df[c])
                and df[c].nunique(dropna=True) <= max_card]
    rows = []
    for c in sorted(df["__cluster__"].unique()):
        sub = df[df["__cluster__"] == c]
        means = {col: round(float(sub[col].mean()), 2) for col in num_cols}
        majo = {col: str(sub[col].mode().iloc[0]) for col in cat_cols if not sub[col].mode().empty}
        rows.append({"cluster": int(c), "taille": int(len(sub)), "means": means, "majoritaires": majo})
    return rows, num_cols


def _business_labels(rows, num_cols, profiles):
    """Raw-threshold labels for the client dataset; generic σ otherwise."""
    has_client = "revenu_annuel_k" in num_cols and "panier_moyen" in num_cols
    out = {}
    for r in rows:
        c, m = r["cluster"], r["means"]
        if c == -1:  # DBSCAN noise points
            out[c] = "Bruit / anomalies"
            continue
        if has_client and m:
            rev, pan = m.get("revenu_annuel_k", 0), m.get("panier_moyen", 0)
            promo, age = m.get("sensibilite_promo", 0), m.get("age", 99)
            if rev > 65 and pan > 100:
                out[c] = "Premium fidèle"
            elif promo > 70 and age < 35:
                out[c] = "Digital promo"
            else:
                out[c] = "Famille pragmatique"
        else:
            prof = profiles.get(c, {})
            top = max(prof.items(), key=lambda kv: abs(kv[1])) if prof else ("?", 0)
            out[c] = str(top[0]) + (" élevé" if top[1] >= 0 else " faible")
    return out


def _profile_plot(means):
    import matplotlib.pyplot as plt
    style_plot()
    var = means.var(axis=0).sort_values(ascending=False)
    feats = var.head(8).index.tolist()
    fig, ax = plt.subplots(figsize=(9, 4.5))
    means[feats].T.plot(kind="bar", ax=ax, colormap="plasma", edgecolor="#eee")
    ax.set_title("Profil moyen des clusters (écarts standardisés)")
    ax.set_ylabel("Moyenne (σ)")
    ax.axhline(0, color="#888", lw=0.8)
    ax.legend(title="Cluster", fontsize=7)
    fig.tight_layout()
    return fig_to_base64(fig)


# ── anomaly detection ─────────────────────────────────────────────────────
def _evaluate_anomaly(session, art, mrun):
    """Score the unsupervised outlier detector: rate, score distribution, PCA map,
    and the most abnormal rows in their raw units."""
    X = art["X_full"]
    preds = np.asarray(mrun.artifacts.get("predictions"))
    scores = np.asarray(mrun.artifacts.get("scores"), dtype=float)
    algo = mrun.artifacts.get("algorithm", "Isolation Forest")
    style_plot()
    n = int(len(preds))
    n_anom = int((preds == -1).sum())
    rate = round(100.0 * n_anom / max(1, n), 2)
    metrics = {"Anomalies": n_anom, "Normaux": int((preds == 1).sum()), "Taux d'anomalies (%)": rate}

    # Most abnormal rows in REAL units (join Cleaning output by position, like clustering).
    clean_run = session.get_run("clean")
    raw_df = clean_run.output_df if clean_run is not None else None
    top_rows = _top_anomalies(raw_df, preds, scores)

    plots = [_anomaly_score_hist(scores, preds), _anomaly_scatter(X, preds)]
    # Operational reading: alert volume per anomaly-score quantile (SOC budget).
    op = opn.build_operational(session)
    if op.get("applicable"):
        plots += opn_plots.operational_plots(op)
    log = [f"{algo} : {n_anom} anomalies ({rate}%) sur {n} observations."]
    result = {
        "report": metrics,
        "diagnostics": {"metrics": metrics, "algorithm": algo, "anomaly_rate": rate,
                        "top_anomalies": top_rows, "operational": op},
        "log": log, "warnings": [], "plots": plots, "metrics": metrics,
    }
    return result, {"metrics": metrics}


def _cell(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return str(v)


def _top_anomalies(raw_df, preds, scores, top_n=8, max_cols=6):
    if raw_df is None or len(raw_df) != len(preds):
        return []
    df = raw_df.reset_index(drop=True)
    order = np.argsort(scores)  # lowest score = most abnormal
    anom_idx = [int(i) for i in order if preds[i] == -1][:top_n]
    cols = list(df.columns)[:max_cols]
    rows = []
    for i in anom_idx:
        row = {str(c): _cell(df.iloc[i][c]) for c in cols}
        row["score"] = round(float(scores[i]), 4)
        rows.append(row)
    return rows


def _anomaly_score_hist(scores, preds):
    import matplotlib.pyplot as plt
    style_plot()
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.hist(scores[preds == 1], bins=30, color="#0f3460", alpha=0.8, label="Normaux", edgecolor="#eee")
    ax.hist(scores[preds == -1], bins=30, color="#e94560", alpha=0.85, label="Anomalies", edgecolor="#eee")
    ax.set_xlabel("Score d'anomalie (plus bas = plus anormal)")
    ax.set_ylabel("Effectif")
    ax.set_title("Distribution des scores d'anomalie")
    ax.legend()
    fig.tight_layout()
    return fig_to_base64(fig)


def _anomaly_scatter(X, preds):
    import matplotlib.pyplot as plt
    style_plot()
    Xv = X.to_numpy() if hasattr(X, "to_numpy") else np.asarray(X)
    coords = PCA(n_components=2).fit_transform(Xv) if Xv.shape[1] > 2 else Xv
    fig, ax = plt.subplots(figsize=(6.5, 5))
    normal = preds == 1
    ax.scatter(coords[normal, 0], coords[normal, 1], c="#0f3460", s=22, alpha=0.6, label="Normaux")
    ax.scatter(coords[~normal, 0], coords[~normal, 1], c="#e94560", s=45, marker="x", label="Anomalies")
    ax.set_title("Anomalies (projection PCA)")
    ax.legend()
    fig.tight_layout()
    return fig_to_base64(fig)


# ── plot helpers ──────────────────────────────────────────────────────────
def _overfit_plot(control, ptype):
    import matplotlib.pyplot as plt
    style_plot()
    label = "R²" if ptype == REGRESSION else "Accuracy"
    names = ["Train", "Test", "CV (5 folds)"]
    vals = [control[label + " (train)"], control[label + " (test)"], control["CV " + label + " (5 folds)"]]
    err = [0, 0, control["CV écart-type"]]
    colors = ["#0f3460", "#e94560", "#16c79a"]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(names, vals, yerr=err, capsize=5, color=colors, edgecolor="#eee")
    ax.set_ylabel(label)
    ax.set_title("Contrôle du surapprentissage (train / test / CV)")
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    return fig_to_base64(fig)


def _pred_scatter(y_test, y_pred):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.scatter(y_test, y_pred, alpha=0.4, color="#0f3460", edgecolor="#e94560", s=20)
    lims = [float(np.min(y_test)), float(np.max(y_test))]
    ax.plot(lims, lims, "r--", lw=2, label="Idéal")
    ax.set_xlabel("Réel")
    ax.set_ylabel("Prédit")
    ax.set_title("Réel vs Prédit")
    ax.legend()
    fig.tight_layout()
    return fig_to_base64(fig)


def _residual_plot(y_test, y_pred):
    import matplotlib.pyplot as plt
    residuals = np.asarray(y_test) - np.asarray(y_pred)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(y_pred, residuals, alpha=0.4, color="#e94560", edgecolor="#0f3460", s=18)
    ax.axhline(0, color="yellow", ls="--", lw=1.5)
    ax.set_xlabel("Prédit")
    ax.set_ylabel("Résidu")
    ax.set_title("Résidus")
    fig.tight_layout()
    return fig_to_base64(fig)


def _confusion_plot(y_test, y_pred, labels):
    import matplotlib.pyplot as plt
    import seaborn as sns
    cm = confusion_matrix(y_test, y_pred)
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    xt = [str(l) for l in labels] if labels is not None else "auto"
    yt = [str(l) for l in labels] if labels is not None else "auto"
    sns.heatmap(cm, annot=True, fmt="d", cmap="RdPu", ax=ax, xticklabels=xt, yticklabels=yt)
    ax.set_xlabel("Prédit")
    ax.set_ylabel("Réel")
    ax.set_title("Matrice de confusion")
    fig.tight_layout()
    return fig_to_base64(fig)


def _cluster_scatter(X, labels, model):
    import matplotlib.pyplot as plt
    labels = np.asarray(labels)
    Xv = X.to_numpy() if hasattr(X, "to_numpy") else np.asarray(X)
    pca = None
    if Xv.shape[1] > 2:
        pca = PCA(n_components=2)
        coords = pca.fit_transform(Xv)
    else:
        coords = Xv
    # KMeans exposes cluster_centers_; DBSCAN / Agglomerative don't → use label centroids.
    centers = getattr(model, "cluster_centers_", None)
    if centers is not None:
        centers2d = pca.transform(centers) if pca is not None else np.asarray(centers)
    else:
        cl = [c for c in sorted(set(labels.tolist())) if c != -1]
        centers2d = np.array([coords[labels == c].mean(axis=0) for c in cl]) if cl else None
    fig, ax = plt.subplots(figsize=(6.5, 5))
    noise = labels == -1
    if noise.any():
        ax.scatter(coords[noise, 0], coords[noise, 1], c="#888", s=18, alpha=0.5,
                   marker="x", label="Bruit")
    pts = ~noise
    ax.scatter(coords[pts, 0], coords[pts, 1], c=labels[pts], cmap="plasma", s=28, alpha=0.7)
    if centers2d is not None and len(centers2d):
        ax.scatter(centers2d[:, 0], centers2d[:, 1], c="red", marker="X", s=200, zorder=5)
    if noise.any():
        ax.legend(loc="best", fontsize=8)
    ax.set_title("Clusters (projection PCA)")
    fig.tight_layout()
    return fig_to_base64(fig)
