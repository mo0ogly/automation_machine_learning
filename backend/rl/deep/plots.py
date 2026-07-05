"""
plots.py — captioned figures for a Deep RL run.

Two views an analyst reads to judge a run:
  - the learning curve (mean episode reward vs training timesteps): is the agent
    actually improving, and has it plateaued?
  - the evaluation reward distribution (one bar per evaluation episode, with the
    mean and the "solved" threshold overlaid): is the learned policy consistent,
    or does it succeed only sometimes?

Reuses the pipeline's plotting helpers so figures inherit the app style + the
{img, caption, topic} contract (zoom modal + per-graph AI button).
"""

import numpy as np

from pipeline.plotting import style_plot, fig_to_base64, message_plot


def learning_curve(result):
    import matplotlib.pyplot as plt
    style_plot()
    curve = result.get("curve") or []
    if len(curve) < 2:
        return message_plot("Trop peu de points pour tracer la courbe d'apprentissage "
                            "(augmentez les pas d'entraînement).")
    xs = [p[0] for p in curve]
    ys = [p[1] for p in curve]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(xs, ys, "-o", color="#0f3460", markeredgecolor="#e94560", ms=3, lw=1.6,
            label="Récompense moyenne (100 derniers épisodes)")
    threshold = result.get("threshold")
    if threshold is not None:
        ax.axhline(threshold, color="#16c79a", ls="--", lw=1.5, label="Seuil de réussite")
        ax.legend()
    ax.set_xlabel("Pas d'entraînement")
    ax.set_ylabel("Récompense par épisode")
    ax.set_title("Deep RL — courbe d'apprentissage")
    fig.tight_layout()
    return fig_to_base64(fig)


def eval_distribution(result, extras):
    import matplotlib.pyplot as plt
    style_plot()
    rewards = np.asarray(extras.get("eval_rewards") or [], dtype=float)
    if rewards.size == 0:
        return message_plot("Aucune récompense d'évaluation à afficher.")
    mean_r = float(rewards.mean())
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(range(1, rewards.size + 1), rewards, color="#0f3460", edgecolor="#e94560")
    ax.axhline(mean_r, color="#e94560", lw=1.6, label=f"Moyenne = {mean_r:.1f}")
    random_ref = result.get("random_reward")
    if random_ref is not None:
        ax.axhline(random_ref, color="#f59e0b", ls=":", lw=1.5,
                   label=f"Politique aléatoire = {random_ref:.1f}")
    threshold = result.get("threshold")
    if threshold is not None:
        ax.axhline(threshold, color="#16c79a", ls="--", lw=1.5, label="Seuil de réussite")
    ax.set_xlabel("Épisode d'évaluation")
    ax.set_ylabel("Récompense cumulée")
    ax.set_title("Deep RL — récompense par épisode d'évaluation (politique gloutonne)")
    ax.legend()
    fig.tight_layout()
    return fig_to_base64(fig)


def all_plots(result, extras):
    return [learning_curve(result), eval_distribution(result, extras)]
