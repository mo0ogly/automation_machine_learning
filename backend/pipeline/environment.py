"""
environment.py — runtime environment fingerprint for drift cause attribution.

Captures a small, deterministic snapshot of the software environment a model is
fit and served in (library versions, thread configuration, Python/platform).
Comparing the fingerprint captured at TRAINING time with the one at MONITORING
time lets the cause-attribution layer (monitoring.attribute_cause) separate an
*execution-environment change* — a different library version, a bad reload on
another node, a changed thread/BLAS config — from a genuine change in the data
or in the model's behaviour.

No hardware telemetry is required: this is entirely self-contained. A caller may
additionally attach free-form OPERATIONAL metadata (node, timestamp, and, if
available, temperature / throttling) to a monitored batch; that is surfaced
as-is and used only as a hint, never as ground truth.
"""

from __future__ import annotations

import platform

# Libraries whose version can move a fitted model's numeric output between the
# training environment and the serving one.
_LIBS = ("numpy", "pandas", "scipy", "sklearn", "joblib", "xgboost")


def _version(name: str):
    try:
        return str(getattr(__import__(name), "__version__", "?"))
    except Exception:
        return None


def _blas_threads():
    """Total worker threads across the BLAS/OpenMP pools, or None if unknown.

    A change here is a legitimate source of numerical jitter (non-associative
    float reductions) but is noisy, so it is captured for display only and does
    NOT count towards the ``changed`` verdict in :func:`compare_fingerprints`.
    """
    try:
        from threadpoolctl import threadpool_info
        return sum(int(i.get("num_threads") or 0) for i in threadpool_info()) or None
    except Exception:
        return None


def capture_fingerprint() -> dict:
    """Snapshot the current software environment. Cheap and deterministic."""
    libs = {name: v for name in _LIBS if (v := _version(name)) is not None}
    return {
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
        "libraries": libs,
        "blas_threads": _blas_threads(),
    }


def compare_fingerprints(baseline: dict, current: dict) -> dict:
    """Diff a training-time fingerprint against a monitoring-time one.

    Returns ``{available, changed, diffs}`` where ``diffs`` is a list of
    ``{field, from, to}``. Only Python version, platform and library versions
    count towards ``changed`` (thread count is intentionally excluded — see
    :func:`_blas_threads`).
    """
    if not baseline or not current:
        return {"available": False, "changed": False, "diffs": []}
    diffs = []
    for field in ("python", "platform"):
        b, c = baseline.get(field), current.get(field)
        if b and c and b != c:
            diffs.append({"field": field, "from": b, "to": c})
    bl, cl = baseline.get("libraries") or {}, current.get("libraries") or {}
    for name in sorted(set(bl) | set(cl)):
        b, c = bl.get(name), cl.get(name)
        if b and c and b != c:
            diffs.append({"field": name, "from": b, "to": c})
        elif (b is None) != (c is None):  # a library appeared or disappeared
            diffs.append({"field": name, "from": b or "absent", "to": c or "absent"})
    return {"available": True, "changed": bool(diffs), "diffs": diffs}
