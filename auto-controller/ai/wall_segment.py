"""WallSegment: one wall of the maze for the physics of TrainEnv (walls on cell edges, IF-04)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WallSegment:
    """One wall on a cell edge, by the centre of the edge in the board frame."""

    is_along_x: bool  # True for a wall on an N or S edge
    centre_x_mm: float
    centre_y_mm: float
