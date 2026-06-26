"""
typology.py — 4-way variable typology.

Features are classified into four families and each is treated differently:

    col_quant  -> quantitative continue   (numeric, many distinct values)
    col_scred  -> quantitative discrète    (numeric, few distinct values)
    col_cat    -> catégorielle NOMINALE    (no order  -> One-Hot)
    col_ord    -> catégorielle ORDINALE    (ordered   -> ranked integers)

The critical correctness point: an ORDINAL column (quality grade Po<Fa<TA<Gd<Ex)
must be encoded preserving its order, not with an arbitrary alphabetical
``OrdinalEncoder``. This module detects ordinals via known vocabularies and
encodes them exactly like the ordered ``qual_map`` (NA/absent -> 0).
"""

import pandas as pd

# Known ordinal vocabularies, ordered low -> high. Absent / NA / None -> 0.
ORDINAL_VOCABS = [
    ["Po", "Fa", "TA", "Gd", "Ex"],                       # Ames quality grades
    ["Low", "Medium", "High"],
    ["Poor", "Fair", "Good", "Very Good", "Excellent"],
]

# Numeric column with more than this many distinct values -> continue, else discrète.
DISCRETE_MAX_UNIQUE = 15

_ABSENT = {"NA", "None", "nan", "NaN", ""}


def _match_vocab(values):
    """Return the ordered vocab if all (non-absent) values belong to one, else None."""
    vals = {str(v) for v in values if str(v) not in _ABSENT}
    for vocab in ORDINAL_VOCABS:
        if vals and vals <= set(vocab):
            return vocab
    return None


def classify(df: pd.DataFrame, target_col=None, ordinal_overrides=None) -> dict:
    """
    Classify each feature (excluding the target) into the four families.

    ``ordinal_overrides``: optional ``{column: [ordered values]}`` supplied by the
    expert to force a column to be ordinal with a specific order.

    Returns ``{"continue": [...], "discrete": [...], "nominale": [...],
               "ordinale": {col: [ordered values]}}``.
    """
    ordinal_overrides = ordinal_overrides or {}
    out = {"continue": [], "discrete": [], "nominale": [], "ordinale": {}}
    for c in df.columns:
        if c == target_col:
            continue
        if c in ordinal_overrides:
            out["ordinale"][str(c)] = list(ordinal_overrides[c])
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            n_unique = df[c].nunique(dropna=True)
            bucket = "discrete" if n_unique <= DISCRETE_MAX_UNIQUE else "continue"
            out[bucket].append(str(c))
        else:
            order = _match_vocab(df[c].dropna().unique())
            if order is not None:
                out["ordinale"][str(c)] = order
            else:
                out["nominale"].append(str(c))
    return out


def encode_ordinal(series: pd.Series, order) -> pd.Series:
    """Map an ordinal column to ranked integers (1..n); absent/unknown -> 0.

    Uses the ordered map ``qual_map = {"NA":0,"Po":1,"Fa":2,"TA":3,"Gd":4,"Ex":5}``.
    """
    rank = {str(v): i + 1 for i, v in enumerate(order)}
    return series.astype(str).map(rank).fillna(0).astype(float)


def summary_rows(typ: dict) -> list:
    """Compact view for the UI diagnostics (one row per family)."""
    rows = []
    families = [
        ("Quantitative continue", typ["continue"]),
        ("Quantitative discrète", typ["discrete"]),
        ("Catégorielle nominale", typ["nominale"]),
        ("Catégorielle ordinale", list(typ["ordinale"].keys())),
    ]
    for label, cols in families:
        if cols:
            rows.append({"type": label, "count": len(cols), "exemples": ", ".join(cols[:5])})
    return rows
