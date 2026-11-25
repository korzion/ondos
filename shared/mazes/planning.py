"""Planning on a maze (IF-04): the distance map and the route, computed by the same code for Vision and for training."""
from __future__ import annotations

from collections import deque

from shared.mazes.maze_grid import NEIGHBOUR_STEPS, Cell, MazeGrid
from shared.mazes.route import ROUTE_INVALID, ROUTE_NO_PATH, ROUTE_VALID, Route

UNREACHABLE_STEPS = -1  # plan/distance_map: no path from this cell to the exit
MAX_ROUTE_POINTS = 3    # plan/route carries up to 3 points


def build_distance_map(maze: MazeGrid) -> list[list[int]]:
    """Steps from every cell to the exit along the maze, as steps[row][col]; UNREACHABLE_STEPS where no path exists."""
    # with an open outer border a neighbour index of -1 would wrap to the other side of the grid without an error
    if not maze.validate():
        raise ValueError(f"maze {maze.maze_id!r} is not valid")
    steps = [[UNREACHABLE_STEPS] * maze.cols for _ in range(maze.rows)]
    exit_row, exit_col = maze.exit_cell
    steps[exit_row][exit_col] = 0
    cells_to_visit = deque([maze.exit_cell])
    while cells_to_visit:
        row, col = cells_to_visit.popleft()
        for neighbour_row, neighbour_col in _open_neighbours(maze, (row, col)):
            if steps[neighbour_row][neighbour_col] != UNREACHABLE_STEPS:
                continue
            steps[neighbour_row][neighbour_col] = steps[row][col] + 1
            cells_to_visit.append((neighbour_row, neighbour_col))
    return steps


def plan_route(maze: MazeGrid, steps: list[list[int]], x_mm: float, y_mm: float) -> Route:
    """Route for a ball at a board-frame point; steps is the distance map of the same maze."""
    ball_cell = maze.cell_of(x_mm, y_mm)
    if ball_cell is None:
        return Route(ROUTE_INVALID, None, (), None)
    distance_cells = steps[ball_cell[0]][ball_cell[1]]
    if distance_cells == UNREACHABLE_STEPS:
        return Route(ROUTE_NO_PATH, ball_cell, (), None)
    return Route(ROUTE_VALID, ball_cell, _target_points_mm(maze, steps, ball_cell), distance_cells)


def _target_points_mm(maze: MazeGrid, steps: list[list[int]], ball_cell: Cell) -> tuple[tuple[float, float], ...]:
    if ball_cell == maze.exit_cell:
        return ((maze.exit_x_mm, maze.exit_y_mm),)  # in the exit cell the only point is the exit marker
    points_mm = []
    cell = ball_cell
    while cell != maze.exit_cell and len(points_mm) < MAX_ROUTE_POINTS:
        cell = _next_cell(maze, steps, cell)
        points_mm.append(maze.cell_centre_mm(*cell))
    return tuple(points_mm)


def _next_cell(maze: MazeGrid, steps: list[list[int]], cell: Cell) -> Cell:
    next_cell = None
    for neighbour in _open_neighbours(maze, cell):
        # strictly smaller only: with equal distances the earlier side in N, E, S, W keeps its place
        if next_cell is None or steps[neighbour[0]][neighbour[1]] < steps[next_cell[0]][next_cell[1]]:
            next_cell = neighbour
    return next_cell


def _open_neighbours(maze: MazeGrid, cell: Cell) -> list[Cell]:
    row, col = cell
    return [(row + row_step, col + col_step)
            for flag, row_step, col_step in NEIGHBOUR_STEPS
            if not maze.walls[row][col] & flag]
