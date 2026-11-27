"""SimulatedVision: the ball as Vision reports it in vision/ball, for TrainEnv (IF-08).

Each camera frame the true ball position gets noise (noise_std_mm), or it is not measured at all
during a short occlusion near a wall. The measurement then goes through Vision's own filter
(shared/ball_filter, C.5 BallTracker), so x_mm, y_mm, vx_mm_s, vy_mm_s, is_visible and is_predicted
behave as at runtime (IF-08: "the same low-pass filter as Vision"). As agreed in #47, the noise is
added before the filter and an occlusion only drops measurements; the filter decides is_predicted
and is_visible.
"""
from __future__ import annotations

import math

import numpy as np

from ai.plate_world import AXES, MS_PER_S
from ai.train_env_config import TrainEnvConfig
from ai.wall_segment import WallSegment
from shared.ball_filter import BallEstimate, BallFilter
from shared.mazes import MazeGrid

NOT_HIDDEN_S = -math.inf  # hidden-until time when no occlusion is running


class SimulatedVision:
    """Noisy, sometimes missing ball measurements and Vision's filter on them."""

    def __init__(self, config: TrainEnvConfig) -> None:
        if not 0.0 < config.occlusion_min_ms <= config.occlusion_max_ms:
            raise ValueError("occlusion_min_ms must be > 0 and not above occlusion_max_ms")
        self._config = config
        self._filter = BallFilter(config.filter_noise, config.lost_timeout_ms)
        self._rng = np.random.default_rng()
        self._noise_std_mm = 0.0
        self._wall_centres_mm = np.zeros((0, AXES))
        self._wall_is_along_x = np.zeros(0, dtype=bool)
        self._half_wall_length_mm = 0.0
        self._occlusion_distance_mm = 0.0
        self._hidden_until_s = NOT_HIDDEN_S
        self.measured_mm: np.ndarray | None = None  # measured centre of this frame; None when not detected

    def reset(self, maze: MazeGrid, walls: list[WallSegment], noise_std_mm: float,
              rng: np.random.Generator) -> None:
        """New episode: forget the ball; rng comes from reset(seed), so a seed repeats the episode."""
        self._filter.reset()
        self._rng = rng
        self._noise_std_mm = noise_std_mm
        self._wall_centres_mm = np.array([[wall.centre_x_mm, wall.centre_y_mm] for wall in walls]).reshape(-1, AXES)
        self._wall_is_along_x = np.array([wall.is_along_x for wall in walls], dtype=bool)
        self._half_wall_length_mm = maze.cell_size_mm / 2.0  # a wall covers one cell edge (IF-04)
        # Ball centre to wall centre line when the gap between the ball and the wall face is occlusion_wall_gap_mm.
        self._occlusion_distance_mm = (maze.ball_diameter_mm / 2.0 + maze.wall_thickness_mm / 2.0
                                       + self._config.occlusion_wall_gap_mm)
        self._hidden_until_s = NOT_HIDDEN_S
        self.measured_mm = None

    def see(self, true_position_mm: np.ndarray, t_s: float, frame_dt_s: float) -> BallEstimate:
        """One camera frame taken at t_s, frame_dt_s after the previous one. The first frame of an episode
        (frame_dt_s = 0) cannot start an occlusion, so the ball is always seen at the start."""
        if self._is_hidden(true_position_mm, t_s, frame_dt_s):
            self.measured_mm = None
            return self._filter.update(None, None, t_s)
        noise_mm = self._rng.normal(0.0, self._noise_std_mm, size=AXES)
        self.measured_mm = np.asarray(true_position_mm, dtype=float) + noise_mm
        meas_x_mm, meas_y_mm = self.measured_mm
        return self._filter.update(float(meas_x_mm), float(meas_y_mm), t_s)

    def _is_hidden(self, true_position_mm: np.ndarray, t_s: float, frame_dt_s: float) -> bool:
        """True during an occlusion; a new one may start in this frame."""
        if t_s < self._hidden_until_s:
            return True
        return self._starts_occlusion(true_position_mm, t_s, frame_dt_s)

    def _starts_occlusion(self, true_position_mm: np.ndarray, t_s: float, frame_dt_s: float) -> bool:
        # ASSUMPTION: IF-08 says only "randomly false for short occlusions near walls". An occlusion starts at
        # occlusion_rate_per_s while the ball is near a wall and lasts a uniform time between occlusion_min_ms
        # and occlusion_max_ms, so a short one is bridged (is_predicted) and a long one loses the ball.
        start_chance = self._config.occlusion_rate_per_s * frame_dt_s
        if not self._is_near_wall(true_position_mm) or self._rng.random() >= start_chance:
            return False
        duration_ms = self._rng.uniform(self._config.occlusion_min_ms, self._config.occlusion_max_ms)
        self._hidden_until_s = t_s + duration_ms / MS_PER_S
        return True

    def _is_near_wall(self, position_mm: np.ndarray) -> bool:
        """Ball centre within occlusion distance of any wall's centre line."""
        if len(self._wall_centres_mm) == 0:
            return False
        offset_x_mm = position_mm[0] - self._wall_centres_mm[:, 0]
        offset_y_mm = position_mm[1] - self._wall_centres_mm[:, 1]
        along_mm = np.where(self._wall_is_along_x, offset_x_mm, offset_y_mm)
        across_mm = np.where(self._wall_is_along_x, offset_y_mm, offset_x_mm)
        beyond_end_mm = np.maximum(np.abs(along_mm) - self._half_wall_length_mm, 0.0)
        return bool(np.min(np.hypot(beyond_end_mm, across_mm)) <= self._occlusion_distance_mm)
