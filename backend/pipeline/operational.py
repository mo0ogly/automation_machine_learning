"""
operational.py — Operational evaluation for SOC / threat-intel use.

The standard Evaluation stage answers "how good is this model on the test set?".
This module answers the questions a CERT / SOC analyst actually asks before
putting a detector into production:

    * At which SCORE THRESHOLD do I operate? (0.5 is almost never right in cyber)
    * What does a false negative (missed attack) vs a false positive (wasted
      triage) actually COST me, and which threshold minimises that cost?
    * If my team can only review N alerts a day, what detection do I get?
    * Are the model's probabilities CALIBRATED enough to triage by score?
    * Under heavy class imbalance (attacks are rare), what do the robust metrics
      (MCC, balanced accuracy, kappa) say?

Everything here is computed from the held-out test predictions ONLY — no model
re-fitting — so an interactive operating-point endpoint can recompute at any
threshold/cost instantly. The public entry point ``operational_evaluation``
dispatches on the problem type; each paradigm surfaces only what applies to it
(binary detection gets the full arsenal; anomaly detection is a score-threshold
task; regression gets tolerance bands; multiclass gets a one-vs-rest operating
point; clustering is not applicable).
"""

from __future__ import annotations

import numpy as np

from sklearn.metrics import (
    matthews_corrcoef, balanced_accuracy_score, cohen_kappa_score,
    brier_score_loss,
)

from .context import REGRESSION, CLASSIFICATION, ANOMALY, CLUSTERING

# Default cost ratio: in cyber a missed detection usually hurts far more than a
# false alert. The expert overrides both from the UI.
DEFAULT_COST_FN = 10.0
DEFAULT_COST_FP = 1.0
_FBETA = 2.0  # recall-weighted F-beta: missing an attack is worse than a false alert


# ── binary detection ─────────────────────────────────────────────────────────
def _confusion_counts(y_true, y_score, threshold, pos_label=1):
    """(tp, fp, tn, fn) for 'flag as positive when score >= threshold'."""
    y = np.asarray(y_true)
    pos = (y == pos_label)
    flagged = np.asarray(y_score) >= threshold
    tp = int(np.sum(flagged & pos))
    fp = int(np.sum(flagged & ~pos))
    fn = int(np.sum(~flagged & pos))
    tn = int(np.sum(~flagged & ~pos))
    return tp, fp, tn, fn


def _point_metrics(tp, fp, tn, fn, cost_fn, cost_fp):
    """Precision / recall / specificity / F-beta / alert volume / expected cost."""
    n = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0        # detection rate / TPR
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    b2 = _FBETA ** 2
    denom = (b2 * precision) + recall
    fbeta = (1 + b2) * precision * recall / denom if denom else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    cost = cost_fn * fn + cost_fp * fp
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 4), "recall": round(recall, 4),
        "specificity": round(specificity, 4), "fpr": round(fpr, 4),
        "f1": round(f1, 4), "fbeta": round(fbeta, 4),
        "alerts": tp + fp, "alert_rate": round((tp + fp) / n, 4) if n else 0.0,
        "cost": round(cost, 2),
    }


def confusion_at(y_true, y_score, threshold, pos_label=1,
                 cost_fn=DEFAULT_COST_FN, cost_fp=DEFAULT_COST_FP):
    """Business-labelled confusion + metrics at one operating threshold."""
    tp, fp, tn, fn = _confusion_counts(y_true, y_score, threshold, pos_label)
    m = _point_metrics(tp, fp, tn, fn, cost_fn, cost_fp)
    m["threshold"] = round(float(threshold), 4)
    # SOC reading of each cell.
    m["cells"] = {
        "true_positive": {"label": "Détection correcte", "count": tp},
        "false_negative": {"label": "Attaque manquée", "count": fn},
        "false_positive": {"label": "Fausse alerte", "count": fp},
        "true_negative": {"label": "Trafic normal", "count": tn},
    }
    return m


def _threshold_grid(y_score, n=101):
    """A dense, data-aware threshold grid over the observed score range."""
    s = np.asarray(y_score, dtype=float)
    lo, hi = float(np.min(s)), float(np.max(s))
    if hi <= lo:
        return np.array([lo])
    return np.linspace(lo, hi, n)


def threshold_sweep(y_true, y_score, pos_label=1,
                    cost_fn=DEFAULT_COST_FN, cost_fp=DEFAULT_COST_FP):
    """Sweep every threshold; return the per-threshold operating curve + the
    recommended operating points (min expected cost, max F-beta, Youden's J,
    and a fixed 1% false-positive-rate budget)."""
    grid = _threshold_grid(y_score)
    rows = []
    for t in grid:
        tp, fp, tn, fn = _confusion_counts(y_true, y_score, t, pos_label)
        m = _point_metrics(tp, fp, tn, fn, cost_fn, cost_fp)
        m["threshold"] = round(float(t), 4)
        m["youden"] = round(m["recall"] - m["fpr"], 4)
        rows.append(m)

    def _best(key, reverse=False):
        return min(rows, key=lambda r: (-r[key] if reverse else r[key]))["threshold"]

    # Fixed alert-budget point: highest recall while keeping FPR <= 1%.
    under_budget = [r for r in rows if r["fpr"] <= 0.01]
    fixed_fpr = (max(under_budget, key=lambda r: r["recall"])["threshold"]
                 if under_budget else _best("fpr"))
    recommended = {
        "min_cost": _best("cost"),
        "max_fbeta": _best("fbeta", reverse=True),
        "youden": _best("youden", reverse=True),
        "fpr_1pct": fixed_fpr,
    }
    return rows, recommended


def calibration(y_true, y_score, pos_label=1, n_bins=10):
    """Reliability curve + Brier score + Expected Calibration Error (ECE).

    Well-calibrated => predicted probability ~ observed frequency, so an analyst
    can trust "score 0.8" to mean "~80% of these are real".
    """
    y = (np.asarray(y_true) == pos_label).astype(int)
    p = np.clip(np.asarray(y_score, dtype=float), 0, 1)
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.digitize(p, bins) - 1
    idx = np.clip(idx, 0, n_bins - 1)
    curve, ece, n = [], 0.0, len(p)
    for b in range(n_bins):
        mask = idx == b
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        conf = float(p[mask].mean())
        freq = float(y[mask].mean())
        curve.append({"bin": round((bins[b] + bins[b + 1]) / 2, 3),
                      "confidence": round(conf, 4), "frequency": round(freq, 4),
                      "count": cnt})
        ece += (cnt / n) * abs(conf - freq)
    try:
        brier = float(brier_score_loss(y, p))
    except Exception:
        brier = None
    return {"curve": curve, "brier": round(brier, 4) if brier is not None else None,
            "ece": round(float(ece), 4)}


def robust_metrics(y_true, y_pred):
    """Imbalance-robust scores: MCC, balanced accuracy, Cohen's kappa."""
    try:
        mcc = float(matthews_corrcoef(y_true, y_pred))
    except Exception:
        mcc = None
    try:
        bacc = float(balanced_accuracy_score(y_true, y_pred))
    except Exception:
        bacc = None
    try:
        kappa = float(cohen_kappa_score(y_true, y_pred))
    except Exception:
        kappa = None
    return {"mcc": round(mcc, 4) if mcc is not None else None,
            "balanced_accuracy": round(bacc, 4) if bacc is not None else None,
            "cohen_kappa": round(kappa, 4) if kappa is not None else None}


def alert_budget(y_true, y_score, pos_label=1, ks=(10, 25, 50, 100)):
    """Precision@k / detection@k: if the SOC reviews the k highest-scoring
    events, how many real positives does it catch, and how pure is the queue?"""
    y = (np.asarray(y_true) == pos_label).astype(int)
    order = np.argsort(-np.asarray(y_score, dtype=float))
    y_sorted = y[order]
    total_pos = int(y.sum())
    rows = []
    for k in ks:
        k = int(min(k, len(y_sorted)))
        if k <= 0:
            continue
        caught = int(y_sorted[:k].sum())
        rows.append({"k": k, "precision_at_k": round(caught / k, 4),
                     "detection_at_k": round(caught / total_pos, 4) if total_pos else 0.0,
                     "caught": caught, "total_positives": total_pos})
    return rows


def _binary_operational(y_true, y_score, pos_label, cost_fn, cost_fp, current_t=0.5):
    sweep, recommended = threshold_sweep(y_true, y_score, pos_label, cost_fn, cost_fp)
    current = confusion_at(y_true, y_score, current_t, pos_label, cost_fn, cost_fp)
    y_pred = (np.asarray(y_score) >= current_t).astype(int)
    y_true_bin = (np.asarray(y_true) == pos_label).astype(int)
    return {
        "mode": "binary",
        "applicable": True,
        "current": current,
        "threshold_sweep": sweep,
        "recommended_thresholds": recommended,
        "calibration": calibration(y_true, y_score, pos_label),
        "robust_metrics": robust_metrics(y_true_bin, y_pred),
        "alert_budget": alert_budget(y_true, y_score, pos_label),
        "cost": {"cost_fn": cost_fn, "cost_fp": cost_fp},
        "positive_class": str(pos_label),
    }


# ── other paradigms (adaptive, lighter) ──────────────────────────────────────
def _regression_operational(y_true, y_pred):
    """Tolerance bands: share of predictions within ±X of the truth — the
    operational reading of a regressor (no threshold)."""
    y, p = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    err = np.abs(y - p)
    spread = float(np.std(y)) or 1.0
    bands = []
    for frac in (0.05, 0.1, 0.2, 0.5):
        tol = frac * spread
        bands.append({"tolerance": round(tol, 3), "tolerance_sigma": frac,
                      "within": round(float(np.mean(err <= tol)), 4)})
    return {"mode": "regression", "applicable": True, "tolerance_bands": bands,
            "mae": round(float(np.mean(err)), 4), "target_std": round(spread, 4)}


def _anomaly_operational(scores, preds):
    """Anomaly detection is a score-threshold task: how many alerts at each
    quantile of the anomaly score (lower = more abnormal)."""
    s = np.asarray(scores, dtype=float)
    n = len(s)
    rows = []
    for q in (0.005, 0.01, 0.02, 0.05, 0.1):
        thr = float(np.quantile(s, q))
        flagged = int(np.sum(s <= thr))
        rows.append({"quantile": q, "score_threshold": round(thr, 4),
                     "alerts": flagged, "alert_rate": round(flagged / n, 4) if n else 0.0,
                     "alerts_per_1000": round(1000 * flagged / n, 1) if n else 0.0})
    flagged_now = int(np.sum(np.asarray(preds) == -1)) if preds is not None else None
    return {"mode": "anomaly", "applicable": True, "budget_curve": rows,
            "flagged_current": flagged_now, "n": n,
            "note": ("Sans vérité terrain, on lit le VOLUME d'alertes par seuil ; "
                     "le tri par score reste valide pour la revue analyste.")}


def multiclass_operating_point(y_true, proba, classes, focus_idx,
                               cost_fn=DEFAULT_COST_FN, cost_fp=DEFAULT_COST_FP):
    """One-vs-rest operating point for a focus class (e.g. escalate 'critical').
    Reuses the binary machinery on the reduction {focus vs the rest}."""
    y = np.asarray(y_true)
    focus = classes[focus_idx]
    y_bin = (y == focus).astype(int)
    p_focus = np.asarray(proba)[:, focus_idx]
    out = _binary_operational(y_bin, p_focus, 1, cost_fn, cost_fp)
    out["mode"] = "multiclass_ovr"
    out["focus_class"] = str(focus)
    out["classes"] = [str(c) for c in classes]
    out["focus_index"] = int(focus_idx)
    return out


# ── public dispatcher ────────────────────────────────────────────────────────
def operational_evaluation(problem_type, *, y_true=None, y_score=None, y_pred=None,
                           proba=None, classes=None, pos_label=1, focus_idx=None,
                           scores=None, preds=None, threshold=0.5,
                           cost_fn=DEFAULT_COST_FN, cost_fp=DEFAULT_COST_FP):
    """Route to the paradigm-appropriate operational analysis.

    Only the arguments a given paradigm needs must be supplied; the caller
    (evaluate.py / the operating-point endpoint) fills them from the stored test
    predictions, so nothing here re-fits a model.
    """
    if problem_type == CLASSIFICATION:
        if proba is not None and classes is not None and len(classes) > 2:
            if focus_idx is None:
                # Default to the RAREST class — usually the operational 'alert' class
                # (e.g. 'critical' for CVE severity), the one worth an OVR operating point.
                counts = [int(np.sum(np.asarray(y_true) == c)) for c in classes]
                fi = int(np.argmin(counts))
            else:
                fi = int(focus_idx)
            fi = max(0, min(fi, len(classes) - 1))
            return multiclass_operating_point(y_true, proba, classes, fi, cost_fn, cost_fp)
        if y_score is not None:
            return _binary_operational(y_true, y_score, pos_label, cost_fn, cost_fp, threshold)
        return {"mode": "classification", "applicable": False,
                "reason": "Modèle sans probabilités — pas d'analyse de seuil."}
    if problem_type == ANOMALY:
        return _anomaly_operational(scores, preds)
    if problem_type == REGRESSION:
        return _regression_operational(y_true, y_pred)
    if problem_type == CLUSTERING:
        return {"mode": "clustering", "applicable": False,
                "reason": "Non supervisé : pas de point de fonctionnement (voir profils de clusters)."}
    return {"mode": "unknown", "applicable": False, "reason": "Type de problème non géré."}


def _pt_at(sweep, threshold):
    """The swept operating row closest to a threshold."""
    if not sweep:
        return None
    return min(sweep, key=lambda r: abs(r["threshold"] - threshold))


def soc_playbook(op, target=None):
    """A deployment-oriented SOC / threat-intel dossier, computed from the
    operational analysis — not boilerplate: the recommended operating point,
    the resulting alert load, and the honest operational limits all come from
    the model's own test predictions."""
    mode = op.get("mode")
    what = f"« {target} »" if target else "l'événement cible"
    sections = []

    if mode in ("binary", "multiclass_ovr"):
        reco_t = op["recommended_thresholds"]["min_cost"]
        row = _pt_at(op["threshold_sweep"], reco_t) or op["current"]
        focus = op.get("focus_class")
        headline = (f"Détecteur : escalade la classe « {focus} » vs le reste."
                    if mode == "multiclass_ovr"
                    else f"Détecteur binaire pour {what}.")
        sections.append({"heading": "Ce que fait le modèle", "text": headline})
        sections.append({"heading": "Point de fonctionnement recommandé (coût minimal)", "text": (
            f"Seuil {reco_t:.3f} → rappel (détection) {row['recall']:.0%}, "
            f"précision {row['precision']:.0%}, {row['alert_rate']:.1%} des événements alertés. "
            "Ajustez le curseur selon votre tolérance : plus bas = rate moins d'attaques mais "
            "plus de fausses alertes.")})
        cal = op.get("calibration") or {}
        ece = cal.get("ece")
        sections.append({"heading": "Volume d'alertes", "text": (
            f"À ce seuil, comptez ~{round(1000 * row['alert_rate'])} alertes pour 1000 événements. "
            "Dimensionnez la file de triage en conséquence (voir budget d'alertes).")})
        sections.append({"heading": "Déploiement SOC", "text": (
            "1) Ingestion des événements → 2) scoring par le modèle → 3) seuil de décision "
            "ci-dessus → 4) enrichissement (contexte actif, IOC) → 5) routage vers la file "
            "analyste (tri par score décroissant).")})
        sections.append({"heading": "Usage threat intel", "text": (
            "Le score calibré prioritise le tri : traitez d'abord les scores les plus élevés. "
            + (f"Calibration actuelle ECE={ece} — " if ece is not None else "")
            + "un score de 0.8 doit correspondre à ~80% de vrais positifs pour être fiable.")})
        limits = ["Les probabilités doivent rester calibrées après mise en production (re-vérifier périodiquement).",
                  "Les attaques évoluent : ré-évaluer sur des données récentes (dérive temporelle).",
                  "Un seuil optimal sur le test ne l'est pas forcément en production (surveiller le FPR réel)."]
        sections.append({"heading": "Limites opérationnelles", "list": limits})

    elif mode == "anomaly":
        sections.append({"heading": "Ce que fait le modèle",
                         "text": "Détecteur d'anomalies non supervisé : signale les événements atypiques."})
        sections.append({"heading": "Point de fonctionnement", "text": (
            "Pas de vérité terrain : choisissez un quantile du score d'anomalie selon le "
            "volume d'alertes soutenable (voir budget d'alertes). Le tri par score reste "
            "valable pour la revue analyste.")})
        sections.append({"heading": "Déploiement SOC", "text": (
            "Scoring en continu → seuil sur le quantile choisi → revue des N plus atypiques → "
            "confirmation analyste (les anomalies ne sont pas toutes malveillantes).")})
        sections.append({"heading": "Limites opérationnelles", "list": [
            "Sans labels, impossible de mesurer précision/rappel — le volume d'alertes est le seul levier.",
            "Une anomalie n'est pas une attaque : nécessite une validation humaine.",
            "Sensible à la dérive : le 'normal' d'hier n'est pas celui de demain."]})

    elif mode == "regression":
        sections.append({"heading": "Ce que fait le modèle",
                         "text": f"Estimateur numérique de {what} (pas un détecteur à seuil)."})
        sections.append({"heading": "Usage", "text": (
            "Lisez la bande de tolérance : la part des prédictions à ±X de la vérité indique la "
            "fiabilité opérationnelle. Utile pour prioriser (score de risque continu), pas pour "
            "une décision binaire.")})
        sections.append({"heading": "Limites opérationnelles", "list": [
            "L'erreur moyenne masque les grands écarts : inspecter les résidus.",
            "Extrapolation hors du domaine d'entraînement = peu fiable."]})
    else:
        return None
    return {"mode": mode, "sections": sections}


def build_operational(session, threshold=0.5, cost_fn=DEFAULT_COST_FN,
                      cost_fp=DEFAULT_COST_FP, focus_idx=None):
    """Assemble the operational analysis from a session's STORED test predictions.

    Used by both the Evaluation stage (defaults) and the interactive
    operating-point endpoint (analyst-chosen threshold/cost) — no model re-fit.
    Returns ``{"applicable": False, ...}`` when the paradigm/model can't support it.
    """
    model, _origin = session.current_model()
    sep = session.get_run("separate")
    ptype = session.ctx.problem_type
    target = getattr(session.ctx, "target_col", None)
    if model is None or sep is None:
        return {"mode": "none", "applicable": False, "reason": "Aucun modèle évalué."}
    art = sep.artifacts

    op = None
    if ptype == ANOMALY:
        mrun = session.get_run("model")
        a = mrun.artifacts if mrun else {}
        op = _anomaly_operational(a.get("scores"), a.get("predictions"))
    elif ptype == REGRESSION:
        X_test, y_test = art.get("X_test"), art.get("y_test")
        if X_test is None:
            return {"mode": "regression", "applicable": False, "reason": "Pas de jeu de test."}
        op = _regression_operational(y_test, model.predict(X_test))
    elif ptype == CLASSIFICATION:
        X_test, y_test = art.get("X_test"), art.get("y_test")
        if X_test is None or not hasattr(model, "predict_proba"):
            return {"mode": "classification", "applicable": False,
                    "reason": "Modèle sans probabilités — pas d'analyse de seuil."}
        try:
            proba = model.predict_proba(X_test)
        except Exception:
            return {"mode": "classification", "applicable": False,
                    "reason": "Probabilités indisponibles."}
        model_classes = list(getattr(model, "classes_", np.unique(y_test)))
        le = art.get("label_encoder")
        if proba.ndim == 2 and proba.shape[1] > 2:
            op = operational_evaluation(
                CLASSIFICATION, y_true=np.asarray(y_test), proba=proba,
                classes=model_classes, focus_idx=focus_idx, cost_fn=cost_fn, cost_fp=cost_fp)
            if le is not None and op.get("focus_class") is not None:
                try:  # show the human class name, not its encoded integer
                    op["focus_class"] = str(le.inverse_transform([int(op["focus_class"])])[0])
                    op["classes"] = [str(c) for c in le.inverse_transform(
                        [int(c) for c in model_classes])]
                except Exception:
                    pass
        else:
            pos_label = model_classes[-1]
            pos_idx = model_classes.index(pos_label)
            y_score = proba[:, pos_idx]
            op = operational_evaluation(
                CLASSIFICATION, y_true=np.asarray(y_test), y_score=y_score, pos_label=pos_label,
                threshold=threshold, cost_fn=cost_fn, cost_fp=cost_fp)
            if le is not None:
                try:
                    op["positive_class"] = str(le.inverse_transform([int(pos_label)])[0])
                except Exception:
                    pass
    else:
        return {"mode": "clustering", "applicable": False,
                "reason": "Non supervisé : pas de point de fonctionnement."}

    if op and op.get("applicable"):
        pb = soc_playbook(op, target=target)
        if pb:
            op["soc_playbook"] = pb
    return op
