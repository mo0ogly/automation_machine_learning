"""
integrate.py — Stage 3 : INTEGRATION.

Responsibility: assemble the final feature matrix and reduce redundancy. Drop
one of each pair of highly-correlated features, optionally select the most
informative features (univariate score vs the target), and optionally compress
with PCA. This is the "data integration / reduction" step of the classic
data-preprocessing taxonomy (Han & Kamber).
"""

import pandas as pd

from sklearn.decomposition import PCA

from .. import diagnostics as dg
from .. import typology as typ
from ..plotting import style_plot, fig_to_base64, message_plot
from ..context import REGRESSION
from .base import toggle, rng, column_table, counts

STAGE_ID = "integrate"
TITLE = "Intégration"
OBJECTIVE = "Assembler la matrice finale : l'expert choisit les variables à garder, redondance signalée."

_TYPE_LABEL = {"continue": "Quant. continue", "discrete": "Quant. discrète", "nominale": "Catégorielle"}


def feature_analysis(df, ctx):
    """Per-feature keep/drop table for integration: redundancy + link-to-target advice."""
    target = ctx.target_col
    feats = [c for c in df.columns if c != target]
    tcorr = ({d["column"]: d["abs_corr"] for d in dg.target_correlation(df, target, top=10_000)}
             if ctx.supervised else {})
    pairs = dg.high_correlation_pairs(df, target, threshold=0.95, top=10_000)
    t = typ.classify(df, target)
    type_of = {}
    for key, lbl in _TYPE_LABEL.items():
        for c in t[key]:
            type_of[c] = lbl
    for c in t["ordinale"]:
        type_of[c] = "Ordinale"

    # Redundancy: for each highly-correlated pair, drop the one less linked to the target.
    redundant, seen = {}, set()
    for p in pairs:
        a, b = p["a"], p["b"]
        if a in seen or b in seen:
            continue
        drop = b if tcorr.get(a, 0) >= tcorr.get(b, 0) else a
        keep = a if drop == b else b
        seen.add(drop)
        redundant[drop] = f"redondante avec {keep} (|r|={p['corr']})"

    rows, rec_drop = [], []
    for c in feats:
        tc = tcorr.get(c)
        if c in redundant:
            rec, reason = "retirer", redundant[c]
        elif ctx.supervised and tc is not None and tc < 0.05:
            rec, reason = "garder", f"lien faible avec la cible (|r|={tc})"
        else:
            rec = "garder"
            reason = (f"|r| cible = {tc}" if tc is not None else "variable conservée")
        if rec == "retirer":
            rec_drop.append(str(c))
        rows.append({"column": str(c), "type": type_of.get(c, "numérique"),
                     "corr": (tc if tc is not None else "—"), "recommended": rec, "reason": reason})
    return rows, rec_drop


_FEATURE_COLS = [
    {"key": "column", "label": "Variable"}, {"key": "type", "label": "Type"},
    {"key": "corr", "label": "|r| cible"}, {"key": "recommended", "label": "Avis"},
    {"key": "reason", "label": "Pourquoi"},
]


def default_config(df, ctx):
    _, rec_drop = feature_analysis(df, ctx)
    return {"dropped_features": rec_drop, "pca": False, "pca_variance": 0.95}


def config_schema(df, ctx):
    rows, rec_drop = feature_analysis(df, ctx)
    return [
        column_table("dropped_features", "Variables — vous décidez lesquelles garder", rows, rec_drop,
                     "Cochez les variables à RETIRER. Les redondantes (très corrélées entre elles) sont pré-cochées.",
                     cols=_FEATURE_COLS),
        toggle("pca", "Réduction PCA (compression)", False,
               "Remplace les variables numériques par des composantes principales."),
        rng("pca_variance", "Variance retenue (PCA)", 0.7, 0.99, 0.01, 0.95,
            "Part de variance que les composantes doivent conserver."),
    ]


def diagnose(df, ctx):
    pairs = dg.high_correlation_pairs(df, ctx.target_col, threshold=0.9)
    tcorr = dg.target_correlation(df, ctx.target_col)
    plots = [_corr_heatmap(df, ctx.target_col)]
    if tcorr:
        plots.append(_target_corr_bar(tcorr))
        # Analyse bivariée (notebook J1) : nuage de points variable la plus liée vs cible.
        if ctx.problem_type == REGRESSION:
            plots.append(_bivariate_scatter(df, ctx.target_col, tcorr[0]["column"]))
    return {
        "diagnostics": {
            "n_features": len(dg.feature_columns(df, ctx.target_col)[0]) + len(dg.feature_columns(df, ctx.target_col)[1]),
            "high_correlation_pairs": pairs,
            "target_correlation": tcorr,
        },
        "plots": plots,
    }


def run(df, config, ctx):
    cfg = {**default_config(df, ctx), **(config or {})}
    df_in = df
    df = df.copy()
    log, warnings = [], []
    target = ctx.target_col

    # 1. Drop the features the expert chose to remove (target is never droppable).
    to_drop = [c for c in (cfg.get("dropped_features") or []) if c in df.columns and c != target]
    if to_drop:
        df = df.drop(columns=to_drop)
        shown = ", ".join(map(str, to_drop[:8])) + ("…" if len(to_drop) > 8 else "")
        log.append(f"{len(to_drop)} variable(s) retirée(s) : {shown}.")
    else:
        log.append("Aucune variable retirée — matrice conservée intégralement.")

    # 2. Optional PCA compression (numeric features only).
    pca_info = None
    if cfg.get("pca"):
        num_cols, _ = dg.feature_columns(df, target)
        if len(num_cols) >= 2:
            X = df[num_cols].fillna(0)
            try:
                pca = PCA(n_components=float(cfg["pca_variance"]), svd_solver="full")
                comps = pca.fit_transform(X)
                pc_cols = [f"PC{i+1}" for i in range(comps.shape[1])]
                df_pca = pd.DataFrame(comps, columns=pc_cols, index=df.index)
                keep_target = df[[target]] if (target and target in df.columns) else None
                df = pd.concat([df_pca, keep_target], axis=1) if keep_target is not None else df_pca
                pca_info = {
                    "n_components": len(pc_cols),
                    "retained_variance": round(float(pca.explained_variance_ratio_.sum()), 3),
                    "from_features": len(num_cols),
                }
                log.append(f"PCA : {len(num_cols)} variables → {len(pc_cols)} composantes "
                           f"({pca_info['retained_variance']*100:.0f}% variance).")
            except Exception as e:
                warnings.append(f"PCA ignorée : {e}.")
        else:
            warnings.append("PCA ignorée : moins de 2 variables numériques.")

    df = df.reset_index(drop=True)
    n_in = len([c for c in df_in.columns if c != target])
    n_final = len([c for c in df.columns if c != target])
    plots = [_corr_heatmap(df, target)]

    result = {
        "report": {
            "Variables": f"{n_in} → {n_final}",
            "Retirées par l'expert": len(to_drop),
            "PCA": (f"{pca_info['n_components']} comp. ({int(pca_info['retained_variance']*100)}% var.)"
                    if pca_info else "non"),
        },
        "diagnostics": {
            "dropped_features": to_drop,
            "pca": pca_info,
            "n_final_features": n_final,
        },
        "counts": counts(df_in, df),
        "log": log,
        "warnings": warnings,
        "plots": plots,
    }
    return df, result


# ── local plot helpers ───────────────────────────────────────────────────
def _corr_heatmap(df, target):
    import matplotlib.pyplot as plt
    import seaborn as sns
    style_plot()
    num, _ = dg.feature_columns(df, target)
    num = num[:15]
    if len(num) < 2:
        return message_plot("Pas assez de variables numériques pour une matrice de corrélation.")
    corr = df[num].corr()
    fig, ax = plt.subplots(figsize=(min(9, 1 + 0.55 * len(num)), min(7, 1 + 0.5 * len(num))))
    sns.heatmap(corr, cmap="RdBu_r", center=0, ax=ax, square=False,
                cbar_kws={"shrink": 0.7}, xticklabels=True, yticklabels=True)
    ax.set_title("Corrélations entre variables")
    fig.tight_layout()
    return fig_to_base64(fig)


def _target_corr_bar(tcorr):
    import matplotlib.pyplot as plt
    style_plot()
    cols = [d["column"] for d in tcorr][::-1]
    vals = [d["abs_corr"] for d in tcorr][::-1]
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.35 * len(cols) + 1)))
    ax.barh(cols, vals, color="#e94560", edgecolor="#0f3460")
    ax.set_title("|Corrélation| avec la cible")
    fig.tight_layout()
    return fig_to_base64(fig)


def _bivariate_scatter(df, target, feature):
    """Analyse bivariée : nuage de points de la variable la plus corrélée vs la cible."""
    import matplotlib.pyplot as plt
    style_plot()
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.scatter(df[feature], df[target], alpha=0.4, color="#0f3460", edgecolor="#e94560", s=18)
    ax.set_xlabel(feature)
    ax.set_ylabel(target)
    ax.set_title("Analyse bivariée : " + str(feature) + " vs " + str(target))
    fig.tight_layout()
    return fig_to_base64(fig)
