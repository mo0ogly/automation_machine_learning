"""
resampling.py — class-imbalance resampling of the TRAINING set (no dependency).

Cyber detection targets are heavily imbalanced (KEV ~13%, phishing ~22%): a model
trained as-is optimises overall accuracy by ignoring the rare — but operationally
critical — positive class. Two levers complement each other:

* ``class_weight='balanced'`` (a model hyperparameter, wired in estimators.py) —
  cross-validation-safe, so it is what the leaderboard uses.
* **Resampling** (here) — rebalance the training rows themselves. Applied to the
  FINAL training fit ONLY (never the held-out test, never inside the leaderboard
  CV folds — that would leak synthetic rows into validation), so it can't inflate
  the reported scores.

Implemented from scratch (no imbalanced-learn dependency), deterministic:
* ``random_oversample`` — duplicate minority rows up to the majority count.
* ``random_undersample`` — subsample majority rows down to the minority count.
* ``smote`` — SMOTE (Chawla et al., 2002): synthesise minority rows by k-NN
  interpolation, ``x_new = x_i + u·(x_neighbour − x_i)`` with ``u ~ U(0,1)``.

All operate on a numeric feature matrix (the transformed train matrix is numeric)
and a discrete target; they return balanced ``(X, y)`` and never raise — an
unusable input (regression target, single class, too few samples) is returned
unchanged so the caller degrades gracefully.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 42
METHODS = ("oversample", "undersample", "smote")


def _as_xy(X, y):
    cols = list(X.columns) if isinstance(X, pd.DataFrame) else None
    Xv = X.to_numpy() if isinstance(X, pd.DataFrame) else np.asarray(X)
    yv = np.asarray(y)
    return Xv.astype(float), yv, cols


def _restore(Xv, yv, cols):
    if cols is not None:
        return pd.DataFrame(Xv, columns=cols), yv
    return Xv, yv


def _usable(yv) -> bool:
    if yv.dtype.kind == "f":                       # continuous target -> not classification
        return False
    _classes, counts = np.unique(yv, return_counts=True)
    return len(_classes) >= 2 and counts.min() >= 1


def random_oversample(X, y, seed=SEED):
    """Duplicate minority-class rows (with replacement) up to the majority count."""
    Xv, yv, cols = _as_xy(X, y)
    if not _usable(yv):
        return X, y
    rng = np.random.RandomState(seed)
    classes, counts = np.unique(yv, return_counts=True)
    target_n = int(counts.max())
    parts_X, parts_y = [], []
    for c in classes:
        idx = np.where(yv == c)[0]
        take = rng.choice(idx, target_n, replace=len(idx) < target_n)
        parts_X.append(Xv[take]); parts_y.append(yv[take])
    return _restore(np.vstack(parts_X), np.concatenate(parts_y), cols)


def random_undersample(X, y, seed=SEED):
    """Subsample majority-class rows (without replacement) down to the minority count."""
    Xv, yv, cols = _as_xy(X, y)
    if not _usable(yv):
        return X, y
    rng = np.random.RandomState(seed)
    classes, counts = np.unique(yv, return_counts=True)
    target_n = int(counts.min())
    parts_X, parts_y = [], []
    for c in classes:
        idx = np.where(yv == c)[0]
        take = rng.choice(idx, target_n, replace=False)
        parts_X.append(Xv[take]); parts_y.append(yv[take])
    return _restore(np.vstack(parts_X), np.concatenate(parts_y), cols)


def smote(X, y, k=5, seed=SEED):
    """SMOTE: synthesise minority rows by interpolating toward a random k-NN.

    Keeps every real row and adds synthetic minority rows until each class matches
    the majority count. Falls back to plain oversampling for a class with fewer
    than 2 samples (no neighbours to interpolate).
    """
    Xv, yv, cols = _as_xy(X, y)
    if not _usable(yv):
        return X, y
    from sklearn.neighbors import NearestNeighbors
    rng = np.random.RandomState(seed)
    classes, counts = np.unique(yv, return_counts=True)
    target_n = int(counts.max())
    new_X, new_y = [Xv], [yv]
    for c, n in zip(classes, counts):
        need = target_n - int(n)
        if need <= 0:
            continue
        minority = Xv[yv == c]
        if len(minority) < 2:                      # no neighbours -> duplicate
            take = rng.choice(len(minority), need, replace=True)
            new_X.append(minority[take]); new_y.append(np.full(need, c))
            continue
        kk = min(k, len(minority) - 1)
        nn = NearestNeighbors(n_neighbors=kk + 1).fit(minority)
        _dist, neigh = nn.kneighbors(minority)
        base = rng.randint(0, len(minority), need)
        step = rng.randint(1, kk + 1, need)        # 1..kk -> skip self (col 0)
        gaps = rng.random(need)[:, None]
        partners = minority[neigh[base, step]]
        synth = minority[base] + gaps * (partners - minority[base])
        new_X.append(synth); new_y.append(np.full(need, c))
    return _restore(np.vstack(new_X), np.concatenate(new_y), cols)


def resample(X, y, method, seed=SEED):
    """Dispatch to the requested resampling method; unknown / none -> unchanged."""
    if method == "oversample":
        return random_oversample(X, y, seed)
    if method == "undersample":
        return random_undersample(X, y, seed)
    if method == "smote":
        return smote(X, y, seed=seed)
    return X, y


def class_distribution(y) -> dict:
    """Counts per class label (for the before/after report)."""
    yv = np.asarray(y)
    classes, counts = np.unique(yv, return_counts=True)
    return {str(c): int(n) for c, n in zip(classes, counts)}
