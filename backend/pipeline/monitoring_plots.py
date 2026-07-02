"""
monitoring_plots.py — figures for the drift & stability report.

Separate from monitoring.py (pure metrics, no matplotlib) so the metric layer
stays importable headless. Each helper returns a captioned base64 figure for the
UI's per-graph AI explainer.
"""

import numpy as np

from .plotting import style_plot, fig_to_base64, message_plot

_LEVEL_COLOR = {"major": "#e94560", "moderate": "#e8a33d", "none": "#16c79a", "stable": "#16c79a"}


def feature_drift_plot(data_drift, top=15):
    """PSI per feature (top movers), coloured by drift level."""
    import matplotlib.pyplot as plt
    style_plot()
    feats = (data_drift or {}).get("features") or []
    if not feats:
        return message_plot("Pas de dérive de variables à afficher.")
    feats = feats[:top][::-1]
    names = [f["feature"] for f in feats]
    vals = [f["psi"] for f in feats]
    colors = [_LEVEL_COLOR.get(f["level"], "#0f3460") for f in feats]
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.4 * len(names) + 1)))
    ax.barh(names, vals, color=colors, edgecolor="#0f3460")
    ax.axvline(0.1, color="#e8a33d", ls="--", lw=1, label="modérée (0.1)")
    ax.axvline(0.25, color="#e94560", ls="--", lw=1, label="majeure (0.25)")
    ax.set_xlabel("PSI (indice de stabilité de population)")
    ax.set_title("Dérive des données par variable (top)")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def prediction_drift_plot(prediction_drift):
    """Reference vs current output distribution (classes) or a note (regression)."""
    import matplotlib.pyplot as plt
    style_plot()
    pd_ = prediction_drift or {}
    if pd_.get("kind") == "categorical" and pd_.get("classes"):
        rows = pd_["classes"]
        labels = [r["class"] for r in rows]
        ref = [r["ref"] for r in rows]
        cur = [r["cur"] for r in rows]
        x = np.arange(len(labels))
        fig, ax = plt.subplots(figsize=(6.5, 4))
        ax.bar(x - 0.2, ref, 0.4, label="Référence", color="#0f3460", edgecolor="#eee")
        ax.bar(x + 0.2, cur, 0.4, label="Lot courant", color="#e94560", edgecolor="#eee")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel("Proportion des prédictions")
        ax.set_title("Dérive de concept : distribution des prédictions "
                     f"(TVD = {pd_.get('total_variation')})")
        ax.legend(fontsize=8)
        fig.tight_layout()
        return fig_to_base64(fig)
    if pd_.get("kind") == "regression":
        return message_plot("Dérive des prédictions (régression) : PSI = "
                            + str(pd_.get("psi")) + " · moyenne "
                            + str(pd_.get("ref_mean")) + " → " + str(pd_.get("cur_mean")))
    return message_plot("Dérive des prédictions indisponible.")


def jitter_plot(jitter):
    """Flip rate vs perturbation amplitude (the jitter-tolerance curve)."""
    import matplotlib.pyplot as plt
    style_plot()
    j = jitter or {}
    curve = j.get("curve") or []
    if not j.get("available") or not curve:
        return message_plot("Protocole jitter indisponible.")
    eps = [c["epsilon"] for c in curve]
    mean = [c["flip_rate"] for c in curve]
    lo = [c["flip_min"] for c in curve]
    hi = [c["flip_max"] for c in curve]
    tol = j.get("tolerance", 0.05)
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.fill_between(eps, lo, hi, color="#0f3460", alpha=0.25,
                    label="min-max (" + str(j.get("repeats")) + " répétitions)")
    ax.plot(eps, mean, marker="o", color="#0f3460", label="taux de bascule moyen")
    ax.axhline(tol, color="#e94560", ls="--", lw=1,
               label="tolérance (" + str(int(tol * 100)) + "%)")
    if j.get("breaking_epsilon") is not None:
        ax.axvline(j["breaking_epsilon"], color="#e8a33d", ls=":", lw=1.2,
                   label="point de rupture")
    ax.set_xscale("log")
    ax.set_xlabel("Amplitude du bruit (fraction de l'écart-type par variable)")
    ax.set_ylabel("Taux de bascule des prédictions")
    ax.set_title("Stabilité sous perturbation (protocole jitter)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def monitoring_plots(report):
    """Figure list for a drift report."""
    if not report or not report.get("available"):
        return []
    return [feature_drift_plot(report.get("data_drift")),
            prediction_drift_plot(report.get("prediction_drift"))]
