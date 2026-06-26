"""
plots.py — captioned figures for the reinforcement-learning demo.

Three views an expert reads to judge a Q-learning run:
  - the learning curve (reward per episode + moving average),
  - the learned policy (an arrow per cell) over the state-value map,
  - the value function V(s) = max_a Q(s, a) as a heatmap.

Reuses the pipeline's plotting helpers so figures inherit the app style + the
{img, caption, topic} contract (zoom modal + per-graph AI button).
"""

import numpy as np

from pipeline.plotting import style_plot, fig_to_base64


def reward_curve(result):
    import matplotlib.pyplot as plt
    style_plot()
    rewards = result["rewards"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(rewards, color="#0f3460", alpha=0.35, lw=1, label="Récompense / épisode")
    w = max(1, len(rewards) // 20)
    if len(rewards) >= w and w > 1:
        ma = np.convolve(rewards, np.ones(w) / w, mode="valid")
        ax.plot(range(w - 1, w - 1 + len(ma)), ma, color="#e94560", lw=2,
                label=f"Moyenne glissante ({w})")
    ax.set_xlabel("Épisode")
    ax.set_ylabel("Récompense cumulée")
    ax.set_title("Apprentissage par renforcement — récompense par épisode")
    ax.legend()
    fig.tight_layout()
    return fig_to_base64(fig)


def policy_grid(result, env):
    import matplotlib.pyplot as plt
    style_plot()
    n = env.size
    policy = result["policy"]
    value = np.asarray(result["value"]).reshape(n, n)
    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    im = ax.imshow(value, cmap="viridis", origin="upper")
    for r in range(n):
        for c in range(n):
            cell = (r, c)
            if cell in env.obstacles:
                ax.add_patch(plt.Rectangle((c - 0.5, r - 0.5), 1, 1, color="#333"))
            elif cell in env.goals:
                ax.text(c, r, "BUT", ha="center", va="center", color="#fff",
                        fontweight="bold", fontsize=9)
            elif cell == env.start:
                ax.text(c, r, "S", ha="center", va="center", color="#16c79a",
                        fontweight="bold", fontsize=12)
            elif cell in env.traps:
                ax.text(c, r, "X", ha="center", va="center", color="#e94560",
                        fontweight="bold", fontsize=12)
            else:
                a = int(policy[env.idx(cell)])
                ax.text(c, r, env.ACTION_ARROWS[a], ha="center", va="center",
                        color="#fff", fontsize=15)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_title("Politique apprise (action par état) + valeur")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="V(s)")
    fig.tight_layout()
    return fig_to_base64(fig)


def value_heatmap(result, env):
    import matplotlib.pyplot as plt
    style_plot()
    n = env.size
    value = np.asarray(result["value"]).reshape(n, n)
    fig, ax = plt.subplots(figsize=(5.6, 5))
    im = ax.imshow(value, cmap="magma", origin="upper")
    for r in range(n):
        for c in range(n):
            ax.text(c, r, f"{value[r, c]:.1f}", ha="center", va="center",
                    color="#fff", fontsize=8)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_title("Fonction valeur V(s) = max(a) Q(s, a)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return fig_to_base64(fig)


def all_plots(result, env):
    return [reward_curve(result), policy_grid(result, env), value_heatmap(result, env)]
