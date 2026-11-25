"""Route (C.5): the answer of the route function for one ball position, with the fields of plan/route (IF-04)."""
from __future__ import annotations

from dataclasses import dataclass

from shared.mazes.maze_grid import Cell

ROUTE_VALID = "valid"
ROUTE_NO_PATH = "no_path"
ROUTE_INVALID = "invalid"


@dataclass(frozen=True)
class Route:
    """Route from the ball cell towards the exit; maze_id and ball_seq are added by the publisher of plan/route."""

    status: str
    ball_cell: Cell | None
    target_points_mm: tuple[tuple[float, float], ...]  # (x_mm, y_mm) of each point, empty unless status is valid
    distance_to_exit_cells: int | None
