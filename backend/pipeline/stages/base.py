"""
base.py — Shared helpers for stage modules.

Every stage module exposes the same contract:

    STAGE_ID, TITLE, OBJECTIVE        # metadata
    default_config(df, ctx) -> dict
    config_schema(df, ctx) -> list[control]
    diagnose(df, ctx) -> dict         # pre-run signals (fed to the LLM agent)
    run(df, config, ctx) -> (df_out, result)

`control` descriptors are consumed verbatim by the React UI to render the
expert's adjustment widgets.
"""

import numpy as np
import pandas as pd


# ── config-schema control builders ──────────────────────────────────────
def select(name, label, options, default, help=""):
    """A dropdown. `options` is a list of (value, label) tuples."""
    return {
        "name": name, "label": label, "type": "select", "default": default,
        "options": [{"value": v, "label": lbl} for v, lbl in options], "help": help,
    }


def toggle(name, label, default, help=""):
    return {"name": name, "label": label, "type": "toggle", "default": bool(default), "help": help}


def rng(name, label, minimum, maximum, step, default, help=""):
    return {
        "name": name, "label": label, "type": "range",
        "min": minimum, "max": maximum, "step": step, "default": default, "help": help,
    }


def number(name, label, default, minimum=None, maximum=None, help=""):
    return {
        "name": name, "label": label, "type": "number",
        "min": minimum, "max": maximum, "default": default, "help": help,
    }


def strategy_table(name, label, rows, options_num, options_cat, options_out, default, help=""):
    """Per-column cleaning-strategy table (imputation + outlier overrides).

    ``rows`` are per-column health dicts (metrics + ``rec_impute`` / ``rec_outliers``
    / ``raison``). The control's value is ``{"impute": {col: mode}, "outliers":
    {col: method}}`` — an empty dict means "follow the global setting".
    """
    return {"name": name, "label": label, "type": "strategy_table", "columns": rows,
            "impute_options_num": [{"value": v, "label": lbl} for v, lbl in options_num],
            "impute_options_cat": [{"value": v, "label": lbl} for v, lbl in options_cat],
            "outlier_options": [{"value": v, "label": lbl} for v, lbl in options_out],
            "default": default, "help": help}


def column_table(name, label, columns, default, help="", cols=None):
    """A per-column keep/drop table (rendered with checkboxes + per-column advice).

    `columns` is a list of row dicts (each MUST contain `column`, `recommended`, `reason`).
    `cols` optionally specifies which fields to display as `[{key, label}, ...]`; when
    omitted the UI shows the default cleaning columns. The control's value is the list
    of column names the expert chose to DROP.
    """
    ctrl = {"name": name, "label": label, "type": "column_table",
            "columns": columns, "default": default, "help": help}
    if cols:
        ctrl["cols"] = cols
    return ctrl


# ── result helpers ───────────────────────────────────────────────────────
def counts(df_in: pd.DataFrame, df_out: pd.DataFrame) -> dict:
    return {
        "rows_in": int(df_in.shape[0]), "rows_out": int(df_out.shape[0]),
        "cols_in": int(df_in.shape[1]), "cols_out": int(df_out.shape[1]),
    }


def to_native(obj):
    """Recursively convert numpy/pandas scalars to JSON-serialisable Python types."""
    if isinstance(obj, dict):
        return {str(k): to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return f if np.isfinite(f) else None
    if isinstance(obj, float):                  # plain Python float (e.g. DataFrame.to_dict on a NaN cell)
        return obj if np.isfinite(obj) else None   # NaN / inf are not JSON-compliant -> null
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [to_native(v) for v in obj.tolist()]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj
