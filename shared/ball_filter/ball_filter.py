"""BallFilter: the ball filter of Vision (C.5 BallTracker), also used by the training environment (IF-08)."""
from __future__ import annotations

from shared.ball_filter.axis_kalman import PROCESS_NOISE_MM2_PER_S3, AxisKalman
from shared.ball_filter.ball_estimate import BallEstimate

MS_PER_S = 1000.0

# ASSUMPTION: vision/ball gives the last known position for a lost ball, but nothing for a ball that was never seen.
# The board centre is given, with is_visible = false.
NEVER_SEEN = BallEstimate(0.0, 0.0, 0.0, 0.0, False, False)


class BallFilter:
    """Filters the measured ball positions of both axes and decides is_visible and is_predicted."""

    def __init__(self, filter_noise: float, lost_timeout_ms: float) -> None:
        self.filter_noise = filter_noise
        self.lost_timeout_ms = lost_timeout_ms
        self._axis_x = AxisKalman()
        self._axis_y = AxisKalman()
        self._is_tracking = False
        self._last_update_s = 0.0
        self._last_detection_s = 0.0
        self._lost_estimate = NEVER_SEEN

    def update(self, meas_x_mm: float | None, meas_y_mm: float | None, t_s: float) -> BallEstimate:
        """Estimate for the frame taken at t_s; the measurement is None when the ball was not detected."""
        if meas_x_mm is None or meas_y_mm is None:
            estimate = self._bridge_or_lose(t_s)
        else:
            estimate = self._track(meas_x_mm, meas_y_mm, t_s)
        self._last_update_s = t_s
        return estimate

    def _track(self, meas_x_mm: float, meas_y_mm: float, t_s: float) -> BallEstimate:
        if self._track_continues(t_s):
            self._predict(t_s - self._last_update_s)
            self._axis_x.correct(meas_x_mm)
            self._axis_y.correct(meas_y_mm)
        else:
            self._axis_x.start(meas_x_mm)
            self._axis_y.start(meas_y_mm)
            self._is_tracking = True
        self._last_detection_s = t_s
        estimate = self._estimate(is_predicted=False)
        # ASSUMPTION: the "last known position" of a lost ball (vision/ball) is the estimate of the last frame with
        # a detection, not the position predicted since then: a prediction of 200 ms can be several cells away.
        self._lost_estimate = BallEstimate(estimate.x_mm, estimate.y_mm, 0.0, 0.0, False, False)
        return estimate

    def _bridge_or_lose(self, t_s: float) -> BallEstimate:
        if self._track_continues(t_s):
            self._predict(t_s - self._last_update_s)
            return self._estimate(is_predicted=True)
        self._is_tracking = False  # only a new detection brings a lost ball back, also if the timeout is raised
        return self._lost_estimate

    def _track_continues(self, t_s: float) -> bool:
        if not self._is_tracking:
            return False
        # ASSUMPTION: a timestamp before the previous one (a restarted clock or recording) ends the track, because
        # the age of the last detection is not known then.
        if t_s < self._last_update_s:
            return False
        return t_s - self._last_detection_s < self.lost_timeout_ms / MS_PER_S

    def _predict(self, dt_s: float) -> None:
        # filter_noise scales the process noise: more of it trusts the measurements more (faster, less smooth)
        process_noise_mm2_per_s3 = self.filter_noise * PROCESS_NOISE_MM2_PER_S3
        self._axis_x.predict(dt_s, process_noise_mm2_per_s3)
        self._axis_y.predict(dt_s, process_noise_mm2_per_s3)

    def _estimate(self, is_predicted: bool) -> BallEstimate:
        return BallEstimate(self._axis_x.position_mm, self._axis_y.position_mm,
                            self._axis_x.velocity_mm_s, self._axis_y.velocity_mm_s, True, is_predicted)
