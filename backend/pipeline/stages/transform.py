"""
transform.py — Stage 2 : TRANSFORMATION.

Reshape feature values into a model-friendly space, following the 4-way variable
typology (see pipeline.typology):

    quantitative continue / discrète  -> impute + scale
    catégorielle ORDINALE             -> ranked integers (order preserved) + scale
    catégorielle NOMINALE             -> One-Hot (no false ordering)

This fixes the earlier bug where a generic OrdinalEncoder encoded quality grades
(Po<Fa<TA<Gd<Ex) in arbitrary alphabetical order, destroying their meaning.

Note on leakage: scalers/encoders are fit on the full frame HERE, for the
exploratory view only (EDA plots, diagnostics, decision tables). The matrices
actually used for modelling are rebuilt by the Separation stage, which splits
first and re-fits the same semantics on the TRAIN partition only (see
``pipeline.preprocessing.FeaturePreprocessor``).
"""

import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler, OrdinalEncoder, PowerTransformer

from .. import diagnostics as dg
from .. import typology as typ
from .. import eda_plots as eda
from .. import feature_engineering as fe
from ..plotting import style_plot, fig_to_base64, message_plot
from .base import select, toggle, rng, number, counts

STAGE_ID = "transform"
TITLE = "Transformation"
OBJECTIVE = "Échelle, asymétrie, encodage ORDONNÉ des ordinales / One-Hot des nominales, features dérivées."


def default_config(df, ctx):
    return {
        "feature_engineering": True,
        "interactions": "none",
        "binning": "none",
        "n_bins": 5,
        "skew_correction": False,
        "skew_threshold": 1.0,
        "skew_method": "yeo-johnson",
        "scaler": "standard",
        "nominal_encoding": "onehot",
        "onehot_max_cardinality": 12,
    }


def config_schema(df, ctx):
    return [
        toggle("feature_engineering", "Features dérivées", True,
               "Crée des variables métier quand les colonnes existent (Age = YrSold − YearBuilt, Renov)."),
        select("interactions", "Interactions de variables",
               [("none", "Aucune"), ("products", "Produits (a×b)"),
                ("ratios", "Rapports (a/b)"), ("both", "Produits + rapports")], "none",
               "Combine les variables numériques les plus variables (produits/rapports) pour "
               "capter des effets non additifs. Nombre borné pour éviter l'explosion de colonnes. "
               "En cas de doute, cliquez « IA »."),
        select("binning", "Discrétisation (binning)",
               [("none", "Aucune"), ("quantile", "Quantiles (effectifs égaux)"),
                ("uniform", "Largeur égale")], "none",
               "Transforme des variables continues en tranches (bins) — utile pour des seuils "
               "métier ou des relations non linéaires. Les bornes sont ajustées sur le train seul."),
        number("n_bins", "Nombre de tranches (bins)", 5, 2, 20,
               "Nombre de tranches quand la discrétisation est active."),
        toggle("skew_correction", "Corriger l'asymétrie", False,
               "Transformation de puissance sur les variables très asymétriques."),
        rng("skew_threshold", "Seuil d'asymétrie |skew|", 0.5, 3.0, 0.25, 1.0, ""),
        select("skew_method", "Méthode de redressement",
               [("yeo-johnson", "Yeo-Johnson (gère négatifs)"), ("log1p", "log(1+x) (positifs)")],
               "yeo-johnson", ""),
        select("scaler", "Mise à l'échelle",
               [("standard", "StandardScaler (μ=0, σ=1)"), ("minmax", "MinMax (0–1)"),
                ("robust", "Robust (médiane/IQR)"), ("none", "Aucune")],
               "standard", "Appliquée aux numériques + ordinales (pas aux indicatrices One-Hot)."),
        select("nominal_encoding", "Encodage des NOMINALES",
               [("onehot", "One-Hot (recommandé, pas d'ordre factice)"), ("ordinal", "Ordinal (entiers)")],
               "onehot", "Les ORDINALES sont toujours encodées en gardant leur ordre sémantique."),
        number("onehot_max_cardinality", "One-Hot : cardinalité max", 12, 2, 50,
               "Au-delà, repli ordinal pour éviter l'explosion de colonnes."),
    ]


def diagnose(df, ctx):
    t = typ.classify(df, ctx.target_col)
    skew = dg.skewness(df, ctx.target_col)
    plots = []
    if skew:
        plots.append(_skew_plot(df, skew[0]["column"]))
    # Analyse univariée par type + bivariée vs cible.
    uni, _ = eda.univariate_plots(df, t)
    plots.extend(uni)
    plots.extend(eda.bivariate_plots(df, ctx.target_col, t))
    return {
        "diagnostics": {
            "typologie": typ.summary_rows(t),
            "ordinales_detectees": list(t["ordinale"].keys()),
            "skewness": skew,
            "analyse_descriptive": {
                "continues": len(t["continue"]),
                "discretes": len(t["discrete"]),
                "nominales": len(t["nominale"]),
            },
        },
        "plots": plots,
    }


def run(df, config, ctx, make_plots=True):
    cfg = {**default_config(df, ctx), **(config or {})}
    df_in = df
    df = df.copy()
    log, warnings = [], []
    target = ctx.target_col
    engineered, skewed, ordinal_enc, nominal_oh, nominal_ord, scaled = [], [], [], [], [], []

    # 1. Feature engineering (preview — the leakage-free preprocessor rebuilds these
    #    with train-fitted interaction base / bin edges; here we build on the working
    #    frame for the exploratory view). Shared logic: pipeline.feature_engineering.
    if cfg["feature_engineering"]:
        df, dom = fe.domain_features(df)
        engineered += dom
    imode = str(cfg.get("interactions", "none"))
    if imode in ("products", "ratios", "both"):
        base = fe.interaction_base(df, target)
        df, inter = fe.apply_interactions(df, base, imode)
        engineered += inter
    bmode = str(cfg.get("binning", "none"))
    if bmode in ("quantile", "uniform"):
        cols = fe.bin_candidate_cols(df, target)
        edges = fe.fit_bin_edges(df, cols, int(cfg.get("n_bins", 5)), bmode)
        df, binned = fe.apply_bins(df, edges)
        engineered += binned
    if engineered:
        log.append(f"Features créées : {', '.join(engineered[:8])}"
                   + ("…" if len(engineered) > 8 else "") + ".")

    # 2. Typology (4-way) on the engineered frame.
    t = typ.classify(df, target, ordinal_overrides=cfg.get("ordinal_overrides"))
    numeric_feats = [c for c in (t["continue"] + t["discrete"]) if c in df.columns]

    # 3. Skewness correction on numeric (continue + discrète).
    if cfg["skew_correction"] and numeric_feats:
        thr = float(cfg["skew_threshold"])
        for c in numeric_feats:
            s = df[c].dropna()
            if len(s) < 3 or s.nunique() < 3:
                continue
            try:
                sk = float(s.skew())
            except Exception:
                continue
            if not np.isfinite(sk) or abs(sk) < thr:
                continue
            if cfg["skew_method"] == "log1p" and (df[c] >= 0).all():
                df[c] = np.log1p(df[c]); skewed.append(c)
            else:
                try:
                    df[c] = PowerTransformer(method="yeo-johnson").fit_transform(df[[c]]); skewed.append(c)
                except Exception:
                    continue
        if skewed:
            log.append(f"{len(skewed)} variable(s) redressée(s).")

    # 4. ORDINAL encoding — preserve semantic order (THE FIX vs alphabetical OrdinalEncoder).
    for col, order in t["ordinale"].items():
        if col in df.columns:
            df[col] = typ.encode_ordinal(df[col], order)
            ordinal_enc.append(col)
    if ordinal_enc:
        log.append(f"{len(ordinal_enc)} ordinale(s) encodée(s) en gardant l'ordre : {', '.join(ordinal_enc[:6])}.")

    # 5. NOMINAL encoding.
    nominal = [c for c in t["nominale"] if c in df.columns]
    if nominal:
        if cfg["nominal_encoding"] == "onehot":
            max_card = int(cfg["onehot_max_cardinality"])
            oh = [c for c in nominal if df[c].nunique(dropna=True) <= max_card]
            fb = [c for c in nominal if c not in oh]
            if oh:
                df = pd.get_dummies(df, columns=oh, dummy_na=False)
                for c in df.columns:
                    if df[c].dtype == bool:
                        df[c] = df[c].astype(int)
                nominal_oh = oh
            if fb:
                enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
                df[fb] = enc.fit_transform(df[fb].astype(str)); nominal_ord = fb
                warnings.append(f"{len(fb)} nominale(s) à forte cardinalité encodée(s) en ordinal.")
            log.append(f"Nominales : {len(nominal_oh)} One-Hot, {len(nominal_ord)} ordinal (repli).")
        else:
            enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
            df[nominal] = enc.fit_transform(df[nominal].astype(str)); nominal_ord = nominal
            log.append(f"Nominales : {len(nominal)} encodée(s) en ordinal.")

    # 6. Scaling — numeric (continue + discrète) + ordinales ; jamais les indicatrices One-Hot.
    scale_cols = [c for c in (numeric_feats + ordinal_enc) if c in df.columns]
    if cfg["scaler"] != "none" and scale_cols:
        scaler = {"standard": StandardScaler, "minmax": MinMaxScaler, "robust": RobustScaler}[cfg["scaler"]]()
        df[scale_cols] = scaler.fit_transform(df[scale_cols])
        scaled = scale_cols
        log.append(f"{len(scaled)} variable(s) mise(s) à l'échelle ({cfg['scaler']}).")

    df = df.reset_index(drop=True)
    plots = []
    if make_plots:
        pre_skew = dg.skewness(df_in, target)
        plots = [_before_after_dist(df_in, df, pre_skew[0]["column"])] if pre_skew else \
                [message_plot("Transformation appliquée.")]

    result = {
        "report": {
            "Features créées": ", ".join(engineered) or "—",
            "Ordinales (ordre gardé)": len(ordinal_enc),
            "Nominales One-Hot": len(nominal_oh),
            "Variables redressées": len(skewed),
            "Mises à l'échelle": len(scaled),
            "Colonnes": f"{df_in.shape[1]} → {df.shape[1]}",
        },
        "diagnostics": {
            "engineered": engineered,
            "ordinal_encoded": ordinal_enc,
            "nominal_onehot": nominal_oh,
            "nominal_ordinal": nominal_ord,
            "skew_corrected": skewed,
            "scaled_count": len(scaled),
        },
        "counts": counts(df_in, df),
        "log": log,
        "warnings": warnings,
        "plots": plots,
    }
    return df, result


# ── local plot helpers ───────────────────────────────────────────────────
def _skew_plot(df, col):
    import matplotlib.pyplot as plt
    style_plot()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.hist(df[col].dropna(), bins=40, color="#e94560", edgecolor="#0f3460")
    ax.set_title(f"Distribution : {col}")
    fig.tight_layout()
    return fig_to_base64(fig)


def _before_after_dist(df_before, df_after, col):
    import matplotlib.pyplot as plt
    style_plot()
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    if col in df_before.columns:
        axes[0].hist(df_before[col].dropna(), bins=40, color="#0f3460", edgecolor="#eee")
    axes[0].set_title(f"{col} — avant")
    if col in df_after.columns:
        axes[1].hist(df_after[col].dropna(), bins=40, color="#e94560", edgecolor="#eee")
    axes[1].set_title(f"{col} — après")
    fig.tight_layout()
    return fig_to_base64(fig)
