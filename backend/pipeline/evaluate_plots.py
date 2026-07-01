"""
evaluate_plots.py — Advanced evaluation figures (ROC / PR / learning curve).

Split out of ``stages/evaluate.py`` to keep that module within the project's
file-size budget. Every helper returns a captioned base64 figure (or ``None``
when the plot does not apply), ready for the UI's per-graph AI explainer.
"""

import numpy as np

from sklearn.metrics import roc_curve, precision_recall_curve, auc
from sklearn.model_selection import learning_curve

from .plotting import style_plot, fig_to_base64


def roc_plot(y_test, proba_pos, auc_value, pos_label=1):
    """Binary ROC curve with the AUC in the title. ``proba_pos`` = P(classe positive)."""
    import matplotlib.pyplot as plt
    style_plot()
    fpr, tpr, _ = roc_curve(y_test, proba_pos, pos_label=pos_label)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot(fpr, tpr, color="#e94560", lw=2, label=f"ROC (AUC = {auc_value:.3f})")
    ax.plot([0, 1], [0, 1], color="#888", ls="--", lw=1.2, label="Hasard (AUC = 0.5)")
    ax.set_xlabel("Taux de faux positifs")
    ax.set_ylabel("Taux de vrais positifs")
    ax.set_title("Courbe ROC (jeu de test)")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def pr_plot(y_test, proba_pos, ap_value, pos_label=1):
    """Binary precision-recall curve — the honest view under class imbalance."""
    import matplotlib.pyplot as plt
    style_plot()
    prec, rec, _ = precision_recall_curve(y_test, proba_pos, pos_label=pos_label)
    baseline = float(np.mean(np.asarray(y_test) == pos_label))
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot(rec, prec, color="#16c79a", lw=2, label=f"PR (AP = {ap_value:.3f})")
    ax.axhline(baseline, color="#888", ls="--", lw=1.2,
               label=f"Hasard (prévalence = {baseline:.2f})")
    ax.set_xlabel("Rappel")
    ax.set_ylabel("Précision")
    ax.set_title("Courbe précision-rappel (jeu de test)")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def learning_curve_plot(model, X_train, y_train, scoring, label, cv=3):
    """Train/CV score vs training-set size: shows whether MORE DATA would help
    (curves still converging) or the model saturates (plateau)."""
    import matplotlib.pyplot as plt
    style_plot()
    try:
        sizes, tr_scores, va_scores = learning_curve(
            model, X_train, y_train, cv=cv, scoring=scoring,
            train_sizes=np.linspace(0.2, 1.0, 5), n_jobs=-1, shuffle=True, random_state=42)
    except Exception:
        return None
    tr_mean, tr_std = tr_scores.mean(axis=1), tr_scores.std(axis=1)
    va_mean, va_std = va_scores.mean(axis=1), va_scores.std(axis=1)
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.plot(sizes, tr_mean, "-o", color="#0f3460", label=f"{label} (train)")
    ax.fill_between(sizes, tr_mean - tr_std, tr_mean + tr_std, color="#0f3460", alpha=0.15)
    ax.plot(sizes, va_mean, "-o", color="#e94560", label=f"{label} (CV {cv} plis)")
    ax.fill_between(sizes, va_mean - va_std, va_mean + va_std, color="#e94560", alpha=0.15)
    ax.set_xlabel("Taille du jeu d'entraînement")
    ax.set_ylabel(label)
    ax.set_title("Courbe d'apprentissage — plus de données aiderait-il ?")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def roc_auc_multiclass(y_test, proba):
    """Weighted one-vs-rest AUC for multiclass problems (None when not computable)."""
    from sklearn.metrics import roc_auc_score
    try:
        return float(roc_auc_score(y_test, proba, multi_class="ovr", average="weighted"))
    except Exception:
        return None


__all__ = ["roc_plot", "pr_plot", "learning_curve_plot", "roc_auc_multiclass", "auc"]
