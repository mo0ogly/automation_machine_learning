"""Reinforcement-learning demo subsystem (separate from the 8-stage pipeline).

GridWorld environment + tabular Q-learning + captioned plots, exposed through the
``/api/rl/train`` route. The third learning paradigm (after supervised and
unsupervised).
"""

from .gridworld import GridWorld
from .qlearning import train_qlearning, summarise
from . import plots

__all__ = ["GridWorld", "train_qlearning", "summarise", "plots"]
