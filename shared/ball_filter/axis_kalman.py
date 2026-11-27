"""AxisKalman: the Kalman filter of one board axis of the ball, with the states position and velocity."""
from __future__ import annotations

# STARTING VALUES, to be tuned with the real camera.
MEASUREMENT_NOISE_STD_MM = 1.0     # noise of one measured ball position (IF-08: Vision estimate)
INITIAL_VELOCITY_STD_MM_S = 300.0  # a started axis is at rest, but the ball may already move this fast
PROCESS_NOISE_MM2_PER_S3 = 10_000.0  # how fast the velocity may change unseen: about (600 mm/s^2)^2 x one frame


class AxisKalman:
    """Filters the measured positions of one axis and estimates the velocity from them."""

    def __init__(self) -> None:
        self.position_mm = 0.0
        self.velocity_mm_s = 0.0
        self._position_variance = 0.0
        self._cross_covariance = 0.0
        self._velocity_variance = 0.0

    def start(self, position_mm: float) -> None:
        """Begin a new track at a measured position, at rest."""
        self.position_mm = position_mm
        self.velocity_mm_s = 0.0
        self._position_variance = MEASUREMENT_NOISE_STD_MM ** 2
        self._cross_covariance = 0.0
        self._velocity_variance = INITIAL_VELOCITY_STD_MM_S ** 2

    def predict(self, dt_s: float, process_noise_mm2_per_s3: float) -> None:
        """Move the state dt_s ahead at constant velocity; the uncertainty grows with the process noise."""
        self.position_mm += self.velocity_mm_s * dt_s
        # constant velocity with white-noise acceleration: Q = q * [[dt^3 / 3, dt^2 / 2], [dt^2 / 2, dt]]
        self._position_variance += (2.0 * dt_s * self._cross_covariance + dt_s ** 2 * self._velocity_variance
                                    + process_noise_mm2_per_s3 * dt_s ** 3 / 3.0)
        self._cross_covariance += dt_s * self._velocity_variance + process_noise_mm2_per_s3 * dt_s ** 2 / 2.0
        self._velocity_variance += process_noise_mm2_per_s3 * dt_s

    def correct(self, measured_mm: float) -> None:
        """Pull the state towards a measured position, by as much as the state is uncertain."""
        innovation_variance = self._position_variance + MEASUREMENT_NOISE_STD_MM ** 2
        position_gain = self._position_variance / innovation_variance
        velocity_gain = self._cross_covariance / innovation_variance
        innovation_mm = measured_mm - self.position_mm
        self.position_mm += position_gain * innovation_mm
        self.velocity_mm_s += velocity_gain * innovation_mm
        self._velocity_variance -= velocity_gain * self._cross_covariance
        self._cross_covariance -= position_gain * self._cross_covariance
        self._position_variance -= position_gain * self._position_variance
