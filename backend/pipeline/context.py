"""
context.py — Pipeline context: target column + problem-type detection.

The context is established once, when the dataset is ingested, and travels with
the session across every stage. It is overridable by the expert (the detection is
only a heuristic seed).
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

REGRESSION = "regression"
CLASSIFICATION = "classification"
CLUSTERING = "clustering"
ANOMALY = "anomaly"  # unsupervised outlier detection (IsolationForest / LOF)


def detect_target_and_type(df: pd.DataFrame):
    """
    Heuristic detection of (target_col, problem_type).

    Recognises the bundled demo datasets (regression / classification / clustering)
    and falls back to generic structural heuristics for arbitrary uploads.
    Returns ``(None, 'clustering')`` when no supervised target is identifiable.
    """
    cols_lower = {c.lower(): c for c in df.columns}

    # Known demo datasets first.
    if "saleprice" in cols_lower:
        return cols_lower["saleprice"], REGRESSION
    if "diagnosis" in cols_lower:
        return cols_lower["diagnosis"], CLASSIFICATION
    # Cyber demos: the label is unambiguous, but a stray 2-value categorical
    # feature (language, attack_complexity, scope…) would otherwise be mis-picked
    # as the target by the generic binary-column heuristic below.
    for tgt in ("is_phishing", "is_spam", "exploited", "severity"):
        if tgt in cols_lower:
            return cols_lower[tgt], CLASSIFICATION
    if "client_id" in cols_lower or "customer_id" in cols_lower:
        return None, CLUSTERING

    # Generic: a binary non-numeric column is a strong classification signal.
    non_numeric = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    for c in non_numeric:
        if df[c].nunique(dropna=True) == 2:
            return c, CLASSIFICATION

    # Otherwise inspect the last column (common target placement).
    target = df.columns[-1]
    n_unique = df[target].nunique(dropna=True)
    is_object = not pd.api.types.is_numeric_dtype(df[target])
    if is_object or n_unique <= 10:
        return target, CLASSIFICATION

    num_ratio = len(df.select_dtypes(include=[np.number]).columns) / max(1, len(df.columns))
    if num_ratio > 0.6:
        return None, CLUSTERING
    return target, REGRESSION


@dataclass
class PipelineContext:
    """Metadata shared by every stage of a session."""

    target_col: Optional[str]
    problem_type: str
    original_columns: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @classmethod
    def from_df(cls, df: pd.DataFrame) -> "PipelineContext":
        target, ptype = detect_target_and_type(df)
        return cls(
            target_col=target,
            problem_type=ptype,
            original_columns=list(df.columns),
        )

    @property
    def supervised(self) -> bool:
        return self.problem_type in (REGRESSION, CLASSIFICATION) and self.target_col is not None

    def to_dict(self) -> dict:
        return {
            "target_col": self.target_col,
            "problem_type": self.problem_type,
            "supervised": self.supervised,
            "n_original_columns": len(self.original_columns),
        }
