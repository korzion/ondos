"""PID Controller of D · Auto Controller (design document D.5, D.7).

Per axis: error = first route point - ball position, and
    tilt = Kp·error + Ki·∫error·dt − Kd·ball velocity, clamped to ±max_tilt_deg.
The integral term is limited to ±pid_integral_limit_deg and is not increased
while the output is saturated (anti-windup).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from bounds import clamp_symmetric
from shared import topics as T

PID_CONFIG_KEY = "pid"
KP_NAME = "pid_kp_deg_per_mm"
KI_NAME = "pid_ki_deg_per_mm_per_s"
KD_NAME = "pid_kd_deg_per_mm_s"
INTEGRAL_LIMIT_NAME = "pid_integral_limit_deg"

AXIS_X = 0
AXIS_Y = 1
AXIS_COUNT = 2

# Without a previous ball sample there is no time step, so the integral is not advanced.
NO_INTEGRATION_STEP_S = 0.0
# A time step longer than the largest allowed input age means samples were missed;
# integrating over the whole gap would add a large, unearned integral jump.
MAX_INTEGRATION_STEP_S = T.CONTROLLER_INPUT_MAX_AGE_MS / 1000.0


class PIDController:
    """Position-error PID with velocity damping and anti-windup, one instance per game."""

    def __init__(self, settings: Mapping[str, float], max_tilt_deg: float) -> None:
        self.settings = settings
        self.max_tilt_deg = max_tilt_deg
        self._integral_term_deg = [0.0] * AXIS_COUNT

    @property
    def settings(self) -> dict[str, float]:
        return dict(self._settings)

    @settings.setter
    def settings(self, settings: Mapping[str, float]) -> None:
        """Replace the gains (live change from cs/variables/pid); the integral is kept."""
        expected_names = set(T.VARIABLES[PID_CONFIG_KEY])
        missing_names = expected_names - set(settings)
        if missing_names:
            raise ValueError(f"missing PID settings: {sorted(missing_names)}")
        self._settings = {name: float(settings[name]) for name in expected_names}

    def compute(self, ball: Mapping[str, float], target: Sequence[float],
                dt_s: float | None) -> tuple[float, float]:
        """Return (target_tilt_x_deg, target_tilt_y_deg) for one ball sample.

        ball: a vision/ball payload (x_mm, y_mm, vx_mm_s, vy_mm_s are used).
        target: target_points_mm[0] of the matching plan/route, [x_mm, y_mm].
        dt_s: time since the previous vision/ball sample; None for the first sample.
        """
        step_s = self._integration_step_s(dt_s)
        tilt_x_deg = self._compute_axis(AXIS_X, target[AXIS_X] - ball["x_mm"], ball["vx_mm_s"], step_s)
        tilt_y_deg = self._compute_axis(AXIS_Y, target[AXIS_Y] - ball["y_mm"], ball["vy_mm_s"], step_s)
        return tilt_x_deg, tilt_y_deg

    def reset(self) -> None:
        """Clear the integral (new game, pause, mode change, new maze_id, fault, invalid input)."""
        self._integral_term_deg = [0.0] * AXIS_COUNT

    def _integration_step_s(self, dt_s: float | None) -> float:
        if dt_s is None or dt_s <= 0:
            return NO_INTEGRATION_STEP_S
        return min(dt_s, MAX_INTEGRATION_STEP_S)

    def _compute_axis(self, axis: int, error_mm: float, velocity_mm_s: float, step_s: float) -> float:
        proportional_deg = self._settings[KP_NAME] * error_mm
        damping_deg = -self._settings[KD_NAME] * velocity_mm_s
        held_integral_deg = self._integral_term_deg[axis]
        candidate_integral_deg = clamp_symmetric(
            held_integral_deg + self._settings[KI_NAME] * error_mm * step_s,
            self._settings[INTEGRAL_LIMIT_NAME])

        unclamped_tilt_deg = proportional_deg + candidate_integral_deg + damping_deg
        integral_change_deg = candidate_integral_deg - held_integral_deg
        if not self._is_winding_up(unclamped_tilt_deg, integral_change_deg):
            self._integral_term_deg[axis] = candidate_integral_deg

        tilt_deg = proportional_deg + self._integral_term_deg[axis] + damping_deg
        return clamp_symmetric(tilt_deg, self.max_tilt_deg)

    def _is_winding_up(self, unclamped_tilt_deg: float, integral_change_deg: float) -> bool:
        """True when the output is saturated and the integral step pushes further into saturation."""
        is_saturated = abs(unclamped_tilt_deg) > self.max_tilt_deg
        return is_saturated and integral_change_deg * unclamped_tilt_deg > 0
