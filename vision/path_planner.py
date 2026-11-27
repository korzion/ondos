"""PathPlanner (C.5): distance map and route of the current maze, computed by the shared maze helper."""
from __future__ import annotations

from shared.mazes import MazeGrid, Route, build_distance_map, plan_route
from shared.mazes.route import ROUTE_INVALID
from vision.ball_state import BallState

NO_ROUTE = Route(ROUTE_INVALID, None, (), None)  # plan/route: invalid = no valid maze or ball not visible


class PathPlanner:
    """Keeps the distance map of the current maze and answers every ball sample with a route."""

    def __init__(self) -> None:
        self._maze: MazeGrid | None = None
        self._steps: list[list[int]] | None = None

    def build(self, maze: MazeGrid) -> list[list[int]] | None:
        """Distance map of a new maze, kept for route(); None when the maze is not valid."""
        self.invalidate()
        # ASSUMPTION: C.5 gives the result as int[rows][cols] and does not say what a maze that is not valid gives.
        # None is returned and the planner keeps no maze, so route() answers invalid instead of raising.
        try:
            steps = build_distance_map(maze)
        except ValueError:
            return None
        self._maze = maze
        self._steps = steps
        return steps

    def route(self, ball: BallState) -> Route:
        """Route for one ball sample; invalid without a valid maze or while the ball is not visible."""
        if self._maze is None or self._steps is None or not ball.is_visible:
            return NO_ROUTE
        # the filtered position, the same one vision/ball publishes; it is still used while the filter predicts
        return plan_route(self._maze, self._steps, ball.x_mm, ball.y_mm)

    def invalidate(self) -> None:
        """Forget the maze: after a changed or failed scan the old route must not be used."""
        self._maze = None
        self._steps = None
