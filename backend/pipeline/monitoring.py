"""
monitoring.py — post-deployment drift & stability monitoring.

Once a model is trained and evaluated, the real risk in a critical (SOC /
threat-intel) environment is not the hardware but **drift**: the input
distribution shifts (data drift), the "normal" the detector learned moves
(concept drift), or the served pipeline stops reproducing its own outputs
(silent corruption / a bad reload). This module quantifies all three from a NEW
batch of data compared to the training reference — everything deterministic,
no model re-fit.

* **Data drift** — per feature, Population Stability Index (PSI) + a
  Kolmogorov-Smirnov two-sample test, each classified none / moderate / major.
* **Prediction drift (concept)** — how the distribution of predictions moved
  (total-variation distance on classes, PSI on regression outputs); for a
  detector, a jump in the positive/alert rate is the actionable signal.
* **Reproducibility** — re-score a reference sample twice and check the outputs
  are identical (determinism), and that the re-computed metric matches what the
  Evaluation stage recorded (no silent pipeline corruption).
* **Threshold re-calibration** — when the new batch carries labels, recompute
  the operating point on it (reusing operational.py) so the analyst sees whether
  the deployed threshold still holds.

Reference distribution = the transformed TRAIN matrix (``sep.artifacts["X_train"]``);
the incoming batch is passed through the SAME fitted preprocessor (via
``scoring.transform_rows``), so the comparison is apples-to-apples in feature space.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .context import REGRESSION, CLASSIFICATION, ANOMALY

# PSI interpretation thresholds (industry-standard credit-risk convention).
PSI_MODERATE = 0.1
PSI_MAJOR = 0.25
KS_ALPHA = 0.05

# Jitter protocol: noise amplitudes as fractions of each feature's reference
# std, repeats per amplitude, and the flip-rate above which the verdict at
# that amplitude is "unstable".
JITTER_EPSILONS = (0.001, 0.005, 0.01, 0.05, 0.1)
JITTER_REPEATS = 5
JITTER_FLIP_TOLERANCE = 0.05
JITTER_MAX_ROWS = 400
JITTER_SEED = 42


def _level(psi_value):
    if psi_value >= PSI_MAJOR:
        return "major"
    if psi_value >= PSI_MODERATE:
        return "moderate"
    return "none"


def psi(reference, current, bins=10) -> float:
    """Population Stability Index between two numeric samples.

    Bins are the reference quantiles (so each reference bin holds ~equal mass);
    the current sample is scored into them. A small epsilon avoids div-by-zero on
    empty bins. Higher = more shift (0 = identical).
    """
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if len(ref) < 2 or len(cur) < 1:
        return 0.0
    quantiles = np.linspace(0, 100, bins + 1)
    edges = np.unique(np.percentile(ref, quantiles))
    if len(edges) < 2:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts = np.histogram(ref, bins=edges)[0].astype(float)
    cur_counts = np.histogram(cur, bins=edges)[0].astype(float)
    eps = 1e-6
    ref_pct = ref_counts / ref_counts.sum() + eps
    cur_pct = cur_counts / cur_counts.sum() + eps
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def ks(reference, current) -> tuple:
    """Kolmogorov-Smirnov two-sample test: ``(statistic, p_value)``.

    p < KS_ALPHA rejects "same distribution" → drift. Falls back to (0, 1) when
    scipy is unavailable or a sample is degenerate (never raises).
    """
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if len(ref) < 2 or len(cur) < 2:
        return 0.0, 1.0
    try:
        from scipy.stats import ks_2samp
        res = ks_2samp(ref, cur)
        return round(float(res.statistic), 4), round(float(res.pvalue), 4)
    except Exception:
        return 0.0, 1.0


def feature_drift(ref_df: pd.DataFrame, cur_df: pd.DataFrame, feature_names) -> dict:
    """Per-feature PSI + KS, each classified; plus an overall summary."""
    rows = []
    for f in feature_names:
        if f not in ref_df.columns or f not in cur_df.columns:
            continue
        p = round(psi(ref_df[f], cur_df[f]), 4)
        ks_stat, ks_p = ks(ref_df[f], cur_df[f])
        lvl = _level(p)
        if lvl == "none" and ks_p < KS_ALPHA:  # KS can catch shape shifts PSI misses
            lvl = "moderate"
        rows.append({"feature": str(f), "psi": p, "ks_stat": ks_stat, "ks_p": ks_p,
                     "level": lvl})
    rows.sort(key=lambda r: -r["psi"])
    n_major = sum(1 for r in rows if r["level"] == "major")
    n_moderate = sum(1 for r in rows if r["level"] == "moderate")
    verdict = "major" if n_major else ("moderate" if n_moderate else "stable")
    return {"features": rows, "n_features": len(rows),
            "n_major": n_major, "n_moderate": n_moderate, "verdict": verdict,
            "worst": rows[0] if rows else None}


def prediction_drift(ref_preds, cur_preds, problem_type) -> dict:
    """Shift in the OUTPUT distribution — the concept-drift signal.

    Classification/anomaly: class proportions + total-variation distance, and the
    change in the positive/alert rate (the number a SOC actually cares about).
    Regression: PSI on the predicted values.
    """
    ref = np.asarray(ref_preds)
    cur = np.asarray(cur_preds)
    if problem_type == REGRESSION:
        p = round(psi(ref, cur), 4)
        return {"kind": "regression", "psi": p, "level": _level(p),
                "ref_mean": round(float(np.mean(ref)), 4) if len(ref) else None,
                "cur_mean": round(float(np.mean(cur)), 4) if len(cur) else None}
    classes = sorted(set(np.concatenate([ref, cur]).tolist())) if len(ref) or len(cur) else []
    def _dist(a):
        n = len(a) or 1
        return {c: float(np.sum(a == c)) / n for c in classes}
    rd, cd = _dist(ref), _dist(cur)
    tvd = 0.5 * sum(abs(cd[c] - rd[c]) for c in classes)
    rows = [{"class": str(c), "ref": round(rd[c], 4), "cur": round(cd[c], 4),
             "delta": round(cd[c] - rd[c], 4)} for c in classes]
    return {"kind": "categorical", "total_variation": round(float(tvd), 4),
            "level": ("major" if tvd >= 0.15 else ("moderate" if tvd >= 0.05 else "none")),
            "classes": rows}


def reproducibility(session) -> dict:
    """Determinism + consistency check on the held-out reference sample.

    (1) score it twice → outputs must be byte-identical (a mismatch means silent
    nondeterminism / a corrupted reload). (2) re-compute the primary metric and
    compare it to what the Evaluation stage recorded — a divergence means the
    served pipeline no longer reproduces its evaluation.
    """
    model, _o = session.current_model()
    sep = session.get_run("separate")
    if model is None or sep is None:
        return {"available": False, "reason": "Aucun modèle entraîné."}
    art = sep.artifacts
    X = art.get("X_test")
    y = art.get("y_test")
    if X is None:
        return {"available": False, "reason": "Pas de jeu de référence (test)."}
    try:
        p1 = np.asarray(model.predict(X))
        p2 = np.asarray(model.predict(X))
    except Exception as e:
        return {"available": False, "reason": f"Re-scoring impossible ({type(e).__name__})."}
    deterministic = bool(np.array_equal(p1, p2))

    out = {"available": True, "deterministic": deterministic, "n_reference": int(len(p1))}
    ev = session.get_run("evaluate")
    ptype = session.ctx.problem_type
    if y is not None and ev is not None and isinstance(ev.result, dict):
        recorded = (ev.result.get("metrics") or {})
        try:
            if ptype == REGRESSION:
                from sklearn.metrics import r2_score
                cur = round(float(r2_score(y, p1)), 4)
                ref = recorded.get("R²")
            else:
                from sklearn.metrics import accuracy_score
                cur = round(float(accuracy_score(y, p1)), 4)
                ref = recorded.get("Accuracy")
            if ref is not None:
                out["recorded_metric"] = ref
                out["recomputed_metric"] = cur
                out["consistent"] = bool(abs(float(ref) - cur) < 1e-6)
        except Exception:
            pass
    out["verdict"] = ("stable" if out.get("deterministic")
                      and out.get("consistent", True) else "instable")
    return out


def recalibrated_operating_point(session, cur_X, cur_y, cost_fn, cost_fp) -> dict:
    """Recompute the binary operating point on the NEW labelled batch, so the
    analyst sees whether the deployed threshold still minimises cost. Binary
    classification only (the SOC detection case)."""
    model, _o = session.current_model()
    if session.ctx.problem_type != CLASSIFICATION or not hasattr(model, "predict_proba"):
        return {"available": False, "reason": "Re-calibration : classification binaire uniquement."}
    try:
        proba = model.predict_proba(cur_X)
    except Exception:
        return {"available": False, "reason": "Probabilités indisponibles sur le lot."}
    classes = list(getattr(model, "classes_", []))
    if proba.ndim != 2 or proba.shape[1] != 2 or len(classes) != 2:
        return {"available": False, "reason": "Re-calibration : cible binaire uniquement."}
    from . import operational as opn
    pos = classes[-1]
    y_score = proba[:, classes.index(pos)]
    _sweep, reco = opn.threshold_sweep(np.asarray(cur_y), y_score, pos, cost_fn, cost_fp)
    cur_point = opn.confusion_at(np.asarray(cur_y), y_score, reco["min_cost"], pos, cost_fn, cost_fp)
    return {"available": True, "recommended_threshold": reco["min_cost"],
            "recall": cur_point["recall"], "precision": cur_point["precision"],
            "fpr": cur_point["fpr"], "n_batch": int(len(cur_y))}


def _jitter_flip_rate(model, X, p0, sigma, eps, rng, ptype, reg_tol):
    """Score one perturbed copy of X and return the fraction of rows whose
    prediction materially changed (class flipped, or regression output moved by
    more than ``reg_tol``)."""
    noise = rng.normal(0.0, 1.0, size=X.shape) * (sigma.to_numpy() * eps)
    Xp = X + noise
    p = np.asarray(model.predict(Xp))
    if ptype == REGRESSION:
        return float(np.mean(np.abs(p.astype(float) - p0.astype(float)) > reg_tol))
    return float(np.mean(p != p0))


def jitter_protocol(session, epsilons=JITTER_EPSILONS, repeats=JITTER_REPEATS,
                    seed=JITTER_SEED) -> dict:
    """Prediction-stability ("jitter") measurement protocol.

    The operational question behind hardware-jitter concerns is: *do the
    verdicts of the deployed detector flip under tiny input perturbations?*
    This protocol answers it in feature space, deterministically: add Gaussian
    noise scaled to a fraction ``eps`` of each feature's reference std, re-score,
    and measure the flip rate (share of rows whose prediction changed — for
    regression, moved by more than 5% of the output std). Repeated ``repeats``
    times per amplitude with a fixed seed, so the report is reproducible.

    A detector whose verdicts flip at eps = 0.1% of a std is unstable in a
    critical environment regardless of the hardware it runs on; one that holds
    up to eps = 10% is robust to any realistic sensor/measurement noise.
    """
    model, _o = session.current_model()
    sep = session.get_run("separate")
    if model is None or sep is None:
        return {"available": False, "reason": "Entraînez un modèle avant le protocole jitter."}
    if not hasattr(model, "predict"):
        return {"available": False, "reason": (
            "Ce détecteur (LOF classique) ne re-score pas de nouveaux points : "
            "le protocole jitter ne s'y applique pas. Utilisez Isolation Forest.")}

    art = sep.artifacts
    ref_df, _feats = _reference_matrix(art)
    X = art.get("X_test")
    if X is None:
        X = ref_df
    if X is None or len(X) == 0:
        return {"available": False, "reason": "Pas de jeu de référence à perturber."}
    X = X if isinstance(X, pd.DataFrame) else pd.DataFrame(np.asarray(X))
    rng = np.random.RandomState(seed)
    if len(X) > JITTER_MAX_ROWS:
        X = X.iloc[rng.choice(len(X), JITTER_MAX_ROWS, replace=False)]

    sigma = X.std(ddof=0).fillna(0.0)  # per-feature scale; constant columns stay untouched
    ptype = session.ctx.problem_type
    try:
        p0 = np.asarray(model.predict(X))
    except Exception as e:
        return {"available": False, "reason": f"Re-scoring impossible ({type(e).__name__})."}
    reg_tol = 0.05 * float(np.std(p0.astype(float))) if ptype == REGRESSION else None

    curve = []
    for eps in epsilons:
        rates = [_jitter_flip_rate(model, X, p0, sigma, float(eps), rng, ptype, reg_tol)
                 for _ in range(int(repeats))]
        curve.append({"epsilon": float(eps),
                      "flip_rate": round(float(np.mean(rates)), 4),
                      "flip_min": round(float(np.min(rates)), 4),
                      "flip_max": round(float(np.max(rates)), 4)})

    breaking = next((c["epsilon"] for c in curve
                     if c["flip_rate"] > JITTER_FLIP_TOLERANCE), None)
    if breaking is None:
        verdict = "stable"
    elif breaking <= 0.005:
        verdict = "instable"
    else:
        verdict = "sensible"
    return {"available": True, "problem_type": ptype, "n_rows": int(len(X)),
            "repeats": int(repeats), "tolerance": JITTER_FLIP_TOLERANCE,
            "curve": curve, "breaking_epsilon": breaking, "verdict": verdict}


def _reference_matrix(art) -> tuple:
    """The training feature matrix used as the drift reference (train split for
    supervised, the full matrix for unsupervised), as a DataFrame + names."""
    feats = list(art.get("feature_names") or [])
    ref = art.get("X_train")
    if ref is None:
        ref = art.get("X_full")
    if ref is None:
        return None, feats
    ref_df = ref if isinstance(ref, pd.DataFrame) else pd.DataFrame(ref, columns=feats)
    return ref_df, (feats or list(ref_df.columns))


def drift_report(session, current_df: pd.DataFrame, cost_fn=None, cost_fp=None) -> dict:
    """Full drift & stability report: compare a NEW batch to the training
    reference (data drift), the prediction distribution (concept drift), the
    served pipeline against itself (reproducibility), and — when the batch is
    labelled — the operating point (re-calibration). No model re-fit.
    """
    from . import operational as opn
    from . import scoring

    model, _o = session.current_model()
    sep = session.get_run("separate")
    if model is None or sep is None:
        return {"available": False, "reason": "Entraînez et évaluez un modèle avant la surveillance."}
    art = sep.artifacts
    ref_df, feats = _reference_matrix(art)
    if ref_df is None or current_df is None or len(current_df) == 0:
        return {"available": False, "reason": "Référence ou lot courant indisponible."}

    ptype = session.ctx.problem_type
    target = session.ctx.target_col
    cf = float(cost_fn) if cost_fn is not None else opn.DEFAULT_COST_FN
    cp = float(cost_fp) if cost_fp is not None else opn.DEFAULT_COST_FP

    # Project the incoming batch into the SAME feature space (fitted preprocessor).
    cur_X = scoring.transform_rows(session, current_df.to_dict(orient="records"))
    fdrift = feature_drift(ref_df, cur_X, feats)

    # Prediction (concept) drift: reference vs current output distribution.
    try:
        # Keep the DataFrames (with feature names) so the estimator doesn't warn.
        ref_preds = model.predict(ref_df)
        cur_preds = model.predict(cur_X)
        pdrift = prediction_drift(ref_preds, cur_preds, ptype)
    except Exception:
        pdrift = {"kind": "unavailable"}

    repro = reproducibility(session)

    # Threshold re-calibration when the batch carries labels.
    recal = {"available": False, "reason": "Lot non labellisé (cible absente)."}
    if target and target in current_df.columns:
        le = art.get("label_encoder")
        y_raw = current_df[target]
        mask = y_raw.notna().to_numpy()
        if mask.any():
            try:
                cur_y = (le.transform(y_raw[mask].astype(str)) if le is not None
                         else y_raw[mask].to_numpy())
                recal = recalibrated_operating_point(session, cur_X.iloc[mask], cur_y, cf, cp)
            except Exception as e:
                recal = {"available": False, "reason": f"Re-calibration impossible ({type(e).__name__})."}

    overall = "major" if (fdrift["verdict"] == "major" or pdrift.get("level") == "major") else \
              ("moderate" if (fdrift["verdict"] == "moderate" or pdrift.get("level") in ("moderate",)
                              or not repro.get("deterministic", True)) else "stable")
    return {"available": True, "n_batch": int(len(current_df)), "n_reference": int(len(ref_df)),
            "problem_type": ptype, "overall": overall,
            "data_drift": fdrift, "prediction_drift": pdrift,
            "reproducibility": repro, "recalibration": recal}
