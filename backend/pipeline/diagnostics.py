"""
diagnostics.py — Pure, deterministic diagnostics shared across stages.

These functions never mutate the dataframe. They compute the structured numeric
signals that (a) the UI displays and (b) the LLM refinement agent reasons over.
Keeping them deterministic and side-effect-free is what makes the agent's
recommendations grounded in real numbers rather than hallucinated ones.
"""

from typing import Optional

import numpy as np
import pandas as pd


def feature_columns(df: pd.DataFrame, target_col: Optional[str]):
    """Return (numeric_cols, categorical_cols) excluding the target."""
    cols = [c for c in df.columns if c != target_col]
    sub = df[cols]
    num = sub.select_dtypes(include=[np.number]).columns.tolist()
    # Everything non-numeric is treated as categorical. Robust to pandas 3.0
    # StringDtype (text columns are no longer reported as 'object').
    cat = [c for c in cols if c not in num]
    return num, cat


def _is_identifier(col) -> bool:
    """Name-based detection of identifier columns (never predictive features)."""
    c = str(col).lower()
    return c == "id" or c.endswith("_id") or c in ("client_id", "customer_id") or c.startswith("unnamed")


def identifier_columns(df: pd.DataFrame, target_col: Optional[str] = None) -> list:
    """Identifier columns present in the frame — their numeric stats are artefacts."""
    return [str(c) for c in df.columns if c != target_col and _is_identifier(c)]


def overview(df: pd.DataFrame, target_col: Optional[str]) -> dict:
    """High-level shape + missingness snapshot of the whole frame."""
    num, cat = feature_columns(df, target_col)
    total_cells = int(df.shape[0] * df.shape[1]) or 1
    missing_cells = int(df.isnull().sum().sum())
    return {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "numeric_features": len(num),
        "categorical_features": len(cat),
        "missing_pct": round(100.0 * missing_cells / total_cells, 2),
        "duplicated_rows": int(df.duplicated().sum()),
        "target_col": target_col,
    }


def missing_by_column(df: pd.DataFrame, top: int = 12) -> list:
    """Per-column missing count/pct, descending, limited to the worst `top`."""
    n = len(df) or 1
    miss = df.isnull().sum()
    miss = miss[miss > 0].sort_values(ascending=False).head(top)
    return [
        {"column": str(c), "missing": int(v), "pct": round(100.0 * int(v) / n, 1)}
        for c, v in miss.items()
    ]


def skewness(df: pd.DataFrame, target_col: Optional[str], top: int = 12) -> list:
    """Absolute skewness of numeric features, descending."""
    num, _ = feature_columns(df, target_col)
    out = []
    for c in num:
        if _is_identifier(c):
            continue  # skew on an identifier is meaningless
        s = df[c].dropna()
        if len(s) < 3 or s.nunique() < 3:
            continue
        try:
            sk = float(s.skew())
        except Exception:
            continue
        if np.isfinite(sk):
            out.append({"column": str(c), "skew": round(sk, 2), "abs_skew": round(abs(sk), 2)})
    out.sort(key=lambda d: d["abs_skew"], reverse=True)
    return out[:top]


def outliers_iqr(df: pd.DataFrame, target_col: Optional[str], k: float = 1.5, top: int = 12) -> list:
    """Count of values beyond the Tukey IQR fences, per numeric feature."""
    num, _ = feature_columns(df, target_col)
    n = len(df) or 1
    out = []
    for c in num:
        if _is_identifier(c):
            continue  # an identifier's "outliers" are an artefact, not a signal
        s = df[c].dropna()
        if s.empty:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        low, high = q1 - k * iqr, q3 + k * iqr
        cnt = int(((s < low) | (s > high)).sum())
        if cnt:
            out.append({"column": str(c), "outliers": cnt, "pct": round(100.0 * cnt / n, 1)})
    out.sort(key=lambda d: d["outliers"], reverse=True)
    return out[:top]


def cardinality(df: pd.DataFrame, target_col: Optional[str], top: int = 12) -> list:
    """Distinct-value count of categorical features, descending."""
    _, cat = feature_columns(df, target_col)
    out = [{"column": str(c), "n_unique": int(df[c].nunique(dropna=True))} for c in cat]
    out.sort(key=lambda d: d["n_unique"], reverse=True)
    return out[:top]


def constant_columns(df: pd.DataFrame, quasi_threshold: float = 0.99) -> list:
    """Columns that are constant or quasi-constant (one value dominates)."""
    out = []
    n = len(df) or 1
    for c in df.columns:
        nun = df[c].nunique(dropna=False)
        if nun <= 1:
            out.append({"column": str(c), "reason": "constant"})
            continue
        top_freq = df[c].value_counts(dropna=False, normalize=True)
        if not top_freq.empty and float(top_freq.iloc[0]) >= quasi_threshold:
            out.append({"column": str(c), "reason": f"quasi-constant ({round(float(top_freq.iloc[0]) * 100, 1)}%)"})
    return out


def high_correlation_pairs(df: pd.DataFrame, target_col: Optional[str], threshold: float = 0.9, top: int = 15) -> list:
    """Pairs of numeric features whose absolute Pearson correlation exceeds threshold."""
    num, _ = feature_columns(df, target_col)
    if len(num) < 2:
        return []
    corr = df[num].corr().abs()
    pairs = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = corr.iloc[i, j]
            if pd.notnull(v) and v >= threshold:
                pairs.append({"a": str(cols[i]), "b": str(cols[j]), "corr": round(float(v), 3)})
    pairs.sort(key=lambda d: d["corr"], reverse=True)
    return pairs[:top]


def target_correlation(df: pd.DataFrame, target_col: Optional[str], top: int = 12) -> list:
    """Absolute correlation of each numeric feature with a numeric target."""
    if target_col is None or target_col not in df.columns:
        return []
    if not pd.api.types.is_numeric_dtype(df[target_col]):
        return []
    num, _ = feature_columns(df, target_col)
    if not num:
        return []
    corr = df[num + [target_col]].corr()[target_col].drop(labels=[target_col], errors="ignore")
    corr = corr.abs().sort_values(ascending=False).head(top)
    return [{"column": str(c), "abs_corr": round(float(v), 3)} for c, v in corr.items() if pd.notnull(v)]
