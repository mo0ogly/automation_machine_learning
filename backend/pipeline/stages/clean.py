"""
clean.py — Stage 1 : NETTOYAGE.

Cleaning section:
- COLUMN SELECTION (`colonne_a_garder`) — the expert decides, column by column,
  which columns stay or go. A per-column table gives a recommendation + reason,
  but the final choice is the expert's (checkboxes in the UI).
- ORDINAL NORMALIZATION (`qual_map`) — quality grades are mapped onto an ordered
  numeric scale (absent=0, Po=1, Fa=2, TA=3, Gd=4, Ex=5), and the mapping is shown.
- Missing-value imputation, outlier handling, univariate row exclusion, dedup.
For supervised problems, rows with a missing target are dropped.
"""

import numpy as np
import pandas as pd

from .. import diagnostics as dg
from .. import typology as typ
from ..plotting import style_plot, fig_to_base64, message_plot
from .base import select, toggle, rng, number, column_table, counts

STAGE_ID = "clean"
TITLE = "Nettoyage"
OBJECTIVE = "Rendre les données fiables : choix des colonnes, normalisation, manquants, doublons, aberrants."

_TYPE_REASON = {
    "Quantitative continue": "Variable numérique continue",
    "Quantitative discrète": "Compte / variable discrète",
    "Catégorielle nominale": "Catégorie (sans ordre)",
    "Catégorielle ordinale": "Note de qualité ordonnée",
}


def column_analysis(df, ctx):
    """Per-column table: (rows, recommended_drops). The 'avis + pourquoi' per column."""
    target = ctx.target_col
    t = typ.classify(df, target)
    ords, noms = set(t["ordinale"].keys()), set(t["nominale"])
    conts, discs = set(t["continue"]), set(t["discrete"])
    ids = set(dg.identifier_columns(df, target))
    consts = {c["column"]: c["reason"] for c in dg.constant_columns(df)}
    n = len(df) or 1

    rows, recommended_drop = [], []
    for c in df.columns:
        miss_pct = round(100.0 * int(df[c].isnull().sum()) / n, 1)
        if c == target:
            tlabel = "Cible"
        elif c in ids:
            tlabel = "Identifiant"
        elif c in ords:
            tlabel = "Catégorielle ordinale"
        elif c in noms:
            tlabel = "Catégorielle nominale"
        elif c in discs:
            tlabel = "Quantitative discrète"
        elif c in conts:
            tlabel = "Quantitative continue"
        else:
            tlabel = "Autre"

        if c == target:
            rec, reason = "garder", "Variable cible — indispensable"
        elif c in ids:
            rec, reason = "retirer", "Identifiant — non prédictif"
        elif miss_pct >= 100:
            rec, reason = "retirer", "Entièrement vide (100% manquant)"
        elif miss_pct > 50:
            rec, reason = "retirer", f"Trop incomplète ({miss_pct}% manquant)"
        elif c in consts:
            rec, reason = "retirer", consts[c]
        else:
            rec = "garder"
            reason = _TYPE_REASON.get(tlabel, "Variable exploitable")
            if miss_pct > 0:
                reason += f" — {miss_pct}% manquant à imputer"

        if rec == "retirer" and c != target:
            recommended_drop.append(str(c))
        rows.append({"column": str(c), "type": tlabel, "missing_pct": miss_pct,
                     "n_unique": int(df[c].nunique(dropna=True)), "recommended": rec, "reason": reason})
    return rows, recommended_drop


def default_config(df, ctx):
    _, rec_drop = column_analysis(df, ctx)
    return {
        "dropped_columns": rec_drop,
        "normalize_ordinals": True,
        "impute_num": "median",
        "impute_cat": "constant",
        "outlier_method": "none",
        "outlier_k": 1.5,
        "exclude_column": "",
        "exclude_op": ">",
        "exclude_value": 0.0,
        "drop_duplicates": True,
    }


def config_schema(df, ctx):
    rows, rec_drop = column_analysis(df, ctx)
    num_cols, _ = dg.feature_columns(df, ctx.target_col)
    ids = set(dg.identifier_columns(df, ctx.target_col))
    drop_set = set(rec_drop)
    miss = df.isnull().mean()
    # Only offer columns we actually keep: numeric, non-identifier, not mostly-missing,
    # and not recommended for removal — excluding rows by a column you drop is pointless.
    usable = [c for c in num_cols
              if c not in ids and c not in drop_set and float(miss.get(c, 0)) < 0.5]
    col_options = [("", "(aucune)")] + [(c, c) for c in usable]
    return [
        column_table("dropped_columns", "Colonnes — vous décidez qui reste", rows, rec_drop,
                     "Cochez « Garder » ou « Retirer » pour chaque colonne. L'avis et la raison sont indicatifs."),
        toggle("normalize_ordinals", "Normaliser les notes de qualité (ordinales)", True,
               "Mappe les notes ordonnées sur une échelle : absent=0, Po=1, Fa=2, TA=3, Gd=4, Ex=5."),
        select("impute_num", "Imputation numérique",
               [("median", "Médiane"), ("mean", "Moyenne"), ("zero", "Zéro"), ("drop_rows", "Supprimer les lignes")],
               "median", "Remplissage des trous numériques."),
        select("impute_cat", "Imputation catégorielle",
               [("constant", 'Constante ("None" = absence)'), ("most_frequent", "Modalité la plus fréquente"),
                ("drop_rows", "Supprimer les lignes")],
               "constant", "Remplissage des trous catégoriels (« None » = absence)."),
        select("outlier_method", "Valeurs aberrantes",
               [("none", "Ne rien faire"), ("iqr_clip", "Borner (IQR)"), ("iqr_remove", "Supprimer (IQR)")],
               "none", "Traitement des valeurs hors bornes de Tukey."),
        rng("outlier_k", "Facteur IQR (k)", 1.0, 3.0, 0.5, 1.5, "Bornes Q1−k·IQR à Q3+k·IQR."),
        select("exclude_column", "Exclusion univariée — colonne", col_options, "",
               "Exclure des lignes selon une variable (ex. GrLivArea > 4000)."),
        select("exclude_op", "Exclusion — opérateur",
               [(">", "supérieur à"), ("<", "inférieur à"), (">=", "≥"), ("<=", "≤")], ">", ""),
        number("exclude_value", "Exclusion — seuil", 0.0, None, None, "Les lignes vérifiant la condition sont exclues."),
        toggle("drop_duplicates", "Supprimer les doublons", True, "Retire les lignes strictement identiques."),
    ]


def _categorical_values(df, max_cols=12, max_vals=12):
    """Distinct values of each categorical column."""
    rows = []
    cat_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    for c in cat_cols[:max_cols]:
        vals = sorted(df[c].dropna().astype(str).unique().tolist())
        shown = ", ".join(vals[:max_vals]) + ("…" if len(vals) > max_vals else "")
        rows.append({"colonne": str(c), "n_distinct": int(df[c].nunique(dropna=True)), "valeurs": shown})
    return rows


def _extreme_rows(df, target, n=5, max_feats=4):
    """Rows with the largest target value (anomaly spotting)."""
    if not target or target not in df.columns or not pd.api.types.is_numeric_dtype(df[target]):
        return []
    num = [c for c in df.columns if c != target and pd.api.types.is_numeric_dtype(df[c])]
    if not num:
        return []
    var = df[num].var(numeric_only=True).sort_values(ascending=False)
    cols = [target] + list(var.index[:max_feats])
    out = []
    for _, r in df.nlargest(n, target)[cols].iterrows():
        out.append({str(k): (round(float(r[k]), 2) if pd.notna(r[k]) else None) for k in cols})
    return out


def diagnose(df, ctx):
    plots = []
    miss = dg.missing_by_column(df)
    if miss:
        style_plot()
        fig, _ax = plt_bar([m["column"] for m in miss], [m["pct"] for m in miss],
                           "Valeurs manquantes par colonne (%)")
        plots.append(fig_to_base64(fig))
    else:
        plots.append(message_plot("Aucune valeur manquante détectée."))
    # The per-column keep/drop decision lives in the config table (config_schema),
    # so it is not duplicated here as a read-only diagnostic.
    return {
        "diagnostics": {
            "overview": dg.overview(df, ctx.target_col),
            "typologie": typ.summary_rows(typ.classify(df, ctx.target_col)),
            "missing_by_column": miss,
            "outliers_iqr": dg.outliers_iqr(df, ctx.target_col),
            "valeurs_categorielles": _categorical_values(df),
            "lignes_extremes": _extreme_rows(df, ctx.target_col),
        },
        "plots": plots,
    }


def run(df, config, ctx, make_plots=True):
    cfg = {**default_config(df, ctx), **(config or {})}
    df_in = df
    df = df.copy()
    log, warnings = [], []
    target = ctx.target_col

    # 0. Supervised: drop rows with a missing target.
    if ctx.supervised and target in df.columns:
        before = len(df)
        df = df[df[target].notna()]
        if before - len(df):
            log.append(f"{before - len(df)} ligne(s) sans cible supprimée(s).")

    # 1. COLUMN SELECTION — drop exactly the columns the expert chose (never the target).
    to_drop = [c for c in (cfg.get("dropped_columns") or []) if c in df.columns and c != target]
    if to_drop:
        df = df.drop(columns=to_drop)
        shown = ", ".join(map(str, to_drop[:8])) + ("…" if len(to_drop) > 8 else "")
        log.append(f"{len(to_drop)} colonne(s) retirée(s) : {shown}.")

    # 2. ORDINAL NORMALIZATION — quality grades to an ordered numeric scale (qual_map).
    t = typ.classify(df, target)
    ordinal_display = []
    if cfg.get("normalize_ordinals", True):
        for col, order in t["ordinale"].items():
            if col in df.columns:
                df[col] = typ.encode_ordinal(df[col], order)
                echelle = "absent=0, " + ", ".join(f"{v}={i + 1}" for i, v in enumerate(order))
                ordinal_display.append({"colonne": str(col), "echelle": echelle})
        if ordinal_display:
            log.append(f"{len(ordinal_display)} note(s) de qualité normalisée(s) (échelle ordonnée).")

    num_cols, cat_cols = dg.feature_columns(df, target)

    # 3. Numeric imputation.
    imputed_num = 0
    if cfg["impute_num"] == "drop_rows":
        before = len(df)
        df = df.dropna(subset=num_cols)
        log.append(f"{before - len(df)} ligne(s) supprimée(s) (NaN numériques).")
    else:
        for c in num_cols:
            n_na = int(df[c].isnull().sum())
            if not n_na:
                continue
            val = df[c].median() if cfg["impute_num"] == "median" else \
                df[c].mean() if cfg["impute_num"] == "mean" else 0
            df[c] = df[c].fillna(val)
            imputed_num += n_na
        if imputed_num:
            log.append(f"{imputed_num} valeur(s) numérique(s) imputée(s) ({cfg['impute_num']}).")

    # 4. Categorical imputation (NA = absence -> "None").
    imputed_cat = 0
    if cfg["impute_cat"] == "drop_rows":
        before = len(df)
        df = df.dropna(subset=cat_cols)
        log.append(f"{before - len(df)} ligne(s) supprimée(s) (NaN catégoriels).")
    else:
        for c in cat_cols:
            n_na = int(df[c].isnull().sum())
            if not n_na:
                continue
            if cfg["impute_cat"] == "most_frequent":
                mode = df[c].mode(dropna=True)
                val = mode.iloc[0] if not mode.empty else "None"
            else:
                val = "None"
            df[c] = df[c].fillna(val)
            imputed_cat += n_na
        if imputed_cat:
            log.append(f"{imputed_cat} valeur(s) catégorielle(s) imputée(s) ({cfg['impute_cat']}).")

    # 5. Outliers (numeric features only).
    outliers_handled = 0
    if cfg["outlier_method"] != "none":
        k = float(cfg["outlier_k"])
        if cfg["outlier_method"] == "iqr_clip":
            for c in num_cols:
                s = df[c]
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                iqr = q3 - q1
                if iqr == 0:
                    continue
                low, high = q1 - k * iqr, q3 + k * iqr
                outliers_handled += int(((s < low) | (s > high)).sum())
                df[c] = s.clip(low, high)
            log.append(f"{outliers_handled} valeur(s) bornée(s) (IQR k={k}).")
        else:
            mask = pd.Series(True, index=df.index)
            for c in num_cols:
                s = df[c]
                q1, q3 = s.quantile(0.25), s.quantile(0.75)
                iqr = q3 - q1
                if iqr == 0:
                    continue
                mask &= s.between(q1 - k * iqr, q3 + k * iqr)
            outliers_handled = int((~mask).sum())
            df = df[mask]
            log.append(f"{outliers_handled} ligne(s) aberrante(s) supprimée(s) (IQR k={k}).")

    # 5b. Univariate row exclusion (expert-driven, e.g. GrLivArea > 4000).
    excl_col = cfg.get("exclude_column") or ""
    excluded = 0
    if excl_col and excl_col in df.columns:
        op = cfg.get("exclude_op", ">")
        val = float(cfg.get("exclude_value", 0))
        s = df[excl_col]
        cond = {">": s > val, "<": s < val, ">=": s >= val, "<=": s <= val}.get(op, s > val)
        excluded = int(cond.sum())
        if excluded:
            df = df[~cond]
            log.append(f"{excluded} ligne(s) exclue(s) ({excl_col} {op} {val}).")

    # 6. Duplicates.
    dup_removed = 0
    if cfg["drop_duplicates"]:
        before = len(df)
        df = df.drop_duplicates()
        dup_removed = before - len(df)
        if dup_removed:
            log.append(f"{dup_removed} doublon(s) supprimé(s).")

    df = df.reset_index(drop=True)
    after = dg.overview(df, target)
    if after["missing_pct"] > 0:
        warnings.append(f"Il reste {after['missing_pct']}% de valeurs manquantes.")

    plots = []
    if make_plots:
        style_plot()
        plots = [fig_to_base64(_before_after_missing(df_in, df, target))]

    result = {
        "report": {
            "Lignes": f"{df_in.shape[0]} → {df.shape[0]}",
            "Colonnes": f"{df_in.shape[1]} → {df.shape[1]}",
            "Colonnes retirées": len(to_drop),
            "Ordinales normalisées": len(ordinal_display),
            "Valeurs imputées": imputed_num + imputed_cat,
            "Doublons retirés": dup_removed,
            "Manquant restant": f"{after['missing_pct']}%",
        },
        "diagnostics": {
            "overview_after": after,
            "columns_dropped": to_drop,
            "normalisation_ordinale": ordinal_display,
            "imputed_numeric": imputed_num,
            "imputed_categorical": imputed_cat,
            "duplicates_removed": dup_removed,
            "outliers_handled": outliers_handled,
        },
        "counts": counts(df_in, df),
        "log": log,
        "warnings": warnings,
        "plots": plots,
    }
    return df, result


# ── local plot helpers ───────────────────────────────────────────────────
def plt_bar(labels, values, title):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, max(2.5, 0.35 * len(labels) + 1)))
    ax.barh(labels[::-1], values[::-1], color="#e94560", edgecolor="#0f3460")
    ax.set_title(title)
    fig.tight_layout()
    return fig, ax


def _before_after_missing(df_before, df_after, target):
    import matplotlib.pyplot as plt
    nb = 100 * df_before.isnull().sum().sum() / max(1, df_before.size)
    na = 100 * df_after.isnull().sum().sum() / max(1, df_after.size)
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.bar(["Avant", "Après"], [nb, na], color=["#0f3460", "#e94560"], edgecolor="#eee")
    ax.set_ylabel("% cellules manquantes")
    ax.set_title("Nettoyage : manquant global")
    for i, v in enumerate([nb, na]):
        ax.text(i, v, f"{v:.1f}%", ha="center", va="bottom", color="#eee")
    fig.tight_layout()
    return fig
