"""
stability_plots.py — figures for the advanced stability analyses (stability.py).

One figure per analysis, keyed by the analysis id, so the route attaches the
right plot generically. Metric layer stays matplotlib-free (stability.py).
"""

import numpy as np

from .plotting import style_plot, fig_to_base64, message_plot


def _hist(values, title, xlabel, vline=None, vlabel=None):
    import matplotlib.pyplot as plt
    style_plot()
    v = np.asarray(values, dtype=float)
    if not len(v):
        return message_plot("Pas de distribution à afficher.")
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.hist(v, bins=30, color="#0f3460", edgecolor="#eee")
    if vline is not None:
        ax.axvline(vline, color="#e94560", ls="--", lw=1.2, label=vlabel)
        ax.legend(fontsize=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Nombre de lignes")
    ax.set_title(title)
    fig.tight_layout()
    return fig_to_base64(fig)


def numerical_plot(rep):
    deltas = rep.get("score_deltas")
    if not deltas:
        return message_plot("Jitter numérique : " + str(rep.get("precision_flip_rate", 0) * 100)
                            + "% de bascules float32 vs float64 (pas de score continu à tracer).")
    return _hist(deltas, "Jitter numérique : écarts de score float32 vs float64",
                 "|score(float64) - score(float32)|")


def margin_plot(rep):
    margins = rep.get("margins")
    if not margins:
        return message_plot("Analyse de marge indisponible.")
    return _hist(margins, "Marges au seuil de décision (population à risque à gauche)",
                 "Distance normalisée au seuil", vline=0.05, vlabel="bande 5%")


def churn_plot(rep):
    import matplotlib.pyplot as plt
    style_plot()
    rates = rep.get("rates") or []
    if not rates:
        return message_plot("Churn indisponible.")
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    xs = [f"seed {i+1}" for i in range(len(rates))]
    ax.bar(xs, rates, color="#0f3460", edgecolor="#eee")
    ax.axhline(0.05, color="#e94560", ls="--", lw=1, label="5%")
    ax.set_ylabel("Désaccord vs modèle déployé")
    ax.set_title("Churn de ré-entraînement (instabilité structurelle)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def conformal_plot(rep):
    import matplotlib.pyplot as plt
    if rep.get("set_sizes") is not None:
        style_plot()
        sizes = np.asarray(rep["set_sizes"])
        vals, counts = np.unique(sizes, return_counts=True)
        fig, ax = plt.subplots(figsize=(6.5, 3.6))
        colors = ["#e94560" if v == 0 else ("#16c79a" if v == 1 else "#e8a33d") for v in vals]
        ax.bar([str(int(v)) for v in vals], counts / counts.sum(), color=colors, edgecolor="#eee")
        ax.set_xlabel("Taille de l'ensemble de prédiction (1 = verdict net)")
        ax.set_ylabel("Proportion des lignes")
        ax.set_title("Prédiction conforme : verdicts nets vs ambigus")
        fig.tight_layout()
        return fig_to_base64(fig)
    if rep.get("p_values") is not None:
        return _hist(rep["p_values"], "P-values conformes (anomalies à gauche)",
                     "p-value conforme", vline=0.05, vlabel="niveau 5%")
    if rep.get("residuals") is not None:
        return _hist(rep["residuals"], "Résidus de calibration et demi-largeur conforme",
                     "|résidu|", vline=rep.get("qhat"), vlabel="demi-largeur garantie")
    return message_plot("Prédiction conforme indisponible.")


def smoothing_plot(rep):
    import matplotlib.pyplot as plt
    style_plot()
    radii = rep.get("radii") or []
    if not radii:
        return message_plot("Aucun point certifié à ce niveau de bruit/confiance.")
    r = np.sort(np.asarray(radii, dtype=float))
    frac = 1.0 - np.arange(len(r)) / max(1, len(r))
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.step(r, frac * rep.get("certified_fraction", 1.0), where="post", color="#0f3460")
    ax.set_xlabel("Rayon certifié (unités : écart-type par variable)")
    ax.set_ylabel("Fraction des points certifiés à ce rayon")
    ax.set_title("Robustesse certifiée (randomized smoothing, Cohen 2019)")
    fig.tight_layout()
    return fig_to_base64(fig)


PLOTS = {
    "numerical": numerical_plot,
    "margin": margin_plot,
    "churn": churn_plot,
    "conformal": conformal_plot,
    "smoothing": smoothing_plot,
}
