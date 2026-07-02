"""
validation.py — dataset ingestion guardrails.

The pipeline is expert-in-the-loop and tolerant, but a genuinely degenerate
upload (empty file, one row, a target with a single class, all-missing columns)
would otherwise crash deep inside a stage with an opaque 500. This module runs a
cheap, deterministic check at ingestion and separates:

* **fatal** problems — the dataset cannot be modelled at all → the API rejects the
  upload with a clear 400 before any stage runs;
* **warnings** — the dataset is usable but has quality issues an analyst should
  know about (constant columns, heavy missingness, a near-degenerate target,
  very high cardinality, a tiny sample) → surfaced in the session payload so the
  UI can show them, with an AI helper to explain each one.

Nothing here mutates the dataframe; it only inspects and reports.
"""

from __future__ import annotations

import pandas as pd

MIN_ROWS = 5            # below this, no train/test split is meaningful
SMALL_ROWS = 30         # below this, metrics/CV are statistically shaky
HIGH_MISSING = 0.6      # a column more than this fraction empty is barely usable
HIGH_CARD = 0.9         # a categorical whose #unique/#rows exceeds this is ~an id
WIDE_COLS = 500         # beyond this many columns, warn about width/perf


def _warn(code, message, columns=None):
    w = {"code": code, "message": message}
    if columns:
        w["columns"] = list(columns)[:20]
    return w


def validate_dataset(df: pd.DataFrame, target_col: str = None) -> tuple:
    """Inspect a freshly-loaded dataframe.

    Returns ``(fatal, warnings)`` where ``fatal`` is a human string (the dataset
    must be rejected) or ``None``, and ``warnings`` is a list of ``{code, message,
    columns?}`` describing non-blocking quality issues.
    """
    if df is None or df.shape[1] == 0:
        return "Le fichier ne contient aucune colonne exploitable.", []
    n_rows, n_cols = df.shape
    if n_rows == 0:
        return "Le fichier ne contient aucune ligne de données.", []
    if n_rows < MIN_ROWS:
        return (f"Trop peu de lignes ({n_rows}) : au moins {MIN_ROWS} sont nécessaires "
                "pour construire un modèle."), []

    warnings = []

    # Duplicate column names — pandas keeps both but downstream indexing breaks.
    dupes = df.columns[df.columns.duplicated()].unique().tolist()
    if dupes:
        warnings.append(_warn("duplicate_columns",
                              f"{len(dupes)} nom(s) de colonne en double : les doublons seront "
                              "distingués automatiquement, mais renommez-les pour plus de clarté.",
                              dupes))

    # Tiny sample — usable but unreliable.
    if n_rows < SMALL_ROWS:
        warnings.append(_warn("small_sample",
                              f"Échantillon réduit ({n_rows} lignes) : les métriques et la "
                              "validation croisée seront peu fiables (viser >= 30)."))

    # Very wide.
    if n_cols > WIDE_COLS:
        warnings.append(_warn("very_wide",
                              f"Jeu très large ({n_cols} colonnes) : envisagez une sélection de "
                              "variables (étape Intégration) pour accélérer et stabiliser."))

    # Constant columns — carry no information.
    const_cols = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
    if const_cols:
        warnings.append(_warn("constant_columns",
                              f"{len(const_cols)} colonne(s) constante(s) (une seule valeur) : "
                              "sans information prédictive, à retirer.", const_cols))

    # Heavy missingness.
    miss = df.isna().mean()
    heavy = [c for c in df.columns if float(miss.get(c, 0)) > HIGH_MISSING]
    if heavy:
        warnings.append(_warn("heavy_missing",
                              f"{len(heavy)} colonne(s) à plus de {int(HIGH_MISSING * 100)}% de "
                              "valeurs manquantes : l'imputation sera peu fiable.", heavy))

    # High-cardinality categoricals (likely identifiers).
    id_like = []
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        nun = df[c].nunique(dropna=True)
        if n_rows and nun / n_rows > HIGH_CARD and nun > 20:
            id_like.append(c)
    if id_like:
        warnings.append(_warn("high_cardinality",
                              f"{len(id_like)} colonne(s) catégorielle(s) à très forte cardinalité "
                              "(proche d'un identifiant) : peu utiles, souvent à retirer.", id_like))

    # Target-specific checks (when a target is known at ingestion).
    if target_col and target_col in df.columns:
        y = df[target_col].dropna()
        if len(y) == 0:
            return f"La cible « {target_col} » est entièrement vide.", warnings
        nun = y.nunique()
        if nun <= 1:
            return (f"La cible « {target_col} » ne contient qu'une seule valeur : "
                    "impossible d'apprendre à distinguer des cas."), warnings
        if not pd.api.types.is_numeric_dtype(y) or nun <= 20:
            vc = y.value_counts()
            if vc.min() < 2:
                rare = [str(k) for k, v in vc.items() if v < 2]
                warnings.append(_warn("rare_class",
                                      f"{len(rare)} classe(s) de la cible n'ont qu'un seul exemple : "
                                      "la stratification et la validation croisée seront limitées.",
                                      rare))

    return None, warnings
