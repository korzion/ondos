"""Planning on a maze (IF-04): the distance map, computed by the same code for Vision and for training."""
from __future__ import annotations

from collections import deque

from shared.mazes.maze_grid import WALL_E, WALL_N, WALL_S, WALL_W, Cell, MazeGrid

UNREACHABLE_STEPS = -1  # plan/distance_map: no path from this cell to the exit

# (wall flag, row step, col step) to the neighbour on that side, in the order N, E, S, W
NEIGHBOUR_STEPS = ((WALL_N, 1, 0), (WALL_E, 0, 1), (WALL_S, -1, 0), (WALL_W, 0, -1))


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


def _open_neighbours(maze: MazeGrid, cell: Cell) -> list[Cell]:
    row, col = cell
    return [(row + row_step, col + col_step)
            for flag, row_step, col_step in NEIGHBOUR_STEPS
            if not maze.walls[row][col] & flag]
