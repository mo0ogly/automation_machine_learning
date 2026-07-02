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

# Total-variation-distance thresholds on the prediction distribution (concept
# drift). Named for parity with the PSI thresholds above (no inline magic numbers).
TVD_MODERATE = 0.05
TVD_MAJOR = 0.15

# Cause-attribution topology: how many features must drift together (and what
# share of them) before the drift reads as "broad" (an upstream/environment
# signature) rather than "localized" (a single-field data-quality signature).
BROAD_MIN_FEATURES = 4
BROAD_MIN_DRIFTING = 3
BROAD_FRACTION = 0.5

# How many missing/extra column names to spell out in the evidence line before
# summarising the remainder as a count.
SCHEMA_MAX_SHOWN = 6

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


def _scipy_available() -> bool:
    """Whether the KS two-sample test can actually run. When False, KS p-values
    are placeholders (1.0) and must not be read as 'no drift' — the report says so
    rather than silently implying stability."""
    try:
        import scipy.stats  # noqa: F401
        return True
    except Exception:
        return False


def _bh_reject(pvalues, alpha=KS_ALPHA) -> list:
    """Benjamini-Hochberg step-up: which p-values are significant at FDR ``alpha``.

    Returns a boolean list aligned to the input order. Controlling the false
    discovery rate matters here: at alpha per feature, ~alpha·m stable features
    would flag by chance (30 features → ~1.5 false 'moderate's), inflating the
    drift count. BH caps the expected share of false positives among the flagged."""
    idx = [i for i, p in enumerate(pvalues) if p is not None and np.isfinite(p)]
    m = len(idx)
    reject = [False] * len(pvalues)
    if m == 0:
        return reject
    order = sorted(idx, key=lambda i: pvalues[i])
    k_max = 0
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= (rank / m) * alpha:
            k_max = rank
    for rank, i in enumerate(order, start=1):
        if rank <= k_max:
            reject[i] = True
    return reject


def schema_diff(expected_cols, batch_cols, target=None) -> dict:
    """Compare the RAW columns of an incoming batch to the training schema.

    This runs on the raw upload — *before* the preprocessor silently reconciles it
    (missing training columns get median/mode-imputed, unknown columns get dropped).
    That reconciliation is exactly what makes a schema change invisible downstream:
    an imputed column fabricates apparent stability, so the mismatch must be caught
    here. Returns ``{changed, missing, extra}`` — ``missing`` = training columns
    absent from the batch, ``extra`` = batch columns unknown to training (the target
    is excluded from both, it is not a feature)."""
    expected = [c for c in (expected_cols or []) if c != target]
    batch = set(batch_cols or [])
    missing = [c for c in expected if c not in batch]
    extra = [c for c in (batch_cols or []) if c not in set(expected) and c != target]
    return {"changed": bool(missing or extra), "missing": missing, "extra": extra}


def _schema_line(label, cols) -> str:
    shown = ", ".join(str(c) for c in cols[:SCHEMA_MAX_SHOWN])
    if len(cols) > SCHEMA_MAX_SHOWN:
        shown += " (+" + str(len(cols) - SCHEMA_MAX_SHOWN) + ")"
    return str(len(cols)) + " " + label + " : " + shown


def feature_drift(ref_df: pd.DataFrame, cur_df: pd.DataFrame, feature_names) -> dict:
    """Per-feature PSI + KS, each classified; plus an overall summary.

    KS across many features is a multiple-comparisons problem, so a KS-driven
    upgrade to 'moderate' uses Benjamini-Hochberg significance (FDR-controlled),
    not a raw per-feature p < alpha. When scipy is absent the KS test can't run;
    ``ks_available`` is False and PSI alone drives the verdict."""
    ks_ok = _scipy_available()
    rows = []
    for f in feature_names:
        if f not in ref_df.columns or f not in cur_df.columns:
            continue
        p = round(psi(ref_df[f], cur_df[f]), 4)
        ks_stat, ks_p = ks(ref_df[f], cur_df[f])
        rows.append({"feature": str(f), "psi": p, "ks_stat": ks_stat, "ks_p": ks_p,
                     "level": _level(p)})
    # KS can catch shape shifts PSI misses, but only trust it after FDR control.
    if ks_ok:
        reject = _bh_reject([r["ks_p"] for r in rows], KS_ALPHA)
        for r, sig in zip(rows, reject):
            r["ks_significant"] = bool(sig)
            if r["level"] == "none" and sig:
                r["level"] = "moderate"
    else:
        for r in rows:
            r["ks_significant"] = False
    rows.sort(key=lambda r: -r["psi"])
    n_major = sum(1 for r in rows if r["level"] == "major")
    n_moderate = sum(1 for r in rows if r["level"] == "moderate")
    verdict = "major" if n_major else ("moderate" if n_moderate else "stable")
    return {"features": rows, "n_features": len(rows), "ks_available": ks_ok,
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
            "level": ("major" if tvd >= TVD_MAJOR else ("moderate" if tvd >= TVD_MODERATE else "none")),
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
                # The recorded metric is rounded to 4 decimals; compare within
                # half a unit of that last digit, not at float precision.
                out["consistent"] = bool(abs(float(ref) - cur) < 5e-5)
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

    # Only perturb CONTINUOUS features. Gaussian noise on a one-hot / binary
    # indicator (0/1) pushes it off-manifold (e.g. 0.97 in a column that is only
    # ever 0 or 1), which fabricates instability the model would never see in
    # production. Heuristic: >2 distinct values in the reference = continuous.
    continuous = (X.nunique(dropna=True) > 2)
    sigma = X.std(ddof=0).fillna(0.0).where(continuous, 0.0)  # constant cols already 0
    n_continuous = int(continuous.sum())
    if n_continuous == 0:
        return {"available": False, "reason": (
            "Aucune variable continue à perturber (colonnes binaires / one-hot "
            "uniquement) : le protocole jitter ne s'y applique pas.")}
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
            "n_continuous": n_continuous, "n_features": int(X.shape[1]),
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


def _cause(cause, label, confidence, severity, evidence, action) -> dict:
    return {"cause": cause, "label": label, "confidence": confidence,
            "severity": severity, "evidence": list(evidence), "action": action}


def _env_diff_lines(env_change: dict) -> list:
    """Render a fingerprint comparison as 'field from → to' evidence strings."""
    out = []
    for d in (env_change or {}).get("diffs", []):
        out.append(str(d.get("field")) + " " + str(d.get("from")) + " → " + str(d.get("to")))
    return out


def attribute_cause(fdrift: dict, pdrift: dict, repro: dict, env_change: dict = None,
                    schema: dict = None) -> dict:
    """Attribute a probable ROOT CAUSE to an observed divergence, from the signals
    already computed — no extra model calls, no external hardware logs.

    The point is to separate *infrastructure / environment* causes from genuine
    *data / model* behaviour change before anyone acts: a divergence that is
    really a broken reload, a changed library version or an upstream ingestion
    change must not be read as a concept shift (or, in a SOC, as an attack).
    Priority: (1) pipeline corruption / non-determinism, (2) execution-environment
    change (a library/platform version differs from training), then the data
    causes — because both (1) and (2) invalidate any conclusion drawn from the
    drift numbers. Candidates are returned ranked; ``primary`` is the top one.

    ``env_change`` is the output of ``environment.compare_fingerprints`` (training
    vs serving); when it reports a change it feeds the two infrastructure causes.

    Returns ``{available, primary, causes, summary}`` where each cause carries
    its evidence and a recommended action.
    """
    env_changed = bool((env_change or {}).get("changed"))
    env_lines = _env_diff_lines(env_change)
    schema = schema or {}
    schema_changed = bool(schema.get("changed"))
    missing = list(schema.get("missing") or [])
    extra = list(schema.get("extra") or [])
    fdrift = fdrift or {}
    n_features = int(fdrift.get("n_features") or 0)
    n_major = int(fdrift.get("n_major") or 0)
    n_moderate = int(fdrift.get("n_moderate") or 0)
    n_drift = n_major + n_moderate
    feat_drift = fdrift.get("verdict") in ("moderate", "major")
    worst = fdrift.get("worst") or None

    broad = (n_features >= BROAD_MIN_FEATURES and n_drift >= BROAD_MIN_DRIFTING
             and n_drift >= BROAD_FRACTION * n_features)
    localized = 1 <= n_drift <= 2

    pkind = (pdrift or {}).get("kind")
    pred_level = (pdrift or {}).get("level") if pkind not in (None, "unavailable") else None
    pred_drift = pred_level in ("moderate", "major")

    repro = repro or {}
    repro_broken = bool(repro.get("available")) and (
        not repro.get("deterministic", True) or repro.get("consistent") is False)

    causes = []

    # 1. Serving / pipeline corruption (infrastructure) — invalidates the rest.
    if repro_broken:
        ev = []
        if not repro.get("deterministic", True):
            ev.append("re-scoring non déterministe : deux passes du même lot donnent des "
                      "sorties différentes")
        if repro.get("consistent") is False:
            rec, cur = repro.get("recorded_metric"), repro.get("recomputed_metric")
            detail = (" (" + str(rec) + " → " + str(cur) + ")") if rec is not None else ""
            ev.append("métrique recalculée ≠ métrique enregistrée à l'évaluation" + detail)
        if env_changed:  # concrete culprit for the non-determinism/inconsistency
            ev.extend("environnement d'exécution modifié : " + line for line in env_lines)
        causes.append(_cause(
            "pipeline_corruption",
            "Corruption / non-déterminisme du pipeline servi (infrastructure)",
            "haute", "major", ev,
            "Cause d'infrastructure, pas de données : vérifier le rechargement du modèle, "
            "les versions de bibliothèques, la graine et le nombre de threads AVANT de "
            "conclure à une dérive des données ou à une attaque."))

    # 1bis. Execution-environment change (infrastructure) — an environment that
    # differs from training can move the outputs without any data/model change.
    if env_changed and not repro_broken:
        causes.append(_cause(
            "environment_change",
            "Changement d'environnement d'exécution (versions / plateforme)",
            "haute", "major", env_lines,
            "L'environnement d'exécution diffère de celui de l'entraînement. Une version de "
            "bibliothèque ou une plateforme différente peut déplacer les sorties sans "
            "changement des données ni du modèle. Rétablir l'environnement d'entraînement "
            "(versions épinglées) et re-mesurer AVANT de conclure à une dérive de données / "
            "concept ou à une attaque."))

    # 1ter. Raw-schema mismatch (upstream ingestion) — a concrete, non-heuristic
    # upstream signal. It outranks the drift topology below because the missing
    # columns were median/mode-imputed and the extra ones dropped, so the PSI/KS
    # numbers on THIS batch are partly artefacts of that reconciliation.
    if schema_changed:
        ev = []
        if missing:
            ev.append(_schema_line("variable(s) d'entraînement absente(s) du lot (imputées)", missing))
        if extra:
            ev.append(_schema_line("variable(s) inconnue(s) du modèle (ignorées)", extra))
        causes.append(_cause(
            "schema_mismatch",
            "Schéma du lot différent de l'entraînement (ingestion amont)",
            "haute", "major", ev,
            "Le lot n'a pas les mêmes colonnes que l'entraînement : colonnes manquantes "
            "imputées, colonnes en trop ignorées. Les chiffres de dérive de ce lot sont donc "
            "en partie des artefacts. Corriger la source / le mapping des colonnes et "
            "re-mesurer AVANT de conclure à une dérive de données ou à une attaque."))

    # 2. Feature-drift topology: broad (upstream/environment) vs localized (field).
    if broad:
        frac = n_drift / n_features if n_features else 0.0
        conf = "haute" if (n_major >= BROAD_MIN_DRIFTING or frac >= 0.7) else "moyenne"
        causes.append(_cause(
            "upstream_ingestion",
            "Changement en amont / ingestion (environnement)",
            conf, "major",
            [str(n_drift) + "/" + str(n_features) + " variables dérivent conjointement (dont "
             + str(n_major) + " majeure(s))"],
            "Une dérive large et simultanée pointe vers l'amont, pas le modèle : suspecter une "
            "nouvelle source, un changement d'unité / format / encodage, ou un bug "
            "d'ingestion ou de prétraitement. Vérifier le schéma du lot avant de ré-entraîner."))
    elif localized and feat_drift:
        detail = ((" ; pire : '" + str(worst.get("feature")) + "' (PSI " + str(worst.get("psi"))
                   + ")") if isinstance(worst, dict) else "")
        causes.append(_cause(
            "localized_data_quality",
            "Anomalie localisée sur une variable (qualité de données)",
            "moyenne", "moderate",
            ["dérive concentrée sur " + str(n_drift) + " variable(s)" + detail],
            "Inspecter cette variable précise : capteur ou colonne défaillant, valeurs "
            "manquantes, changement d'unité ou d'encodage sur ce champ isolé."))

    # 3. Mechanism from the input/output interplay.
    if pred_drift and feat_drift:
        causes.append(_cause(
            "covariate_shift",
            "Dérive des entrées répercutée sur les sorties (covariate shift)",
            "moyenne", "moderate",
            ["entrées en dérive (" + str(fdrift.get("verdict")) + ") et distribution des "
             "prédictions déplacée (niveau " + str(pred_level) + ")"],
            "Déplacement réel des entrées reflété par le modèle : re-calibrer le seuil sur le "
            "nouveau régime, envisager un ré-entraînement si le déplacement persiste."))
    elif pred_drift and not feat_drift:
        causes.append(_cause(
            "concept_shift",
            "Sorties déplacées sans dérive des entrées (dérive de concept ou rechargement)",
            "moyenne", "moderate",
            ["distribution des prédictions déplacée (niveau " + str(pred_level) + ") alors que "
             "les entrées restent stables"],
            "Deux hypothèses : (1) la relation entrées→cible a changé (ré-étiqueter / "
            "ré-entraîner) ; (2) mauvais rechargement du modèle. Croiser avec la "
            "reproductibilité pour trancher."))
    elif feat_drift and not pred_drift:
        causes.append(_cause(
            "absorbed_input_drift",
            "Dérive des entrées sans impact sur les sorties",
            "faible", "stable",
            ["entrées en dérive (" + str(fdrift.get("verdict")) + ") mais distribution des "
             "prédictions stable"],
            "Le modèle absorbe le déplacement pour l'instant. Surveiller : une dérive d'entrée "
            "non répercutée peut précéder une chute de performance. Pas d'action immédiate."))

    if not causes:
        return {"available": True, "primary": None, "causes": [],
                "summary": "Aucune cause significative : le lot est conforme au régime "
                           "d'entraînement."}
    primary = causes[0]
    return {"available": True, "primary": primary, "causes": causes,
            "summary": primary["label"] + " (confiance " + primary["confidence"] + ")"}


def drift_report(session, current_df: pd.DataFrame, cost_fn=None, cost_fp=None,
                 exec_meta=None) -> dict:
    """Full drift & stability report: compare a NEW batch to the training
    reference (data drift), the prediction distribution (concept drift), the
    served pipeline against itself (reproducibility), the execution environment
    against the one the model was trained in, and — when the batch is labelled —
    the operating point (re-calibration). No model re-fit.

    ``exec_meta`` is optional free-form operational metadata about the serving
    context (node, timestamp, temperature, ``throttling``); surfaced as-is and
    used only as a hint to the cause attribution.
    """
    from . import operational as opn
    from . import scoring
    from . import environment

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

    # Raw-schema check BEFORE transform_rows reconciles the columns (imputes the
    # missing, drops the unknown) — the mismatch is invisible once reconciled.
    raw = getattr(session, "raw_df", None)
    schema = (schema_diff(list(raw.columns), list(current_df.columns), target)
              if raw is not None else {"changed": False, "missing": [], "extra": []})

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

    # Execution environment: training-time fingerprint vs now. A change here is an
    # infrastructure cause that must be ruled out before concluding data/concept drift.
    mrun = session.get_run("model")
    baseline_fp = (mrun.artifacts or {}).get("env_fingerprint") if mrun else None
    current_fp = environment.capture_fingerprint()
    env_change = environment.compare_fingerprints(baseline_fp, current_fp)
    meta = exec_meta if isinstance(exec_meta, dict) else None
    if meta and meta.get("throttling"):  # operational hint: hardware was throttling
        env_change = {**env_change, "available": True, "changed": True,
                      "diffs": list(env_change.get("diffs", []))
                      + [{"field": "throttling matériel", "from": "non signalé", "to": "actif"}]}

    # Infrastructure faults (non-determinism, inconsistency, a changed execution
    # environment) invalidate any conclusion drawn from the drift numbers, so the
    # overall verdict must never read "stable" while one of them holds.
    repro_broken = bool(repro.get("available")) and (
        not repro.get("deterministic", True) or repro.get("consistent") is False)
    env_changed = bool((env_change or {}).get("changed"))
    if fdrift["verdict"] == "major" or pdrift.get("level") == "major" or repro_broken:
        overall = "major"
    elif (fdrift["verdict"] == "moderate" or pdrift.get("level") == "moderate"
          or env_changed or schema["changed"]):
        overall = "moderate"
    else:
        overall = "stable"
    cause = attribute_cause(fdrift, pdrift, repro, env_change, schema)
    return {"available": True, "n_batch": int(len(current_df)), "n_reference": int(len(ref_df)),
            "problem_type": ptype, "overall": overall, "cause": cause,
            "data_drift": fdrift, "prediction_drift": pdrift, "schema": schema,
            "reproducibility": repro, "recalibration": recal,
            "environment": {"baseline": baseline_fp, "current": current_fp,
                            "comparison": env_change, "operational": meta}}
