"""
Tests for the deepened cleaning stage — model-based imputation (KNN / iterative),
z-score outlier handling, and the per-column data-quality diagnostic.
Dedicated module (test_api.py is at the file-size budget). No network.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.stages import clean as C  # noqa: E402
from pipeline.context import PipelineContext  # noqa: E402


def _df_with_issues(seed=0):
    rng = np.random.RandomState(seed)
    df = pd.DataFrame({
        "a": rng.normal(10, 2, 200), "b": rng.normal(5, 1, 200),
        "const": [3.0] * 200, "idcol": [f"u{i}" for i in range(200)],
        "y": (rng.rand(200) < 0.5).astype(int),
    })
    df.loc[rng.choice(200, 30, replace=False), "a"] = np.nan
    df.loc[0, "a"] = 999.0                         # a clear outlier
    return df


def test_knn_imputation_fills_all_missing():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    out, r = C.run(df, {"impute_num": "knn", "dropped_columns": []}, ctx, make_plots=False)
    assert r["report"]["Valeurs imputées"] == 30
    assert out["a"].isnull().sum() == 0


def test_iterative_imputation_fills_all_missing():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    out, r = C.run(df, {"impute_num": "iterative", "dropped_columns": []}, ctx, make_plots=False)
    assert r["report"]["Valeurs imputées"] == 30
    assert out["a"].isnull().sum() == 0


def test_zscore_clip_bounds_outlier():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    out, r = C.run(df, {"impute_num": "median", "outlier_method": "zscore_clip",
                        "outlier_k": 3.0, "dropped_columns": []}, ctx, make_plots=False)
    assert r["diagnostics"]["outliers_handled"] >= 1
    assert out["a"].max() < 999.0                  # the 999 was clipped down


def test_zscore_remove_drops_rows():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    n0 = len(df)
    out, r = C.run(df, {"impute_num": "median", "outlier_method": "zscore_remove",
                        "outlier_k": 3.0, "dropped_columns": []}, ctx, make_plots=False)
    assert len(out) < n0
    assert r["diagnostics"]["outliers_handled"] == n0 - len(out)


def test_data_quality_by_column_flags_and_order():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    rows = C.diagnose(df, ctx)["diagnostics"]["qualite_par_colonne"]
    by = {r["colonne"]: r for r in rows}
    assert "constante" in by["const"]["alertes"]
    assert "cardinalité" in by["idcol"]["alertes"]
    assert by["a"]["manquant_%"] == 15.0
    # Worst-first: a flagged column (const/idcol/a) precedes a clean-ish one.
    assert rows[0]["colonne"] in ("const", "idcol", "a")


def test_imputation_schema_offers_knn_and_iterative():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    ctrl = next(c for c in C.config_schema(df, ctx) if c["name"] == "impute_num")
    vals = {o["value"] for o in ctrl["options"]}
    assert {"knn", "iterative", "median"} <= vals
    oc = next(c for c in C.config_schema(df, ctx) if c["name"] == "outlier_method")
    assert {"zscore_clip", "zscore_remove", "iqr_clip"} <= {o["value"] for o in oc["options"]}
