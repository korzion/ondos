"""Output Shaper of D · Auto Controller (design document D.5, D.7).

Applies the output bounds (±max_tilt_deg) and, when configured, smoothing
(action_smoothing_pct) to a (target_tilt_x_deg, target_tilt_y_deg) action.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from bounds import clamp_symmetric

MAX_TILT_NAME = "max_tilt_deg"            # platform/variables_spec
SMOOTHING_NAME = "action_smoothing_pct"   # ai/variables_spec; D.7: AI output only
NO_SMOOTHING_PCT = 0.0
PERCENT_FULL_SCALE = 100.0


class OutputShaper:
    """Bounds and optionally smooths consecutive actions of one controller."""

    def __init__(self) -> None:
        self._previous_tilt_deg: tuple[float, float] | None = None

    def shape(self, action: Sequence[float], limits: Mapping[str, float]) -> tuple[float, float]:
        """Return the bounded (and smoothed) action.

        limits: max_tilt_deg is required; action_smoothing_pct is optional and
        left out for the PID Controller, which is never smoothed (D.7).
        Smoothing: new = previous·s + action·(1 − s), s = action_smoothing_pct / 100.
        """
        if not all(math.isfinite(value) for value in action):
            raise ValueError(f"non-finite action {tuple(action)}")
        smoothing_fraction = limits.get(SMOOTHING_NAME, NO_SMOOTHING_PCT) / PERCENT_FULL_SCALE
        smoothed = self._smooth(action, smoothing_fraction)
        max_tilt_deg = limits[MAX_TILT_NAME]
        bounded = (clamp_symmetric(smoothed[0], max_tilt_deg), clamp_symmetric(smoothed[1], max_tilt_deg))
        self._previous_tilt_deg = bounded
        return bounded

    def reset(self) -> None:
        """Forget the previous action, so the next one is not smoothed towards it."""
        self._previous_tilt_deg = None

    def _smooth(self, action: Sequence[float], smoothing_fraction: float) -> tuple[float, float]:
        if self._previous_tilt_deg is None:
            return action[0], action[1]
        previous_x_deg, previous_y_deg = self._previous_tilt_deg
        new_fraction = 1.0 - smoothing_fraction
        return (previous_x_deg * smoothing_fraction + action[0] * new_fraction,
                previous_y_deg * smoothing_fraction + action[1] * new_fraction)
