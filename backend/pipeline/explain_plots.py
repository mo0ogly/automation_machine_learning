"""
explain_plots.py — partial dependence (PDP) figures for the Explicability stage.

SHAP answers "which features drove THIS set of predictions and by how much".
Partial dependence answers a complementary question: "as feature X varies, how
does the model's AVERAGE prediction move?" — the shape of the learned effect
(monotone? threshold? non-linear?). The 2-D variant plots a pair of features
together, surfacing the **interaction** an additive view would miss (which is why
it pairs naturally with the interaction features the Transform stage now builds).

Kept out of explain.py (SHAP) to respect the file-size budget. Each helper
returns a captioned base64 figure for the UI's per-graph AI explainer, or None.
Built on ``sklearn.inspection.partial_dependence`` (model-agnostic).
"""

import numpy as np

from .plotting import style_plot, fig_to_base64


def _grid(pd_result):
    """sklearn renamed 'values' -> 'grid_values' across versions; support both."""
    g = pd_result.get("grid_values", pd_result.get("values"))
    return g


def _class_row(avg, class_row):
    """Pick the output row for the class of interest. ``average`` has one row per
    output — n_classes for multiclass proba, 1 for binary / regression. Clamps."""
    n = len(avg)
    r = int(class_row) if class_row is not None else 0
    return avg[r] if 0 <= r < n else avg[0]


def pdp_1d(model, X, feature, feature_name, problem_type, class_row=0):
    """Average prediction as one feature varies (partial-dependence curve)."""
    import matplotlib.pyplot as plt
    from sklearn.inspection import partial_dependence
    style_plot()
    try:
        res = partial_dependence(model, X, [feature], kind="average", grid_resolution=40)
    except Exception:
        return None
    xs = np.asarray(_grid(res)[0], dtype=float)
    ys = np.asarray(_class_row(res["average"], class_row), dtype=float)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, color="#e94560", lw=2)
    ax.fill_between(xs, ys.min(), ys, color="#e94560", alpha=0.08)
    ylabel = "Probabilité moyenne" if problem_type == "classification" else "Prédiction moyenne"
    ax.set_xlabel(str(feature_name))
    ax.set_ylabel(ylabel)
    ax.set_title("Dépendance partielle — " + str(feature_name))
    fig.tight_layout()
    return fig_to_base64(fig)


def pdp_2d(model, X, pair, names, problem_type, class_row=0):
    """2-D partial-dependence surface for a feature pair — reveals interaction."""
    import matplotlib.pyplot as plt
    from sklearn.inspection import partial_dependence
    style_plot()
    try:
        res = partial_dependence(model, X, [tuple(pair)], kind="average", grid_resolution=20)
    except Exception:
        return None
    grids = _grid(res)
    gx, gy = np.asarray(grids[0], dtype=float), np.asarray(grids[1], dtype=float)
    z = np.asarray(_class_row(res["average"], class_row), dtype=float)   # (len(gx), len(gy))
    fig, ax = plt.subplots(figsize=(6, 4.6))
    cf = ax.contourf(gx, gy, z.T, levels=14, cmap="plasma")
    fig.colorbar(cf, ax=ax, shrink=0.85,
                 label=("Proba moyenne" if problem_type == "classification" else "Prédiction moyenne"))
    ax.set_xlabel(str(names[0]))
    ax.set_ylabel(str(names[1]))
    ax.set_title("Dépendance partielle 2D — " + str(names[0]) + " × " + str(names[1]))
    fig.tight_layout()
    return fig_to_base64(fig)


def partial_dependence_plots(model, X, feature_names, top_indices, problem_type, class_row=0):
    """1-D PDP for the top features + a 2-D PDP for the top pair. ``top_indices``
    are column positions into ``X`` (most influential first); ``class_row`` selects
    the class in multiclass (0 for binary / regression)."""
    plots = []
    for i in top_indices[:3]:
        p = pdp_1d(model, X, int(i), feature_names[i], problem_type, class_row)
        if p:
            plots.append(p)
    if len(top_indices) >= 2:
        p2 = pdp_2d(model, X, (int(top_indices[0]), int(top_indices[1])),
                    (feature_names[top_indices[0]], feature_names[top_indices[1]]),
                    problem_type, class_row)
        if p2:
            plots.append(p2)
    return plots
