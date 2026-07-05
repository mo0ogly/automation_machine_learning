"""
preprocessing.py — Train-only-fit feature preprocessing (leakage-free path).

Replays the semantics of the Transform and Integrate stages as a single
``FeaturePreprocessor`` with a scikit-learn-like ``fit`` / ``transform`` split:

    fit(df_train)   learns every data-dependent parameter on the TRAIN partition
                    only — skew transformers, one-hot categories, scaler statistics,
                    PCA components. Ordinal maps and engineered features are
                    stateless (vocabulary-driven), the dropped-feature list comes
                    from the expert's Integrate config.
    transform(df)   applies the fitted parameters to any frame (train, test, or
                    serving rows) WITHOUT re-fitting.

This is what removes the preprocessing leakage of the exploratory path (where
transformers are fit on the full frame before the split, see the note in
``stages/transform.py``): the Separation stage splits first, fits this object on
the train rows, and applies it to the test rows. The fitted object is stored in
the session artefacts and reused verbatim by the serving layer (``scoring.py``)
and the model export, so serving can never drift from training.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sklearn.decomposition import PCA
from sklearn.preprocessing import (
    StandardScaler, MinMaxScaler, RobustScaler, OrdinalEncoder, PowerTransformer,
)

from . import typology as typ
from . import feature_engineering as fe

_SCALERS = {"standard": StandardScaler, "minmax": MinMaxScaler, "robust": RobustScaler}


# Domain / interaction / binning feature construction is shared with the Transform
# stage via pipeline.feature_engineering; the preprocessor fits the interaction base
# and bin edges on TRAIN and reuses them on test/serving (see _build_features).


class FeaturePreprocessor:
    """Transform + Integrate semantics with parameters learned on the train split only.

    Parameters
    ----------
    transform_cfg / integrate_cfg : the stage configs the expert validated in the UI.
    target_col : excluded from the feature matrix (may be absent from served rows).
    """

    def __init__(self, transform_cfg: dict, integrate_cfg: dict, target_col=None,
                 problem_type=None):
        self.transform_cfg = dict(transform_cfg or {})
        self.integrate_cfg = dict(integrate_cfg or {})
        self.target_col = target_col
        self.problem_type = problem_type
        self.fitted_ = False
        # Learned state
        self.typology_ = None
        self.skew_cols_ = []            # [(col, "log1p" | PowerTransformer)]
        self.onehot_categories_ = {}    # col -> [train categories]
        self.highcard_encoder_ = None   # fitted OrdinalEncoder for high-cardinality nominals
        self.highcard_cols_ = []
        self.ordinal_nominal_encoder_ = None  # when nominal_encoding == "ordinal"
        self.nominal_cols_ = []
        self.scaler_ = None
        self.scale_cols_ = []
        self.pca_ = None
        self.pca_input_cols_ = []
        self.selected_features_ = None  # univariate selection result (train-fitted)
        # Feature construction fit on train, reused on test/serving (leakage-free):
        self.interaction_base_ = []     # numeric columns combined into interactions
        self.bin_edges_ = {}            # {col: edges} for binning
        self.feature_names_ = []

    def _build_features(self, df, fitting: bool):
        """Domain features + (optional) interactions + (optional) binning.

        On ``fitting`` the interaction base columns and bin edges are chosen from
        this (train) frame and stored; otherwise the stored ones are reused — so
        the same derived columns appear on train, test and serving."""
        cfg = self.transform_cfg
        df, _dom = fe.domain_features(df)
        imode = str(cfg.get("interactions", "none"))
        if imode in ("products", "ratios", "both"):
            if fitting:
                self.interaction_base_ = fe.interaction_base(df, self.target_col)
            df, _ = fe.apply_interactions(df, self.interaction_base_, imode)
        bmode = str(cfg.get("binning", "none"))
        if bmode in ("quantile", "uniform"):
            if fitting:
                cols = fe.bin_candidate_cols(df, self.target_col)
                self.bin_edges_ = fe.fit_bin_edges(df, cols, int(cfg.get("n_bins", 5)), bmode)
            df, _ = fe.apply_bins(df, self.bin_edges_)
        return df

    # ── fit ──────────────────────────────────────────────────────────────
    def fit(self, df: pd.DataFrame, y=None) -> "FeaturePreprocessor":
        cfg = self.transform_cfg
        df = df.copy()
        df = self._build_features(df, fitting=True)
        t = typ.classify(df, self.target_col, ordinal_overrides=cfg.get("ordinal_overrides"))
        self.typology_ = t
        numeric = [c for c in (t["continue"] + t["discrete"]) if c in df.columns]

        # 1. Skew correction: choose the columns AND fit the transformers on train.
        self.skew_cols_ = []
        if cfg.get("skew_correction"):
            thr = float(cfg.get("skew_threshold", 1.0))
            for c in numeric:
                s = df[c].dropna()
                if len(s) < 3 or s.nunique() < 3:
                    continue
                try:
                    sk = float(s.skew())
                except Exception:
                    continue
                if not np.isfinite(sk) or abs(sk) < thr:
                    continue
                if cfg.get("skew_method") == "log1p" and (df[c].dropna() >= 0).all():
                    df[c] = np.log1p(df[c])
                    self.skew_cols_.append((c, "log1p"))
                else:
                    try:
                        pt = PowerTransformer(method="yeo-johnson")
                        df[c] = pt.fit_transform(df[[c]])
                        self.skew_cols_.append((c, pt))
                    except Exception:
                        continue

        # 2. Ordinal encoding (vocabulary-driven, no statistics to leak).
        for col, order in t["ordinale"].items():
            if col in df.columns:
                df[col] = typ.encode_ordinal(df[col], order)
        ordinal_cols = [c for c in t["ordinale"] if c in df.columns]

        # 3. Nominal encoding: one-hot categories / high-cardinality fallback fit on train.
        self.nominal_cols_ = [c for c in t["nominale"] if c in df.columns]
        self.onehot_categories_ = {}
        self.highcard_cols_, self.highcard_encoder_ = [], None
        self.ordinal_nominal_encoder_ = None
        if self.nominal_cols_:
            if cfg.get("nominal_encoding", "onehot") == "onehot":
                max_card = int(cfg.get("onehot_max_cardinality", 12))
                oh = [c for c in self.nominal_cols_ if df[c].nunique(dropna=True) <= max_card]
                self.highcard_cols_ = [c for c in self.nominal_cols_ if c not in oh]
                for c in oh:
                    self.onehot_categories_[c] = sorted(df[c].dropna().astype(str).unique().tolist())
                if self.highcard_cols_:
                    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
                    enc.fit(df[self.highcard_cols_].astype(str))
                    self.highcard_encoder_ = enc
            else:
                enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
                enc.fit(df[self.nominal_cols_].astype(str))
                self.ordinal_nominal_encoder_ = enc
        df = self._encode_nominals(df)

        # 4. Integrate: expert-dropped features (static list from the validated config).
        dropped = set(self.integrate_cfg.get("dropped_features") or [])
        df = df.drop(columns=[c for c in dropped if c in df.columns])

        # 5. Scaling: statistics fit on train (numeric + ordinal; never one-hot dummies).
        self.scale_cols_ = [c for c in (numeric + ordinal_cols)
                            if c in df.columns and c not in dropped]
        scaler_kind = cfg.get("scaler", "standard")
        self.scaler_ = None
        if scaler_kind != "none" and self.scale_cols_:
            self.scaler_ = _SCALERS.get(scaler_kind, StandardScaler)()
            df[self.scale_cols_] = self.scaler_.fit_transform(df[self.scale_cols_])

        feats = [c for c in df.columns if c != self.target_col]

        # 6a. Optional univariate feature selection, fit on the TRAIN matrix only
        # (leakage-free): keep the top-k features by ANOVA F-test / mutual information
        # vs the target. Mutually exclusive with PCA (PCA already reduces).
        self.selected_features_ = None
        fs = str(self.integrate_cfg.get("feature_selection", "none")).lower()
        if fs == "univariate" and not self.integrate_cfg.get("pca") and y is not None:
            num_final = [c for c in feats if pd.api.types.is_numeric_dtype(df[c])]
            k = int(self.integrate_cfg.get("fs_k", 0) or 0)
            if k > 0 and 0 < k < len(num_final):
                kept = self._univariate_select(df[num_final].fillna(0), y, k,
                                               str(self.integrate_cfg.get("fs_score", "anova")))
                if kept:
                    non_num = [c for c in feats if c not in num_final]
                    feats = [c for c in feats if c in kept or c in non_num]
                    self.selected_features_ = list(feats)

        # 6b. Optional PCA compression, fit on the train matrix.
        self.pca_, self.pca_input_cols_ = None, []
        if self.integrate_cfg.get("pca"):
            num_final = [c for c in feats if pd.api.types.is_numeric_dtype(df[c])]
            if len(num_final) >= 2:
                try:
                    pca = PCA(n_components=float(self.integrate_cfg.get("pca_variance", 0.95)),
                              svd_solver="full")
                    comps = pca.fit_transform(df[num_final].fillna(0))
                    self.pca_ = pca
                    self.pca_input_cols_ = num_final
                    feats = [f"PC{i + 1}" for i in range(comps.shape[1])]
                except Exception:
                    self.pca_ = None

        self.feature_names_ = list(feats)
        self.fitted_ = True
        return self

    def _univariate_select(self, X, y, k, score):
        """Top-k feature names by ANOVA F-test / mutual information vs the target
        (classification or regression score chosen from ``problem_type``)."""
        from sklearn.feature_selection import (
            SelectKBest, f_classif, f_regression, mutual_info_classif, mutual_info_regression,
        )
        is_reg = self.problem_type == "regression"
        if score == "mutual_info":
            func = mutual_info_regression if is_reg else mutual_info_classif
        else:
            func = f_regression if is_reg else f_classif
        try:
            sel = SelectKBest(func, k=min(k, X.shape[1])).fit(X, y)
            support = sel.get_support()
            return [c for c, keep in zip(X.columns, support) if keep]
        except Exception:
            return []

    # ── transform ────────────────────────────────────────────────────────
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply the fitted preprocessing; returns the numeric feature matrix."""
        if not self.fitted_:
            raise RuntimeError("FeaturePreprocessor.transform() appelé avant fit().")
        df = df.copy()
        df = self._build_features(df, fitting=False)

        for c, how in self.skew_cols_:
            if c not in df.columns:
                continue
            if how == "log1p":
                df[c] = np.log1p(df[c].clip(lower=0))
            else:
                try:
                    df[c] = how.transform(df[[c]])
                except Exception:
                    pass

        for col, order in (self.typology_ or {}).get("ordinale", {}).items():
            if col in df.columns:
                df[col] = typ.encode_ordinal(df[col], order)

        df = self._encode_nominals(df)

        dropped = set(self.integrate_cfg.get("dropped_features") or [])
        df = df.drop(columns=[c for c in dropped if c in df.columns], errors="ignore")

        if self.scaler_ is not None:
            for c in self.scale_cols_:
                if c not in df.columns:
                    df[c] = 0.0
            df[self.scale_cols_] = self.scaler_.transform(df[self.scale_cols_])

        if self.pca_ is not None:
            X = df.reindex(columns=self.pca_input_cols_, fill_value=0).fillna(0)
            comps = self.pca_.transform(X)
            out = pd.DataFrame(comps, columns=self.feature_names_, index=df.index)
            return out.fillna(0)

        out = df.reindex(columns=self.feature_names_, fill_value=0)
        out = out.apply(pd.to_numeric, errors="coerce").fillna(0)
        return out

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df)

    # ── helpers ──────────────────────────────────────────────────────────
    def _encode_nominals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply the nominal encoding learned at fit time (fixed categories)."""
        if self.ordinal_nominal_encoder_ is not None:
            cols = [c for c in self.nominal_cols_ if c in df.columns]
            if cols == self.nominal_cols_:
                df[cols] = self.ordinal_nominal_encoder_.transform(df[cols].astype(str))
            return df
        for c, cats in self.onehot_categories_.items():
            if c not in df.columns:
                for v in cats:
                    df[f"{c}_{v}"] = 0
                continue
            # Series (not bare Categorical) so the dummies keep df's index — a bare
            # Categorical gets a fresh RangeIndex and the concat would misalign rows.
            # Unseen values -> NaN first (all-zero dummy row), pandas 4 forbids them.
            vals = df[c].astype(str)
            vals = vals.where(vals.isin(cats))
            cat = pd.Series(pd.Categorical(vals, categories=cats), index=df.index)
            dummies = pd.get_dummies(cat, prefix=c, dummy_na=False).astype(int)
            df = df.drop(columns=[c])
            df = pd.concat([df, dummies], axis=1)
        if self.highcard_encoder_ is not None:
            cols = [c for c in self.highcard_cols_ if c in df.columns]
            if cols == self.highcard_cols_:
                df[cols] = self.highcard_encoder_.transform(df[cols].astype(str))
        return df
