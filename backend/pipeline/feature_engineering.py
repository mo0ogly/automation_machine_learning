"""
feature_engineering.py — shared feature construction (Transform stage + preprocessor).

Both the Transform stage (exploratory preview) and the leakage-free
``FeaturePreprocessor`` (the authoritative train-only path) must build the SAME
derived features, or the model would train on columns the serving path doesn't
produce. This module centralises them:

* **domain features** — guarded on known columns (Age, Renov). Stateless.
* **interactions** — products / ratios of the most informative numeric columns,
  bounded to avoid a dimensionality explosion. The *base columns* are chosen by
  variance, which is row-dependent, so the choice is FIT ON TRAIN by the
  preprocessor and reused verbatim on test/serving (``interaction_base`` →
  ``apply_interactions``). The arithmetic itself is stateless.
* **binning** — discretise continuous columns into quantile / uniform bins. The
  bin EDGES are fit on train (``fit_bin_edges``) and applied verbatim
  (``apply_bins``), so binning is leakage-free.

Everything is deterministic and dependency-free (numpy / pandas only).
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

INTERACT_MAX_BASE = 4        # -> at most C(4,2) = 6 pairs
INTERACT_MAX_NEW = 8         # hard cap on synthesised interaction columns
BIN_MAX_COLS = 5             # cap on how many columns get binned
_EPS = 1e-6


def domain_features(df: pd.DataFrame) -> tuple:
    """Guarded domain features (Age, Renov). Returns ``(df, new_names)``. Stateless."""
    eng = []
    if {"YrSold", "YearBuilt"}.issubset(df.columns):
        df["Age"] = (df["YrSold"] - df["YearBuilt"]).clip(lower=0)
        eng.append("Age")
    if {"YearBuilt", "YearRemodAdd"}.issubset(df.columns):
        df["Renov"] = (df["YearBuilt"] != df["YearRemodAdd"]).astype(int)
        eng.append("Renov")
    return df, eng


def _numeric_cols(df, target):
    return [c for c in df.columns if c != target and pd.api.types.is_numeric_dtype(df[c])]


def interaction_base(df: pd.DataFrame, target, k=INTERACT_MAX_BASE) -> list:
    """The numeric columns to combine: the top-``k`` by variance (a compact,
    informative set). Row-dependent → fit this on TRAIN and reuse it."""
    num = _numeric_cols(df, target)
    if len(num) < 2:
        return []
    var = df[num].var(numeric_only=True).sort_values(ascending=False)
    return [str(c) for c in var.index[:k]]


def apply_interactions(df: pd.DataFrame, base: list, mode: str) -> tuple:
    """Add products / ratios over the given ``base`` columns (bounded). Stateless
    given ``base``. ``mode`` ∈ {products, ratios, both}."""
    if mode not in ("products", "ratios", "both") or not base:
        return df, []
    present = [c for c in base if c in df.columns]
    new = []
    for a, b in itertools.combinations(present, 2):
        if mode in ("products", "both"):
            name = f"{a}_x_{b}"
            df[name] = pd.to_numeric(df[a], errors="coerce") * pd.to_numeric(df[b], errors="coerce")
            new.append(name)
        if mode in ("ratios", "both"):
            name = f"{a}_div_{b}"
            df[name] = pd.to_numeric(df[a], errors="coerce") / (pd.to_numeric(df[b], errors="coerce").abs() + _EPS)
            new.append(name)
        if len(new) >= INTERACT_MAX_NEW:
            break
    return df, new


def bin_candidate_cols(df: pd.DataFrame, target, k=BIN_MAX_COLS) -> list:
    """Continuous columns worth binning: top-``k`` by variance among columns with
    enough distinct values to form bins."""
    num = _numeric_cols(df, target)
    cont = [c for c in num if df[c].nunique(dropna=True) > 10]
    if not cont:
        return []
    var = df[cont].var(numeric_only=True).sort_values(ascending=False)
    return [str(c) for c in var.index[:k]]


def fit_bin_edges(df: pd.DataFrame, cols: list, n_bins: int, mode: str) -> dict:
    """Bin edges per column (open-ended), fit on the given frame. ``mode`` ∈
    {quantile, uniform}. Columns yielding fewer than 2 usable edges are skipped."""
    n_bins = max(2, int(n_bins))
    edges = {}
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(s) < n_bins:
            continue
        if mode == "uniform":
            e = np.linspace(float(s.min()), float(s.max()), n_bins + 1)
        else:
            e = np.quantile(s, np.linspace(0, 1, n_bins + 1))
        e = np.unique(e)
        if len(e) < 3:                       # degenerate (constant-ish) -> skip
            continue
        e[0], e[-1] = -np.inf, np.inf
        edges[str(c)] = e.tolist()
    return edges


def apply_bins(df: pd.DataFrame, edges: dict) -> tuple:
    """Add a ``<col>_bin`` integer index per column using the fitted ``edges``."""
    new = []
    for c, e in (edges or {}).items():
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        idx = np.digitize(s.to_numpy(dtype=float), np.asarray(e, dtype=float)[1:-1])
        name = f"{c}_bin"
        df[name] = idx.astype(int)
        new.append(name)
    return df, new
