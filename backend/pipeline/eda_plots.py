"""
eda_plots.py — Univariate & bivariate exploratory plots, ONE figure per chart.

Covers the "Analyse des variables descriptives" and "Analyse bivariée" sections,
but each variable is its own figure (not packed into a grid) so the labels stay
readable in the thumbnail and every chart gets its own caption + per-graph AI
explainer.

These run on the *cleaned* frame (Transformation's input): ordinals are already
encoded to integers, nominals are still text.

These per-variable distributions belong to the TRANSFORMATION stage. Before adding
similar plots elsewhere, read docs/pipeline-graphs.md (graph catalogue / anti-doublon)
— e.g. the Nettoyage shows per-variable BOXPLOTS (outliers), not these distributions.
"""

from .plotting import style_plot, fig_to_base64, message_plot

# Per-type caps so a wide frame doesn't flood the view with hundreds of charts.
_MAX_CONTINUOUS = 8
_MAX_DISCRETE = 8
_MAX_NOMINAL = 6
_MAX_BIVAR_DISCRETE = 3
_MAX_BIVAR_NOMINAL = 2


def univariate_plots(df, t):
    """One readable figure per variable: histogram (continuous) or count plot."""
    import matplotlib.pyplot as plt
    import seaborn as sns
    style_plot()

    plots = []
    cont = [c for c in t["continue"] if c in df.columns][:_MAX_CONTINUOUS]
    disc = [c for c in t["discrete"] if c in df.columns][:_MAX_DISCRETE]
    nomi = [c for c in t["nominale"] if c in df.columns][:_MAX_NOMINAL]

    for c in cont:
        fig, ax = plt.subplots(figsize=(5, 3.4))
        ax.hist(df[c].dropna(), bins=30, color="#e94560", edgecolor="#0f3460")
        ax.set_title("Distribution — " + str(c))
        fig.tight_layout()
        plots.append(fig_to_base64(fig))

    for c in disc:
        fig, ax = plt.subplots(figsize=(5, 3.4))
        sns.countplot(x=df[c], ax=ax, color="#0f3460")
        ax.set_title("Effectifs — " + str(c))
        ax.set_xlabel("")
        fig.tight_layout()
        plots.append(fig_to_base64(fig))

    for c in nomi:
        fig, ax = plt.subplots(figsize=(5.6, 3.6))
        order = df[c].value_counts().index
        sns.countplot(y=df[c].astype(str), order=[str(o) for o in order], ax=ax, color="#16c79a")
        ax.set_title("Effectifs — " + str(c))
        ax.set_ylabel("")
        fig.tight_layout()
        plots.append(fig_to_base64(fig))

    if not plots:
        plots.append(message_plot("Pas de variable exploitable pour l'analyse univariée."))
    return plots, []


def bivariate_plots(df, target, t):
    """One boxplot per variable vs the target."""
    import matplotlib.pyplot as plt
    import pandas as pd
    import seaborn as sns
    style_plot()
    if not target or target not in df.columns:
        return [message_plot("Pas de cible : analyse bivariée non applicable (non supervisé).")]
    if not pd.api.types.is_numeric_dtype(df[target]):
        return [message_plot("Cible non numérique : analyse bivariée par boxplot non applicable (classification).")]

    plots = []
    disc = [c for c in t["discrete"] if c in df.columns and c != target]
    if disc:
        try:  # rank by |correlation| so the most telling boxplots come first
            corr = df[disc + [target]].corr()[target].abs().drop(labels=[target], errors="ignore")
            disc = list(corr.sort_values(ascending=False).index)
        except Exception:
            pass
        for c in disc[:_MAX_BIVAR_DISCRETE]:
            fig, ax = plt.subplots(figsize=(5, 3.6))
            sns.boxplot(data=df, x=c, y=target, ax=ax, color="#0f3460")
            ax.set_title(str(target) + " selon " + str(c))
            fig.tight_layout()
            plots.append(fig_to_base64(fig))

    nomi = sorted([c for c in t["nominale"] if c in df.columns], key=lambda c: df[c].nunique())
    for c in nomi[:_MAX_BIVAR_NOMINAL]:
        fig, ax = plt.subplots(figsize=(6.4, 4))
        order = df.groupby(c)[target].median().sort_values().index
        sns.boxplot(data=df, x=c, y=target, order=[o for o in order], ax=ax, color="#16c79a")
        ax.set_title(str(target) + " selon " + str(c))
        ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        plots.append(fig_to_base64(fig))

    if not plots:
        plots.append(message_plot("Pas de variable catégorielle/discrète pour l'analyse bivariée."))
    return plots
