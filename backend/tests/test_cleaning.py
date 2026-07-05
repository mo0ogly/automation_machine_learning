"""
Tests for the deepened cleaning stage — model-based imputation (KNN / iterative),
z-score outlier handling, the per-column data-quality diagnostic, and the
leakage-free path (CleanPreprocessor fit on train only, applied to test/serving).
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


# ── per-column strategies (P1): overrides + recommendations ─────────────────
def _df_two_gaps(seed=3):
    rng = np.random.RandomState(seed)
    df = pd.DataFrame({
        "a": rng.normal(10, 2, 200), "b": rng.normal(50, 5, 200),
        "y": (rng.rand(200) < 0.5).astype(int),
    })
    df.loc[rng.choice(200, 20, replace=False), "a"] = np.nan
    df.loc[rng.choice(200, 20, replace=False), "b"] = np.nan
    return df


def test_per_column_impute_override():
    df = _df_two_gaps()
    ctx = PipelineContext.from_df(df)
    med_a, mean_b = df["a"].median(), df["b"].mean()
    out, _r = C.run(df, {"impute_num": "median", "dropped_columns": [],
                         "drop_duplicates": False,
                         "column_strategies": {"impute": {"b": "mean"}}},
                    ctx, make_plots=False)
    assert out["a"].isnull().sum() == 0 and out["b"].isnull().sum() == 0
    # b was filled with its MEAN (override), a with its MEDIAN (global).
    assert (out["b"] == mean_b).sum() >= 20
    assert (out["a"] == med_a).sum() >= 20


def test_per_column_outlier_override():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    b_max = float(df["b"].max())
    out, _r = C.run(df, {"impute_num": "median", "outlier_method": "none",
                         "dropped_columns": [],
                         "column_strategies": {"outliers": {"a": "iqr_clip"}}},
                    ctx, make_plots=False)
    assert float(out["a"].max()) < 999.0          # a clipped by its override
    assert float(out["b"].max()) == b_max          # b untouched (global = none)


def test_clean_preprocessor_honors_column_overrides():
    df = _df_two_gaps()
    tr, te = df.iloc[:150].copy(), df.iloc[150:].copy()
    cp = C.CleanPreprocessor({"impute_num": "median",
                              "column_strategies": {"impute": {"b": "mean"}}}, "y").fit(tr)
    out = cp.transform(te)
    na_b = te["b"].isna()
    na_a = te["a"].isna()
    assert (out.loc[na_b, "b"] == float(tr["b"].mean())).all()    # train MEAN (override)
    assert (out.loc[na_a, "a"] == float(tr["a"].median())).all()  # train MEDIAN (global)


def test_schema_exposes_strategy_table_with_recommendations():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    ctrl = next(c for c in C.config_schema(df, ctx) if c["type"] == "strategy_table")
    assert ctrl["name"] == "column_strategies"
    assert {o["value"] for o in ctrl["impute_options_num"]} >= {"", "median", "knn"}
    by = {r["colonne"]: r for r in ctrl["columns"]}
    assert by["a"]["rec_impute"] == "knn"          # 15% missing, 3+ numeric columns
    assert by["a"]["rec_outliers"] is None or by["a"]["rec_outliers"] == "iqr_clip"
    assert by["a"]["raison"] != "—"


# ── leakage-free path: clean statistics fit on TRAIN only ───────────────────
def test_run_stats_false_skips_imputation_and_outliers():
    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    out, _r = C.run(df, {"impute_num": "median", "outlier_method": "iqr_clip",
                         "dropped_columns": []}, ctx, make_plots=False, stats=False)
    assert out["a"].isnull().sum() == 30           # imputation skipped
    assert float(out["a"].max()) == 999.0          # clipping skipped


def test_clean_preprocessor_uses_train_statistics_on_test():
    rng = np.random.RandomState(1)
    tr = pd.DataFrame({"a": rng.normal(10, 2, 100), "b": rng.normal(5, 1, 100),
                       "cat": ["x"] * 60 + ["y"] * 40,
                       "y": (rng.rand(100) < 0.5).astype(int)})
    te = pd.DataFrame({"a": [np.nan, 500.0], "b": [np.nan, 5.0],
                       "cat": [None, "z"], "y": [0, 1]})
    cp = C.CleanPreprocessor({"impute_num": "median", "impute_cat": "most_frequent",
                              "outlier_method": "iqr_clip", "outlier_k": 1.5}, "y").fit(tr)
    out = cp.transform(te)
    assert len(out) == 2                            # test/serving rows never dropped
    assert out.loc[0, "a"] == tr["a"].median()      # TRAIN median, not the test frame's
    assert out.loc[0, "b"] == tr["b"].median()
    assert out.loc[0, "cat"] == "x"                 # TRAIN mode
    low, high, action = cp.bounds_["a"]
    assert action == "clip"
    assert out.loc[1, "a"] == high                  # clipped to TRAIN bounds
    assert (out["y"] == te["y"]).all()              # target untouched


def test_clean_preprocessor_remove_drops_train_rows_only():
    df = _df_with_issues()
    cp = C.CleanPreprocessor({"impute_num": "median", "outlier_method": "zscore_remove",
                              "outlier_k": 3.0}, "y").fit(df)
    tr_out = cp.transform(df, training=True)
    te_out = cp.transform(df)
    assert len(tr_out) < len(df)                    # the 999 outlier row leaves the train
    assert len(te_out) == len(df)                   # ...but never the test/serving rows


class _FakeRun:
    def __init__(self, config=None, output_df=None):
        self.config = config or {}
        self.output_df = output_df
        self.artifacts = {}
        self.stale = False


class _FakeSession:
    """Just enough session for separate.run's leakage-free path."""

    def __init__(self, raw_df, clean_cfg):
        self.raw_df = raw_df
        self._clean = _FakeRun(clean_cfg, raw_df)

    def get_run(self, stage_id):
        return self._clean if stage_id == "clean" else None


def test_separate_refits_clean_statistics_on_train_only():
    from sklearn.model_selection import train_test_split
    from pipeline.stages import separate as S

    df = _df_with_issues()
    ctx = PipelineContext.from_df(df)
    clean_cfg = {"impute_num": "median", "dropped_columns": ["idcol", "const"]}
    session = _FakeSession(df, clean_cfg)
    _out, result, art = S.run(df, {"target_col": "y"}, ctx, session=session)

    cp = art["clean_preprocessor"]
    assert cp is not None and art["preprocessor"] is not None
    assert not art["X_train"].isnull().to_numpy().any()
    assert not art["X_test"].isnull().to_numpy().any()

    # The imputation value must be the TRAIN partition's median — replay the
    # exact same structural clean + split (same stratification) and compare.
    base, _ = C.run(df, clean_cfg, ctx, make_plots=False, stats=False)
    base = base[base["y"].notna()].reset_index(drop=True)
    strat = base["y"] if result["diagnostics"]["stratified"] else None
    tr, _te = train_test_split(base, test_size=0.25, random_state=42,
                               shuffle=True, stratify=strat)
    assert cp.num_fill_["a"] == float(tr["a"].median())
