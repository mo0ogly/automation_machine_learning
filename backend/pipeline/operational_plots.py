"""
operational_plots.py — Figures for the operational (SOC/threat-intel) evaluation.

Kept separate from ``operational.py`` (pure metrics, no matplotlib) so the
metric layer stays importable in headless/serving contexts. Every helper returns
a captioned base64 figure for the UI's per-graph AI explainer.
"""

import numpy as np

from .plotting import style_plot, fig_to_base64, message_plot


def threshold_curve_plot(sweep, recommended):
    """Precision / recall / F-beta vs threshold, with the recommended operating
    points marked — the analyst reads off the trade-off before choosing one."""
    import matplotlib.pyplot as plt
    style_plot()
    if not sweep:
        return message_plot("Pas de courbe de seuil disponible.")
    t = [r["threshold"] for r in sweep]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(t, [r["precision"] for r in sweep], color="#16c79a", lw=2, label="Précision")
    ax.plot(t, [r["recall"] for r in sweep], color="#e94560", lw=2, label="Rappel (détection)")
    ax.plot(t, [r["fbeta"] for r in sweep], color="#0f9bd7", lw=1.6, ls="--", label="F2 (rappel prioritaire)")
    marks = {"min_cost": ("#f4a261", "coût min"), "fpr_1pct": ("#a06cd5", "FPR 1%")}
    for key, (color, lbl) in marks.items():
        tv = recommended.get(key)
        if tv is not None:
            ax.axvline(tv, color=color, ls=":", lw=1.4)
            ax.text(tv, 1.01, lbl, color=color, fontsize=7, ha="center", rotation=0)
    ax.set_xlabel("Seuil de décision")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.05)
    ax.set_title("Précision / rappel / F2 selon le seuil")
    ax.legend(loc="lower center", fontsize=8, ncol=3)
    fig.tight_layout()
    return fig_to_base64(fig)


def cost_curve_plot(sweep, cost_fn, cost_fp):
    """Expected cost vs threshold, with the minimum-cost point highlighted."""
    import matplotlib.pyplot as plt
    style_plot()
    if not sweep:
        return message_plot("Pas de courbe de coût disponible.")
    t = [r["threshold"] for r in sweep]
    costs = [r["cost"] for r in sweep]
    imin = int(np.argmin(costs))
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t, costs, color="#e94560", lw=2)
    ax.scatter([t[imin]], [costs[imin]], color="#16c79a", s=80, zorder=5,
               label=f"Coût min @ seuil {t[imin]:.3f}")
    ax.set_xlabel("Seuil de décision")
    ax.set_ylabel(f"Coût attendu (FN×{cost_fn:g} + FP×{cost_fp:g})")
    ax.set_title("Coût opérationnel attendu selon le seuil")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def reliability_plot(calib):
    """Reliability diagram: observed frequency vs predicted confidence per bin.
    On the diagonal = well calibrated."""
    import matplotlib.pyplot as plt
    style_plot()
    curve = (calib or {}).get("curve") or []
    if not curve:
        return message_plot("Calibration non calculable.")
    conf = [c["confidence"] for c in curve]
    freq = [c["frequency"] for c in curve]
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 1], [0, 1], color="#888", ls="--", lw=1.2, label="Calibration parfaite")
    ax.plot(conf, freq, "-o", color="#e94560", lw=2, label="Modèle")
    ax.set_xlabel("Probabilité prédite (confiance)")
    ax.set_ylabel("Fréquence observée")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    brier = calib.get("brier")
    ece = calib.get("ece")
    subtitle = []
    if brier is not None:
        subtitle.append(f"Brier {brier}")
    if ece is not None:
        subtitle.append(f"ECE {ece}")
    ax.set_title("Diagramme de fiabilité" + (f" — {' · '.join(subtitle)}" if subtitle else ""))
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def alert_budget_plot(budget_rows):
    """Precision@k and detection@k as the analyst's review queue deepens."""
    import matplotlib.pyplot as plt
    style_plot()
    if not budget_rows:
        return message_plot("Pas de budget d'alertes disponible.")
    ks = [r["k"] for r in budget_rows]
    prec = [r["precision_at_k"] for r in budget_rows]
    det = [r["detection_at_k"] for r in budget_rows]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot(ks, prec, "-o", color="#16c79a", label="Précision@k (pureté file)")
    ax.plot(ks, det, "-o", color="#e94560", label="Détection@k (couverture)")
    ax.set_xlabel("Alertes revues (k, triées par score)")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1.05)
    ax.set_title("Budget d'alertes : que gagne-t-on en revoyant les k plus suspectes ?")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def anomaly_budget_plot(budget_rows):
    """Alert volume per anomaly-score quantile (unsupervised detection)."""
    import matplotlib.pyplot as plt
    style_plot()
    if not budget_rows:
        return message_plot("Pas de budget d'alertes disponible.")
    q = [str(r["quantile"]) for r in budget_rows]
    per_k = [r["alerts_per_1000"] for r in budget_rows]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.bar(q, per_k, color="#e94560", edgecolor="#0f3460")
    ax.set_xlabel("Quantile du score d'anomalie (seuil d'alerte)")
    ax.set_ylabel("Alertes pour 1000 événements")
    ax.set_title("Volume d'alertes selon le seuil d'anomalie")
    fig.tight_layout()
    return fig_to_base64(fig)


def operational_plots(op):
    """Build the figure list adapted to the operational analysis mode."""
    if not op or not op.get("applicable"):
        return []
    mode = op.get("mode")
    if mode in ("binary", "multiclass_ovr"):
        return [
            threshold_curve_plot(op["threshold_sweep"], op["recommended_thresholds"]),
            cost_curve_plot(op["threshold_sweep"], op["cost"]["cost_fn"], op["cost"]["cost_fp"]),
            reliability_plot(op.get("calibration")),
            alert_budget_plot(op.get("alert_budget")),
        ]
    if mode == "anomaly":
        return [anomaly_budget_plot(op.get("budget_curve"))]
    return []
