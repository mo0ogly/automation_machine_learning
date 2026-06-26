"""
gridworld.py — a small deterministic GridWorld environment for the reinforcement
learning demo (Atelier Jour 2, troisième paradigme).

The agent starts top-left and must reach the bottom-right goal. Each step costs a
small penalty, the goal gives a reward, optional traps end the episode with a
negative reward, and obstacles block movement. States are flattened to integers
(``row * size + col``) so a tabular Q-table indexes them directly.

Pure standard library + the (row, col) tuples it is handed — no gym, no torch.
"""


class GridWorld:
    # Actions, in order: up, right, down, left.
    ACTIONS = [(-1, 0), (0, 1), (1, 0), (0, -1)]
    ACTION_NAMES = ["haut", "droite", "bas", "gauche"]
    # Arrow glyphs for the learned-policy plot (index-aligned with ACTIONS).
    ACTION_ARROWS = ["↑", "→", "↓", "←"]

    def __init__(self, size=5, obstacles=None, traps=None, start=None, goal=None, goals=None,
                 step_penalty=-1.0, goal_reward=10.0, trap_reward=-10.0):
        self.size = int(size)
        self.start = tuple(start) if start else (0, 0)
        # One or several goals: reaching ANY of them ends the episode with goal_reward.
        if goals:
            self.goals = {tuple(g) for g in goals}
        elif goal:
            self.goals = {tuple(goal)}
        else:
            self.goals = {(self.size - 1, self.size - 1)}
        self.obstacles = {tuple(o) for o in (obstacles or [])}
        self.traps = {tuple(t) for t in (traps or [])}
        self.step_penalty = float(step_penalty)
        self.goal_reward = float(goal_reward)
        self.trap_reward = float(trap_reward)
        self.n_states = self.size * self.size
        self.n_actions = len(self.ACTIONS)
        self.state = self.start

    def idx(self, cell):
        """Flatten a (row, col) cell to a state index."""
        return cell[0] * self.size + cell[1]

    def cell(self, index):
        """Inverse of :meth:`idx`."""
        return (index // self.size, index % self.size)

    def reset(self):
        self.state = self.start
        return self.idx(self.state)

    def step(self, action):
        """Apply an action. Returns (next_state_index, reward, done)."""
        dr, dc = self.ACTIONS[action]
        r, c = self.state
        nr, nc = r + dr, c + dc
        # Stay in place when stepping off the grid or into an obstacle.
        if not (0 <= nr < self.size and 0 <= nc < self.size) or (nr, nc) in self.obstacles:
            nr, nc = r, c
        self.state = (nr, nc)
        if self.state in self.goals:
            return self.idx(self.state), self.goal_reward, True
        if self.state in self.traps:
            return self.idx(self.state), self.trap_reward, True
        return self.idx(self.state), self.step_penalty, False

    def at_goal(self):
        return self.state in self.goals
