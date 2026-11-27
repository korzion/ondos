"""BallEstimate: the answer of the ball filter for one frame, with the filtered fields of vision/ball (IF-04)."""
from __future__ import annotations

from typing import NamedTuple


# ASSUMPTION: the design document has no type for the answer of the filter. A named tuple keeps the plain tuple
# (x_mm, y_mm, vx_mm_s, vy_mm_s, is_visible, is_predicted) agreed in #47 and gives its values their names.
class BallEstimate(NamedTuple):
    """Filtered ball position and velocity in the board frame, and whether the ball is visible or predicted."""

    x_mm: float
    y_mm: float
    vx_mm_s: float
    vy_mm_s: float
    is_visible: bool
    is_predicted: bool
