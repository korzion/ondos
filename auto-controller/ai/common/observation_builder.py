"""ObservationBuilder (D.5): the one implementation of the AI's observation, used in training and at runtime.

The observation has the ball velocity, the measured plate tilt, the previous command and the
next route points relative to the ball (board frame, D4 units). There is no absolute position,
so the same model also works on a changed maze. The keys are the bus field names (IF-08).
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from gymnasium import spaces

from ai.common.observation_scales import ObservationScales

ROUTE_POINT_COUNT = 3  # the next 3 route points (D.5; plan/route sends up to 3)
POINT_DIMENSIONS = 2   # x_mm, y_mm
OBSERVATION_DTYPE = np.float32
SCALAR_SHAPE = (1,)

VELOCITY_KEYS = ("vx_mm_s", "vy_mm_s")                        # from vision/ball
TILT_KEYS = ("tilt_x_deg", "tilt_y_deg")                      # measured tilt, from platform/state
PREVIOUS_ACTION_KEYS = ("target_tilt_x_deg", "target_tilt_y_deg")  # the previous command
TARGET_POINTS_KEY = "target_points_mm"                        # route points relative to the ball
BALL_POSITION_KEYS = ("x_mm", "y_mm")                         # used for the relative points only


class ObservationBuilder:
    """Builds the AI's observation from the ball, the plate tilt, the previous command and the route points."""

    def __init__(self, scales: ObservationScales | None = None) -> None:
        self._scales = scales or ObservationScales()

    @property
    def scales(self) -> ObservationScales:
        return self._scales

    def build(self, ball: Mapping[str, float], tilt: Mapping[str, float], previous_action: Sequence[float],
              targets: Sequence[Sequence[float]]) -> dict[str, np.ndarray]:
        """The scaled observation.

        ball: vision/ball fields (x_mm, y_mm, vx_mm_s, vy_mm_s); tilt: platform/state fields (tilt_x_deg,
        tilt_y_deg); previous_action: the last target tilt in degrees (0, 0 after a reset);
        targets: plan/route target_points_mm (1 to 3 points). Raises ValueError on missing or non-finite values.
        """
        observation = {}
        for key in VELOCITY_KEYS:
            observation[key] = _scalar(_finite(ball[key], key) / self._scales.velocity_mm_s)
        for key in TILT_KEYS:
            observation[key] = _scalar(_finite(tilt[key], key) / self._scales.tilt_deg)
        for key, value in zip(PREVIOUS_ACTION_KEYS, previous_action, strict=True):
            observation[key] = _scalar(_finite(value, key) / self._scales.tilt_deg)
        observation[TARGET_POINTS_KEY] = self._relative_targets(ball, targets)
        return observation

    @staticmethod
    def observation_space() -> spaces.Dict:
        """The gymnasium space of build()'s output; TrainEnv and the trainers use the same space (IF-08)."""
        scalar = spaces.Box(-np.inf, np.inf, SCALAR_SHAPE, OBSERVATION_DTYPE)
        scalar_keys = VELOCITY_KEYS + TILT_KEYS + PREVIOUS_ACTION_KEYS
        entries = {key: scalar for key in scalar_keys}
        entries[TARGET_POINTS_KEY] = spaces.Box(-np.inf, np.inf, (ROUTE_POINT_COUNT, POINT_DIMENSIONS),
                                                OBSERVATION_DTYPE)
        return spaces.Dict(entries)

    def _relative_targets(self, ball: Mapping[str, float], targets: Sequence[Sequence[float]]) -> np.ndarray:
        if not targets:
            raise ValueError("the route has no target points")
        ball_position_mm = np.array([_finite(ball[key], key) for key in BALL_POSITION_KEYS])
        points_mm = np.array(_padded(targets), dtype=np.float64)
        if points_mm.shape != (ROUTE_POINT_COUNT, POINT_DIMENSIONS) or not np.all(np.isfinite(points_mm)):
            raise ValueError(f"target points must be finite [x_mm, y_mm] pairs, got {list(targets)}")
        offsets = (points_mm - ball_position_mm) / self._scales.target_offset_mm
        return offsets.astype(OBSERVATION_DTYPE)


def _padded(targets: Sequence[Sequence[float]]) -> list[Sequence[float]]:
    """The first ROUTE_POINT_COUNT points; a shorter route repeats its last point (near the exit)."""
    points = list(targets[:ROUTE_POINT_COUNT])
    return points + [points[-1]] * (ROUTE_POINT_COUNT - len(points))


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _scalar(value: float) -> np.ndarray:
    return np.array([value], dtype=OBSERVATION_DTYPE)
