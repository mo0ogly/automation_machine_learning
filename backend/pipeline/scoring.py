"""
scoring.py — Universal serving layer (the engine behind "Le modèle en action").

Turns user-friendly RAW inputs (the original columns, e.g. LotArea / Neighborhood)
into correct model predictions, for ANY dataset and paradigm the pipeline produced.

Why a dedicated layer: the model is trained on the TRANSFORMED feature space
(scaled / one-hot / ordinal-encoded, often hundreds of columns). Feeding raw values
straight to ``model.predict`` is wrong — a StandardScaler expects standardized input,
so a raw ``LotArea=8450`` is read as a +8450σ outlier. This layer replays the exact
data-prep the session was trained with (clean → transform → integrate) on the original
frame AUGMENTED with the queried row(s), then slices the transformed row back out.

Consistency: encoders/scalers are fit on the full frame at training time (see the note
in separate.py), so re-fitting on ``raw_df + new_rows`` reproduces the same transform.
Row-dropping steps (dedup, outlier removal, univariate exclusion, missing-target drop)
are training-time only and are neutralised for serving so the queried row always
survives; they never change how a single row is transformed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import diagnostics as dg
from . import typology as typ
from .context import REGRESSION, CLASSIFICATION, CLUSTERING, ANOMALY
from .stages import clean, transform, integrate

# Clean options that DROP rows — neutralised for serving (the queried row must survive).
_CLEAN_SERVING_OVERRIDE = {"drop_duplicates": False, "outlier_method": "none", "exclude_column": ""}
_PRIMARY_K = 8  # how many top-importance fields the UI features by default


# ── small helpers ────────────────────────────────────────────────────────────
def _native(v):
    """numpy / pandas scalar -> JSON-native python."""
    if v is None or (np.isscalar(v) and pd.isna(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.str_,)):
        return str(v)
    return v


def _cfg(session, stage_id) -> dict:
    r = session.get_run(stage_id)
    return dict(r.config) if (r and r.config) else {}


def _raw_importance(session) -> dict:
    """Map model importances (on the encoded feature space) back to RAW columns."""
    sep, mdl = session.get_run("separate"), session.get_run("model")
    if not sep or not mdl:
        return {}
    feats = sep.artifacts.get("feature_names") or []
    model = mdl.artifacts.get("model")
    vec = None
    if hasattr(model, "feature_importances_"):
        vec = np.asarray(model.feature_importances_, dtype=float).ravel()
    elif hasattr(model, "coef_"):
        c = np.asarray(model.coef_, dtype=float)
        vec = np.abs(c).sum(axis=0).ravel() if c.ndim > 1 else np.abs(c).ravel()
    if vec is None or len(vec) != len(feats):
        return {}
    raw_cols = [c for c in session.raw_df.columns if c != session.ctx.target_col]
    out: dict = {}
    for f, w in zip(feats, vec):
        owner = f
        if f not in raw_cols:  # one-hot column "RawCol_Value" -> credit the raw column
            cand = [rc for rc in raw_cols if f.startswith(str(rc) + "_")]
            owner = max(cand, key=len) if cand else f
        out[owner] = out.get(owner, 0.0) + float(w)
    tot = sum(out.values()) or 1.0
    return {k: v / tot for k, v in out.items()}


def _nice_step(s: pd.Series) -> float:
    rng = float(s.max() - s.min())
    if rng <= 0:
        return 1.0
    if (s.dropna() % 1 == 0).all() and rng <= 5000:
        return 1.0
    step = rng / 100.0
    return round(step, 4) if step < 1 else float(round(step))


def _target_stats(session) -> dict:
    ctx, raw, target = session.ctx, session.raw_df, session.ctx.target_col
    out = {"problem_type": ctx.problem_type}
    ev = session.get_run("evaluate")
    if ctx.problem_type == REGRESSION and target in raw.columns:
        s = pd.to_numeric(raw[target], errors="coerce").dropna()
        if len(s):
            out.update({"min": float(s.min()), "max": float(s.max()), "median": float(s.median())})
        if ev:
            out["rmse"] = ev.result.get("report", {}).get("RMSE")
    if ctx.problem_type == CLASSIFICATION:
        sep = session.get_run("separate")
        le = sep.artifacts.get("label_encoder") if sep else None
        if le is not None:
            out["classes"] = [str(c) for c in le.classes_]
        elif target in raw.columns:
            out["classes"] = [str(c) for c in sorted(raw[target].dropna().unique())]
    return out


# ── public: dynamic form schema ──────────────────────────────────────────────
def serving_schema(session) -> dict:
    """A friendly, dataset-agnostic input schema: one control per ORIGINAL column."""
    ctx, raw, target = session.ctx, session.raw_df, session.ctx.target_col
    dropped = set((_cfg(session, "clean").get("dropped_columns")) or [])
    ids = set(dg.identifier_columns(raw, target))
    t = typ.classify(raw, target)
    ordinals, nominal = t["ordinale"], set(t["nominale"])
    imp = _raw_importance(session)

    fields = []
    for c in raw.columns:
        if c == target or c in dropped or c in ids:
            continue
        s = raw[c]
        if c in ordinals:
            cats = list(ordinals[c])
            mode = s.dropna().astype(str).mode()
            fields.append({"name": str(c), "kind": "categorical", "ordinal": True,
                           "categories": cats,
                           "default": (str(mode.iloc[0]) if not mode.empty else (cats[0] if cats else "")),
                           "importance": imp.get(c)})
        elif c in nominal or not pd.api.types.is_numeric_dtype(s):
            cats = sorted(s.dropna().astype(str).unique().tolist())
            mode = s.dropna().astype(str).mode()
            fields.append({"name": str(c), "kind": "categorical", "ordinal": False,
                           "categories": cats[:50],
                           "default": (str(mode.iloc[0]) if not mode.empty else (cats[0] if cats else "")),
                           "importance": imp.get(c)})
        else:
            sn = pd.to_numeric(s, errors="coerce").dropna()
            if sn.empty:
                continue
            fields.append({"name": str(c), "kind": "numeric",
                           "min": float(sn.min()), "max": float(sn.max()),
                           "median": float(sn.median()),
                           "q1": float(sn.quantile(0.25)), "q3": float(sn.quantile(0.75)),
                           "step": _nice_step(sn), "default": float(sn.median()),
                           "importance": imp.get(c)})

    fields.sort(key=lambda f: (f.get("importance") is None, -(f.get("importance") or 0.0)))
    for i, f in enumerate(fields):
        f["primary"] = i < _PRIMARY_K
    return {
        "problem_type": ctx.problem_type,
        "target": target,
        "supervised": ctx.supervised,
        "fields": fields,
        "baseline": {f["name"]: f["default"] for f in fields},  # a "typical" row
        "target_stats": _target_stats(session),
    }


# ── public: transform + predict ──────────────────────────────────────────────
def transform_rows(session, rows: list) -> pd.DataFrame:
    """Replay clean→transform→integrate on raw_df + ``rows``; return the rows' feature matrix."""
    ctx, base, target = session.ctx, session.raw_df, session.ctx.target_col
    n = len(rows)
    if n == 0:
        sep = session.get_run("separate")
        return pd.DataFrame(columns=(sep.artifacts.get("feature_names") if sep else []))

    new = pd.DataFrame(rows)
    for c in base.columns:                       # align to the raw schema
        if c not in new.columns:
            new[c] = np.nan
    new = new[list(base.columns)]
    for c in base.columns:                       # coerce + complete with median / mode
        if pd.api.types.is_numeric_dtype(base[c]):
            new[c] = pd.to_numeric(new[c], errors="coerce")
        if c == target:
            continue
        if new[c].isna().any():
            if pd.api.types.is_numeric_dtype(base[c]):
                fill = pd.to_numeric(base[c], errors="coerce").median()
            else:
                m = base[c].dropna().astype(str).mode()
                fill = m.iloc[0] if not m.empty else "None"
            new[c] = new[c].where(new[c].notna(), fill)
    if ctx.supervised and target in base.columns:  # a valid target so clean keeps the row
        if pd.api.types.is_numeric_dtype(base[target]):
            new[target] = pd.to_numeric(base[target], errors="coerce").median()
        else:
            m = base[target].dropna().astype(str).mode()
            new[target] = m.iloc[0] if not m.empty else "None"

    aug = pd.concat([base, new], ignore_index=True)
    clean_cfg = {**_cfg(session, "clean"), **_CLEAN_SERVING_OVERRIDE}
    if clean_cfg.get("impute_num") == "drop_rows":
        clean_cfg["impute_num"] = "median"
    if clean_cfg.get("impute_cat") == "drop_rows":
        clean_cfg["impute_cat"] = "constant"

    df1, _ = clean.run(aug, clean_cfg, ctx, make_plots=False)
    df2, _ = transform.run(df1, _cfg(session, "transform"), ctx, make_plots=False)
    df3, _ = integrate.run(df2, _cfg(session, "integrate"), ctx, make_plots=False)

    sep = session.get_run("separate")
    feats = (sep.artifacts.get("feature_names") if sep else None) or [c for c in df3.columns if c != target]
    X = df3.reindex(columns=feats, fill_value=0)
    return X.tail(n).reset_index(drop=True)   # the appended rows (no drops -> order stable)


def predict_rows(session, rows: list) -> list:
    """Predict for raw input rows; output shape adapts to the problem type."""
    ctx = session.ctx
    model, _origin = session.current_model()
    if model is None:
        raise ValueError("Aucun modèle entraîné. Lancez Séparation + Modélisation d'abord.")
    X = transform_rows(session, rows)
    sep = session.get_run("separate")
    le = sep.artifacts.get("label_encoder") if sep else None
    pt = ctx.problem_type
    out = []

    if pt == CLASSIFICATION:
        preds = model.predict(X)
        proba = model.predict_proba(X) if hasattr(model, "predict_proba") else None
        classes = [str(c) for c in (le.classes_ if le is not None else getattr(model, "classes_", []))]
        for i, p in enumerate(preds):
            label = le.inverse_transform([int(p)])[0] if le is not None else p
            rec = {"prediction": _native(label)}
            if proba is not None:
                rec["proba"] = [{"label": classes[j] if j < len(classes) else str(j),
                                 "p": float(proba[i][j])} for j in range(proba.shape[1])]
            out.append(rec)
    elif pt == CLUSTERING:
        preds = model.predict(X) if hasattr(model, "predict") else [None] * len(X)
        for p in preds:
            out.append({"prediction": (None if p is None else int(p)), "kind": "cluster"})
    elif pt == ANOMALY:
        preds = model.predict(X) if hasattr(model, "predict") else [None] * len(X)
        score = model.decision_function(X) if hasattr(model, "decision_function") else [None] * len(X)
        for i, p in enumerate(preds):
            out.append({"prediction": (None if p is None else ("anomalie" if int(p) == -1 else "normal")),
                        "score": _native(score[i]), "kind": "anomaly"})
    else:  # regression
        for p in model.predict(X):
            out.append({"prediction": float(p)})
    return out


def predict_one(session, row: dict) -> dict:
    return predict_rows(session, [dict(row)])[0]


# ── public: what-if sensitivity ──────────────────────────────────────────────
def _proba_of(rec: dict, label) -> float:
    for d in rec.get("proba") or []:
        if str(d["label"]) == str(label):
            return float(d["p"])
    return 0.0


def sensitivity(session, base_row: dict, feature: str, points: int = 21) -> dict:
    """Sweep one feature across its range; return the model's response curve."""
    schema = serving_schema(session)
    field = next((f for f in schema["fields"] if f["name"] == feature), None)
    if field is None:
        raise ValueError(f"Variable inconnue : {feature}")
    rows, xs = [], []
    if field["kind"] == "numeric":
        for v in np.linspace(field["min"], field["max"], max(3, int(points))):
            r = dict(base_row); r[feature] = float(v); rows.append(r); xs.append(float(v))
    else:
        for v in field["categories"]:
            r = dict(base_row); r[feature] = v; rows.append(r); xs.append(v)
    preds = predict_rows(session, rows)
    pt = schema["problem_type"]
    y = [(_proba_of(p, predict_one(session, base_row)["prediction"]) if pt == CLASSIFICATION
          else (p.get("score") if pt == ANOMALY else p.get("prediction"))) for p in preds]
    return {"feature": feature, "kind": field["kind"], "problem_type": pt,
            "x": xs, "y": [_native(v) for v in y],
            "labels": [p.get("prediction") for p in preds] if pt == CLASSIFICATION else None}


def tornado(session, base_row: dict, top_k: int = _PRIMARY_K) -> dict:
    """Local one-at-a-time impact of each top feature on THIS prediction (low vs high)."""
    schema = serving_schema(session)
    pt = schema["problem_type"]
    ranked = [f for f in schema["fields"] if f.get("importance") is not None] or schema["fields"]
    fields = ranked[:top_k]
    base_pred = predict_one(session, base_row)

    rows, meta = [], []
    for f in fields:
        if f["kind"] == "numeric":
            lo, hi = f.get("q1", f["min"]), f.get("q3", f["max"])
        else:
            cats = f["categories"] or [""]
            lo, hi = cats[0], cats[-1]
        r_lo = dict(base_row); r_lo[f["name"]] = lo
        r_hi = dict(base_row); r_hi[f["name"]] = hi
        rows += [r_lo, r_hi]
        meta.append((f["name"], lo, hi))

    preds = predict_rows(session, rows)
    bars = []
    for i, (name, lo, hi) in enumerate(meta):
        plo, phi = preds[2 * i], preds[2 * i + 1]
        if pt == CLASSIFICATION:
            cls = base_pred["prediction"]
            vlo, vhi = _proba_of(plo, cls), _proba_of(phi, cls)
        elif pt == ANOMALY:
            vlo, vhi = (plo.get("score") or 0.0), (phi.get("score") or 0.0)
        else:
            vlo, vhi = plo.get("prediction"), phi.get("prediction")
        bars.append({"feature": name, "low": _native(lo), "high": _native(hi),
                     "v_low": _native(vlo), "v_high": _native(vhi),
                     "delta": _native((vhi or 0) - (vlo or 0))})
    bars.sort(key=lambda b: -abs(b["delta"] or 0))
    return {"problem_type": pt, "base_prediction": base_pred, "bars": bars}
