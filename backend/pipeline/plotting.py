"""
plotting.py — Shared matplotlib primitives.

Every chart in the app uses the same dark theme (coherent with the React UI)
and is returned to the frontend as an inline base64 PNG data-URI.
"""

import io
import base64
import threading

import matplotlib
matplotlib.use("Agg")  # headless backend — must be set before pyplot import
import matplotlib.pyplot as plt

# matplotlib's pyplot keeps GLOBAL state (figure registry, rcParams, current style).
# FastAPI runs sync routes in a threadpool and the dev client can fire overlapping
# requests (React StrictMode), so two diagnose/run calls could build figures at the
# same time and corrupt that state → blank / missing plots. Serialise all figure
# generation behind this lock (held by the stage diagnose/run, see app.py).
PLOT_LOCK = threading.RLock()

# Palette aligned with the frontend CSS variables.
BG = "#1a1a2e"
PANEL = "#16213e"
ACCENT = "#e94560"
ACCENT_2 = "#0f3460"
TEXT = "#eee"
MUTED = "#aaa"


def style_plot():
    """Apply the dark theme used throughout the UI."""
    plt.style.use("dark_background")
    plt.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor": PANEL,
        "axes.edgecolor": ACCENT,
        "text.color": TEXT,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.labelcolor": TEXT,
        "axes.titlecolor": TEXT,
        "figure.figsize": (7, 4.5),
        "font.size": 9,
    })


def _fig_caption(fig) -> str:
    """Best-effort human caption for a figure (its suptitle, else first axes title)."""
    st = getattr(fig, "_suptitle", None)
    if st is not None and st.get_text():
        return st.get_text()
    for ax in fig.axes:
        t = ax.get_title()
        if t:
            return t
    return ""


def fig_to_base64(fig, topic: str = None) -> dict:
    """Serialise a matplotlib figure to a captioned base64 PNG and close it.

    Returns ``{"img": data_uri, "caption": ..., "topic": ...}``. The higher DPI
    keeps figures crisp when opened enlarged in the detail modal; the caption
    (auto-extracted from the figure title) labels each plot and lets the UI offer
    a per-graph AI explainer.
    """
    caption = _fig_caption(fig)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=160, facecolor=BG)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return {"img": f"data:image/png;base64,{img_b64}", "caption": caption, "topic": topic or caption}


def message_plot(message: str) -> str:
    """A small placeholder chart carrying a textual message (e.g. 'no numeric columns')."""
    style_plot()
    fig, ax = plt.subplots(figsize=(6, 2))
    ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, fontsize=11, wrap=True)
    ax.axis("off")
    return fig_to_base64(fig)
