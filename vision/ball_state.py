"""BallState (C.5): one ball sample, as BallTracker gives it to the other parts of Vision."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BallState:
    """Filtered ball position and speed in the board frame, with the unfiltered measurement of the frame."""

    x_mm: float
    y_mm: float
    vx_mm_s: float
    vy_mm_s: float
    is_visible: bool
    is_predicted: bool
    meas_x_mm: float | None  # None when the ball was not detected in this frame
    meas_y_mm: float | None
