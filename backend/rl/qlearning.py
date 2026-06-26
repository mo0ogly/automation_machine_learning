"""
qlearning.py — tabular Q-learning for the GridWorld demo.

Q-learning is the canonical value-based reinforcement-learning algorithm
(Watkins & Dayan, 1992): the agent learns Q(s, a) — the expected return of taking
action ``a`` in state ``s`` — by bootstrapping from its own estimates:

    Q(s, a) <- Q(s, a) + alpha * (r + gamma * max_a' Q(s', a') - Q(s, a))

Exploration uses an epsilon-greedy policy with decay. NumPy only.
"""

import numpy as np


def train_qlearning(env, episodes=300, alpha=0.1, gamma=0.95, epsilon=1.0,
                    epsilon_min=0.05, epsilon_decay=0.99, max_steps=200, seed=0):
    """Train a tabular Q-learning agent on ``env`` (a GridWorld).

    Returns a dict with the learned Q-table, greedy policy, state values, and the
    per-episode learning curves (reward, steps, success).
    """
    rng = np.random.default_rng(int(seed))
    Q = np.zeros((env.n_states, env.n_actions), dtype=float)
    rewards, steps_hist, successes = [], [], []
    eps = float(epsilon)

    for _ in range(int(episodes)):
        s = env.reset()
        total, steps, done = 0.0, 0, False
        while not done and steps < max_steps:
            if rng.random() < eps:
                a = int(rng.integers(env.n_actions))      # explore
            else:
                a = int(np.argmax(Q[s]))                  # exploit
            ns, r, done = env.step(a)
            Q[s, a] += alpha * (r + gamma * np.max(Q[ns]) - Q[s, a])
            s = ns
            total += r
            steps += 1
        rewards.append(float(total))
        steps_hist.append(int(steps))
        successes.append(1 if env.at_goal() else 0)
        eps = max(float(epsilon_min), eps * float(epsilon_decay))

    return {
        "Q": Q,
        "policy": np.argmax(Q, axis=1),
        "value": np.max(Q, axis=1),
        "rewards": rewards,
        "steps": steps_hist,
        "successes": successes,
        "episodes": int(episodes),
    }


def summarise(result, env, tail=20):
    """Headline metrics an expert reads to judge whether the agent learned."""
    rewards = result["rewards"]
    steps = result["steps"]
    successes = result["successes"]
    tail = min(int(tail), len(rewards)) or 1
    first = sum(rewards[:tail]) / tail
    last = sum(rewards[-tail:]) / tail
    return {
        "Récompense initiale (moy.)": round(first, 2),
        "Récompense finale (moy.)": round(last, 2),
        "Gain d'apprentissage": round(last - first, 2),
        "Taux de réussite final": f"{round(100.0 * sum(successes[-tail:]) / tail, 1)}%",
        "Pas moyens (fin)": round(sum(steps[-tail:]) / tail, 1),
        "Chemin optimal (Manhattan)": int(min(abs(g[0] - env.start[0]) + abs(g[1] - env.start[1])
                                              for g in env.goals)),
    }
