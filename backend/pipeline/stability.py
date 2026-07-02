"""
stability.py — advanced prediction-stability analyses (post-deployment).

Extends the jitter protocol (monitoring.py) with five deeper questions about a
deployed detector, each deterministic (fixed seed) and honest about what it can
and cannot certify:

* **Numerical jitter** — the only mechanism by which *hardware* can flip an ML
  verdict in software terms: floating-point precision. Re-score in float32 vs
  float64 and under a single BLAS thread, count flipped verdicts.
* **Margin analysis** — how much of the reference population sits within a
  hair's width of the decision threshold (the rows any perturbation would flip).
  Deterministic; complements the stochastic jitter protocol.
* **Prediction churn** — re-fit the same model with different seeds and measure
  verdict disagreement: the *structural* instability of the model family
  (Google's "prediction churn"), as opposed to inference instability.
* **Conformal prediction** — split-conformal sets/intervals with a finite-sample
  coverage guarantee under exchangeability; flags the verdicts that are
  statistically ambiguous. For unsupervised detection, conformal p-values.
* **Randomized smoothing** — Cohen et al. (ICML 2019) certified radius: a
  probabilistic guarantee that the *smoothed* classifier's verdict cannot change
  within an L2 ball (in per-feature-std units). The certificate applies to the
  smoothed classifier, not the base model — stated in the notes.

Every function returns a uniform display contract:
``{available, verdict, summary: [{label, value}], notes: [...], ...raw fields}``
so the frontend renders all five analyses with one generic card.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .context import REGRESSION, CLASSIFICATION, ANOMALY

SEED = 42
MAX_ROWS = 400

CHURN_MODELS = 5
CONFORMAL_ALPHA = 0.1
SMOOTH_SIGMA_REL = 0.25
SMOOTH_N_NOISE = 100
SMOOTH_M_POINTS = 80
SMOOTH_ALPHA = 0.05


def _pct(x) -> str:
    return f"{100.0 * float(x):.1f}%"


def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


def _reference(session):
    """(model, X reference DataFrame capped to MAX_ROWS, artifacts, problem_type)."""
    model, _o = session.current_model()
    sep = session.get_run("separate")
    if model is None or sep is None:
        return None, None, None, None
    art = sep.artifacts
    X = art.get("X_test")
    if X is None:
        X = art.get("X_full")
    if X is None:
        return model, None, art, session.ctx.problem_type
    X = X if isinstance(X, pd.DataFrame) else pd.DataFrame(np.asarray(X))
    if len(X) > MAX_ROWS:
        rng = np.random.RandomState(SEED)
        X = X.iloc[rng.choice(len(X), MAX_ROWS, replace=False)]
    return model, X, art, session.ctx.problem_type


def _verdict_from_rate(rate, stable=0.01, sensible=0.05) -> str:
    if rate < stable:
        return "stable"
    if rate < sensible:
        return "sensible"
    return "instable"


# ---------------------------------------------------------------------------
# 1. Numerical jitter — float32 vs float64, single-thread vs default
# ---------------------------------------------------------------------------

def numerical_jitter(session) -> dict:
    """Verdict flips induced by numerical precision and thread scheduling.

    This is the honest software-side form of "hardware jitter": non-associative
    float reductions and reduced mantissas move scores by ULPs; only points
    sitting on the decision boundary can flip. Zero flips = the deployed
    verdicts do not depend on the arithmetic environment.
    """
    model, X, _art, ptype = _reference(session)
    if model is None or X is None:
        return _unavailable("Entraînez et évaluez un modèle avant l'analyse.")
    if not hasattr(model, "predict"):
        return _unavailable("Ce détecteur (LOF classique) ne re-score pas de nouveaux points.")

    X64 = X.astype(np.float64)
    X32 = X.astype(np.float32)
    try:
        p64 = np.asarray(model.predict(X64))
        p32 = np.asarray(model.predict(X32))
    except Exception as e:
        return _unavailable(f"Re-scoring impossible ({type(e).__name__}).")

    if ptype == REGRESSION:
        tol = 1e-9 + 0.05 * float(np.std(p64.astype(float)))
        prec_flips = float(np.mean(np.abs(p64.astype(float) - p32.astype(float)) > tol))
    else:
        prec_flips = float(np.mean(p64 != p32))

    # Score-level deltas when a continuous score exists (finer than verdicts).
    max_delta = None
    scorer = getattr(model, "decision_function", None) or getattr(model, "predict_proba", None)
    deltas = None
    if scorer is not None:
        try:
            s64 = np.asarray(scorer(X64), dtype=float)
            s32 = np.asarray(scorer(X32), dtype=float)
            deltas = np.abs(s64 - s32).ravel()
            max_delta = float(np.max(deltas)) if len(deltas) else None
        except Exception:
            deltas = None

    # Thread sensitivity: single BLAS/OpenMP thread vs the default pool.
    thread_flips = None
    try:
        from threadpoolctl import threadpool_limits
        with threadpool_limits(limits=1):
            p1t = np.asarray(model.predict(X64))
        if ptype == REGRESSION:
            thread_flips = float(np.mean(np.abs(p1t.astype(float) - p64.astype(float)) > tol))
        else:
            thread_flips = float(np.mean(p1t != p64))
    except Exception:
        thread_flips = None

    worst = max(prec_flips, thread_flips or 0.0)
    verdict = _verdict_from_rate(worst)
    summary = [
        {"label": "Bascules float32 vs float64", "value": _pct(prec_flips)},
        {"label": "Bascules 1 thread vs pool", "value": _pct(thread_flips) if thread_flips is not None else "non mesurable"},
        {"label": "Écart max de score (float32 vs 64)", "value": f"{max_delta:.2e}" if max_delta is not None else "pas de score continu"},
        {"label": "Lignes testées", "value": str(len(X))},
    ]
    notes = ["Seule manifestation logicielle mesurable du « jitter matériel » : la précision "
             "flottante. Une bascule ici = un point posé sur la frontière de décision."]
    return {"available": True, "verdict": verdict, "summary": summary, "notes": notes,
            "precision_flip_rate": round(prec_flips, 4),
            "thread_flip_rate": (round(thread_flips, 4) if thread_flips is not None else None),
            "max_score_delta": max_delta,
            "score_deltas": (deltas.tolist()[:1000] if deltas is not None else None)}


# ---------------------------------------------------------------------------
# 2. Margin analysis — the at-risk population near the threshold
# ---------------------------------------------------------------------------

def _anomaly_margins(session, model, X):
    """Normalized |score - threshold| for the fitted detector."""
    if hasattr(model, "decision_function"):          # IsolationForest: 0 = threshold
        s = np.asarray(model.decision_function(X), dtype=float)
        margins = np.abs(s)
    else:                                            # LOF: stored training scores vs offset_
        mrun = session.get_run("model")
        scores = (mrun.artifacts or {}).get("scores") if mrun else None
        offset = getattr(model, "offset_", None)
        if scores is None or offset is None:
            return None
        margins = np.abs(np.asarray(scores, dtype=float) - float(offset))
    sd = float(np.std(margins)) or 1.0
    return margins / sd


def margin_analysis(session) -> dict:
    """Distance of each verdict to the decision threshold — who *would* flip.

    Deterministic complement to the jitter protocol: instead of sampling noise
    and counting flips, measure directly how much of the population sits within
    1% / 5% / 10% (of the score scale) of the threshold.
    """
    model, X, art, ptype = _reference(session)
    if model is None or X is None:
        return _unavailable("Entraînez et évaluez un modèle avant l'analyse.")
    if ptype == REGRESSION:
        return _unavailable("Pas de seuil de décision en régression : analyse non applicable.")

    notes = []
    if ptype == ANOMALY:
        margins = _anomaly_margins(session, model, X)
        if margins is None:
            return _unavailable("Scores d'anomalie indisponibles pour ce détecteur.")
        scale = "écart-type des marges"
    elif hasattr(model, "predict_proba"):
        proba = np.asarray(model.predict_proba(X), dtype=float)
        if proba.shape[1] == 2:
            margins = np.abs(proba[:, 1] - 0.5) / 0.5      # relative to the 0.5 threshold
            scale = "distance au seuil 0.5 (échelle 0-1)"
            notes.append("Seuil 0.5 par défaut — si vous déployez le seuil coût-minimal de "
                         "l'évaluation opérationnelle, la population à risque est celle autour "
                         "de CE seuil.")
        else:
            part = np.partition(proba, -2, axis=1)
            margins = part[:, -1] - part[:, -2]            # top1 - top2
            scale = "écart top1 - top2 des probabilités"
    else:
        return _unavailable("Ce modèle n'expose pas de score continu (pas de predict_proba).")

    bands = [(0.01, "à moins de 1%"), (0.05, "à moins de 5%"), (0.10, "à moins de 10%")]
    fracs = {eps: float(np.mean(margins < eps)) for eps, _lbl in bands}
    verdict = _verdict_from_rate(fracs[0.01], stable=0.01, sensible=0.05)
    summary = [{"label": f"Population {lbl} du seuil", "value": _pct(fracs[eps])}
               for eps, lbl in bands]
    summary.append({"label": "Marge médiane", "value": f"{float(np.median(margins)):.3f}"})
    summary.append({"label": "Échelle des marges", "value": scale})
    notes.append("Ces lignes sont celles qu'une perturbation quelconque (bruit, dérive, "
                 "précision flottante) ferait basculer en premier.")
    return {"available": True, "verdict": verdict, "summary": summary, "notes": notes,
            "fractions": {str(k): round(v, 4) for k, v in fracs.items()},
            "median_margin": round(float(np.median(margins)), 4),
            "margins": margins.tolist()[:1000]}


# ---------------------------------------------------------------------------
# 3. Prediction churn — structural instability across retrains
# ---------------------------------------------------------------------------

def prediction_churn(session, n_models: int = CHURN_MODELS) -> dict:
    """Re-fit the deployed model class with different seeds; measure verdict
    disagreement on the reference set (Google's "prediction churn"). High churn
    = the *model family* is unstable on these data, independent of inference.
    """
    from sklearn.base import clone

    model, X, art, ptype = _reference(session)
    if model is None or X is None:
        return _unavailable("Entraînez et évaluez un modèle avant l'analyse.")

    if ptype in (CLASSIFICATION, REGRESSION):
        X_tr, y_tr = art.get("X_train"), art.get("y_train")
        if X_tr is None or y_tr is None:
            return _unavailable("Splits d'entraînement indisponibles.")
        fit_args = (X_tr, y_tr)
        base_pred = np.asarray(model.predict(X))
    else:
        X_tr = art.get("X_full")
        if X_tr is None:
            return _unavailable("Matrice d'entraînement indisponible.")
        fit_args = None                                  # fit_predict path
        mrun = session.get_run("model")
        base_pred = np.asarray((mrun.artifacts or {}).get("predictions"))
        X = X_tr                                         # compare on the full matrix

    seeded = "random_state" in model.get_params(deep=False)
    if ptype == REGRESSION:
        tol = 1e-9 + 0.05 * float(np.std(base_pred.astype(float)))

    rates = []
    try:
        for seed in range(1, int(n_models) + 1):
            m = clone(model)
            if seeded:
                m.set_params(random_state=seed)
            if fit_args is not None:
                m.fit(*fit_args)
                p = np.asarray(m.predict(X))
            else:
                p = np.asarray(m.fit_predict(X))
            if ptype == REGRESSION:
                rates.append(float(np.mean(np.abs(p.astype(float) - base_pred.astype(float)) > tol)))
            else:
                rates.append(float(np.mean(p != base_pred)))
    except Exception as e:
        return _unavailable(f"Ré-entraînement impossible ({type(e).__name__}).")

    mean_churn = float(np.mean(rates))
    verdict = _verdict_from_rate(mean_churn)
    summary = [
        {"label": "Churn moyen vs modèle déployé", "value": _pct(mean_churn)},
        {"label": "Churn max (pire seed)", "value": _pct(max(rates))},
        {"label": "Ré-entraînements", "value": str(len(rates))},
        {"label": "Lignes comparées", "value": str(len(X))},
    ]
    notes = ["Instabilité STRUCTURELLE (le modèle ré-appris diverge), à distinguer de "
             "l'instabilité d'inférence mesurée par le protocole jitter."]
    if not seeded:
        notes.append("Modèle sans random_state : l'apprentissage est déterministe, un churn "
                     "nul est attendu par construction.")
    return {"available": True, "verdict": verdict, "summary": summary, "notes": notes,
            "mean_churn": round(mean_churn, 4),
            "rates": [round(r, 4) for r in rates], "seeded": seeded}


# ---------------------------------------------------------------------------
# 4. Conformal prediction — coverage-guaranteed uncertainty
# ---------------------------------------------------------------------------

def _conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    n = len(scores)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    k = min(max(k, 1), n)
    return float(np.sort(scores)[k - 1])


def conformal_report(session, alpha: float = CONFORMAL_ALPHA) -> dict:
    """Split-conformal diagnostic: finite-sample coverage under exchangeability.

    Classification: prediction SETS (a set that contains the true class with
    probability >= 1-alpha); the ambiguous fraction (set size > 1) is the share
    of verdicts that are statistically uncertain. Regression: intervals of
    guaranteed coverage. Anomaly: conformal p-values (alerts at level alpha have
    a false-alarm rate <= alpha under exchangeability).
    """
    model, X, art, ptype = _reference(session)
    if model is None or X is None:
        return _unavailable("Entraînez et évaluez un modèle avant l'analyse.")
    rng = np.random.RandomState(SEED)
    notes = ["Garantie de couverture finite-sample VALIDE sous hypothèse d'échangeabilité "
             "(données calib/éval de même distribution) — elle tombe en cas de dérive."]

    if ptype == ANOMALY:
        margins = _anomaly_margins(session, model, X)
        if hasattr(model, "decision_function"):
            s = np.asarray(model.decision_function(X), dtype=float)
        else:
            mrun = session.get_run("model")
            s = np.asarray((mrun.artifacts or {}).get("scores"), dtype=float)
        idx = rng.permutation(len(s))
        half = len(s) // 2
        calib, ev = s[idx[:half]], s[idx[half:]]
        # Lower score = more abnormal -> p-value = rank of the score from below.
        pvals = np.array([(np.sum(calib <= v) + 1.0) / (len(calib) + 1.0) for v in ev])
        alert_rate = float(np.mean(pvals <= alpha))
        summary = [
            {"label": f"Alertes conformes (p <= {alpha})", "value": _pct(alert_rate)},
            {"label": "Garantie", "value": f"taux de fausses alertes <= {_pct(alpha)} (échangeabilité)"},
            {"label": "Calibration / évaluation", "value": f"{len(calib)} / {len(ev)} lignes"},
        ]
        return {"available": True, "verdict": "info", "summary": summary, "notes": notes,
                "alert_rate": round(alert_rate, 4), "p_values": pvals.tolist()[:1000]}

    y = art.get("y_test")
    if y is None:
        return _unavailable("Cible de test indisponible (nécessaire pour la calibration).")
    y = np.asarray(y)
    idx = rng.permutation(len(y))
    half = len(y) // 2
    if half < 10:
        return _unavailable("Jeu de test trop petit pour une calibration conforme (>= 20 lignes).")

    Xf = art.get("X_test")
    Xf = Xf if isinstance(Xf, pd.DataFrame) else pd.DataFrame(np.asarray(Xf))
    Xc, Xe = Xf.iloc[idx[:half]], Xf.iloc[idx[half:]]
    yc, ye = y[idx[:half]], y[idx[half:]]

    if ptype == REGRESSION:
        res_c = np.abs(yc.astype(float) - np.asarray(model.predict(Xc), dtype=float))
        qhat = _conformal_quantile(res_c, alpha)
        pe = np.asarray(model.predict(Xe), dtype=float)
        cov = float(np.mean(np.abs(ye.astype(float) - pe) <= qhat))
        rel = qhat / (float(np.std(y.astype(float))) or 1.0)
        summary = [
            {"label": f"Demi-largeur d'intervalle (couverture {_pct(1 - alpha)})", "value": f"{qhat:.4g}"},
            {"label": "Couverture empirique (moitié éval)", "value": _pct(cov)},
            {"label": "Largeur relative (vs écart-type de y)", "value": f"{2 * rel:.2f}x"},
        ]
        verdict = "stable" if rel <= 0.5 else ("sensible" if rel <= 1.0 else "instable")
        return {"available": True, "verdict": verdict, "summary": summary, "notes": notes,
                "qhat": float(qhat), "coverage": round(cov, 4),
                "residuals": res_c.tolist()[:1000]}

    if not hasattr(model, "predict_proba"):
        return _unavailable("Ce modèle n'expose pas de probabilités (predict_proba).")
    classes = list(getattr(model, "classes_", []))
    col = {c: i for i, c in enumerate(classes)}
    pc = np.asarray(model.predict_proba(Xc), dtype=float)
    scores_c = np.array([1.0 - pc[i, col[yc[i]]] for i in range(len(yc)) if yc[i] in col])
    qhat = _conformal_quantile(scores_c, alpha)
    pe = np.asarray(model.predict_proba(Xe), dtype=float)
    sets = (1.0 - pe) <= qhat
    sizes = sets.sum(axis=1)
    hits = np.array([ye[i] in col and sets[i, col[ye[i]]] for i in range(len(ye))])
    cov = float(np.mean(hits))
    ambiguous = float(np.mean(sizes > 1))
    empty = float(np.mean(sizes == 0))
    verdict = _verdict_from_rate(ambiguous, stable=0.05, sensible=0.15)
    summary = [
        {"label": "Couverture empirique (moitié éval)", "value": f"{_pct(cov)} (cible {_pct(1 - alpha)})"},
        {"label": "Verdicts ambigus (ensemble > 1 classe)", "value": _pct(ambiguous)},
        {"label": "Ensembles vides (hors distribution)", "value": _pct(empty)},
        {"label": "Taille moyenne des ensembles", "value": f"{float(np.mean(sizes)):.2f}"},
    ]
    notes.append("Un verdict ambigu = le modèle ne peut PAS statistiquement trancher entre "
                 "plusieurs classes à ce niveau de confiance — à router vers un analyste.")
    return {"available": True, "verdict": verdict, "summary": summary, "notes": notes,
            "coverage": round(cov, 4), "ambiguous": round(ambiguous, 4),
            "empty": round(empty, 4), "set_sizes": sizes.tolist()[:1000]}


# ---------------------------------------------------------------------------
# 5. Randomized smoothing — certified radius (Cohen et al., ICML 2019)
# ---------------------------------------------------------------------------

def smoothing_certificate(session, sigma_rel: float = SMOOTH_SIGMA_REL,
                          n_noise: int = SMOOTH_N_NOISE, m_points: int = SMOOTH_M_POINTS,
                          alpha: float = SMOOTH_ALPHA) -> dict:
    """Certified robustness of the SMOOTHED classifier g(x) = majority vote of
    f(x + noise), noise ~ N(0, (sigma_rel * std_j)^2) per feature.

    For each point: n_noise Monte-Carlo draws, Clopper-Pearson lower bound on
    the majority-class probability, certified L2 radius sigma * PHI^-1(p_lower)
    in per-feature-std units (Cohen, Rosenfeld & Kolter, ICML 2019, Theorem 1).
    The guarantee is probabilistic (level 1-alpha) and applies to g, NOT to the
    base model f — that caveat is structural, not a defect.
    """
    from scipy.stats import beta, norm

    model, X, _art, ptype = _reference(session)
    if model is None or X is None:
        return _unavailable("Entraînez et évaluez un modèle avant l'analyse.")
    if ptype == REGRESSION:
        return _unavailable("Certification par smoothing : classification/détection uniquement.")
    if not hasattr(model, "predict"):
        return _unavailable("Ce détecteur (LOF classique) ne re-score pas de nouveaux points.")

    rng = np.random.RandomState(SEED)
    if len(X) > int(m_points):
        X = X.iloc[rng.choice(len(X), int(m_points), replace=False)]
    sigma = (X.std(ddof=0).fillna(0.0).to_numpy() * float(sigma_rel))

    m, n = len(X), int(n_noise)
    base = np.repeat(X.to_numpy(dtype=float), n, axis=0)
    noisy = base + rng.normal(0.0, 1.0, size=base.shape) * sigma
    try:
        preds = np.asarray(model.predict(pd.DataFrame(noisy, columns=X.columns)))
        base_preds = np.asarray(model.predict(X))
    except Exception as e:
        return _unavailable(f"Re-scoring impossible ({type(e).__name__}).")
    preds = preds.reshape(m, n)

    radii, certified, agree = [], 0, 0
    for i in range(m):
        vals, counts = np.unique(preds[i], return_counts=True)
        k = int(counts.max())
        top = vals[int(counts.argmax())]
        if top == base_preds[i]:
            agree += 1
        p_lower = float(beta.ppf(alpha, k, n - k + 1)) if k < n else float((alpha) ** (1.0 / n))
        if p_lower > 0.5:
            radii.append(float(sigma_rel) * float(norm.ppf(p_lower)))
            certified += 1
    frac_cert = certified / m
    med_radius = float(np.median(radii)) if radii else None
    verdict = ("stable" if frac_cert >= 0.9 else ("sensible" if frac_cert >= 0.7 else "instable"))
    summary = [
        {"label": "Points certifiés (rayon > 0)", "value": _pct(frac_cert)},
        {"label": "Rayon certifié médian", "value": (f"{med_radius:.3f} écart-type" if med_radius is not None else "aucun")},
        {"label": "Accord classifieur lissé vs base", "value": _pct(agree / m)},
        {"label": "Protocole", "value": f"{m} points x {n} bruits, sigma = {sigma_rel} écart-type, confiance {_pct(1 - alpha)}"},
    ]
    notes = [
        "Certificat de Cohen et al. (ICML 2019, Theorem 1) : le verdict du classifieur LISSÉ "
        "ne peut pas changer dans une boule L2 de ce rayon (unités : écart-type par variable).",
        "La garantie porte sur le classifieur lissé g (vote majoritaire sous bruit), pas sur "
        "le modèle de base f — c'est la limite structurelle de la méthode.",
    ]
    return {"available": True, "verdict": verdict, "summary": summary, "notes": notes,
            "certified_fraction": round(frac_cert, 4), "median_radius": med_radius,
            "radii": [round(r, 4) for r in radii]}


ANALYSES = {
    "numerical": numerical_jitter,
    "margin": margin_analysis,
    "churn": prediction_churn,
    "conformal": conformal_report,
    "smoothing": smoothing_certificate,
}
