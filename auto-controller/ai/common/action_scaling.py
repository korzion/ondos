"""The AI's action (D.5): the network outputs −1…1 per axis, scaled by max_tilt_deg into a target tilt in degrees.

The AI Controller uses it at runtime and the training environment wrapper uses it in training,
so both turn the network output into degrees the same way.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from gymnasium import spaces

ACTION_LIMIT = 1.0
ACTION_DIMENSIONS = 2         # target_tilt_x_deg, target_tilt_y_deg
PERCENT = 100.0
FULL_TILT_SCALE_PCT = 100.0   # training uses the full scale; tilt_scale_pct is a runtime setting (D.7)

# ASSUMPTION (#64): every model is trained with this action space; the AI Controller refuses another one.
ACTION_SPACE = spaces.Box(-ACTION_LIMIT, ACTION_LIMIT, (ACTION_DIMENSIONS,), np.float32)


def to_target_tilt_deg(action: Sequence[float], max_tilt_deg: float, tilt_scale_pct: float) -> tuple[float, float]:
    """Target tilt in degrees (target_tilt_x_deg, target_tilt_y_deg) for a normalized action.

    Runtime: act() → to_target_tilt_deg(action, max_tilt_deg, tilt_scale_pct) → OutputShaper.shape().
    Training: to_target_tilt_deg(action, max_tilt_deg, FULL_TILT_SCALE_PCT), since TrainEnv.step() takes degrees
    (IF-08). The result is not clamped: OutputShaper and the platform apply the final bounds."""
    # ASSUMPTION (#64): D.5 lists AIController as "compute a normalized action", but also says act() returns
    # target_tilt_*. act() returns −1…1 (its interface has no max_tilt_deg) and this function does the scaling.
    scale_deg = max_tilt_deg * tilt_scale_pct / PERCENT
    return float(action[0]) * scale_deg, float(action[1]) * scale_deg
