import dataclasses
import json
from pathlib import Path

import pytest

from shared.mazes import MazeGrid, build_distance_map

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = ROOT / "shared/interfaces/examples/maze_file.json"
MESSAGES_PATH = ROOT / "shared/interfaces/examples/messages.json"
EXAMPLE_MESSAGES = json.loads(MESSAGES_PATH.read_text(encoding="utf-8"))["examples"]


def example_maze():
    return MazeGrid.load(str(EXAMPLE_PATH))


def example_message(topic):
    return next(e["msg"] for e in EXAMPLE_MESSAGES if e["topic"] == topic)


def open_room():
    # 3 x 3 cells without inner walls, exit in the front right cell (0, 2), start in the far left cell (2, 0)
    return dataclasses.replace(example_maze(), rows=3, cols=3, origin_x_mm=-60.0, origin_y_mm=-60.0,
                               walls=((12, 4, 6), (8, 0, 2), (9, 1, 3)), start_cell=(2, 0), exit_cell=(0, 2),
                               exit_x_mm=40.0, exit_y_mm=-40.0)


def maze_with_closed_cells():
    # the two cells of column 0 are closed on all four sides; the exit cell (0, 1) is open only to cell (1, 1)
    return dataclasses.replace(example_maze(), walls=((15, 14), (15, 11)))


def open_neighbour_steps(maze, steps, row, col):
    sides = ((1, 1, 0), (2, 0, 1), (4, -1, 0), (8, 0, -1))  # wall flag, row step, col step for N, E, S, W (IF-04)
    return [steps[row + row_step][col + col_step] for flag, row_step, col_step in sides
            if not maze.walls[row][col] & flag]


def test_distance_map_of_the_example_maze():
    assert build_distance_map(example_maze()) == [[3, 0], [2, 1]]


def test_distance_map_of_the_example_maze_is_the_example_message():
    assert build_distance_map(example_maze()) == example_message("plan/distance_map")["steps"]


def test_distance_map_of_an_open_room_counts_cells_along_rows_and_columns():
    assert build_distance_map(open_room()) == [[2, 1, 0], [3, 2, 1], [4, 3, 2]]


def test_cells_without_a_path_to_the_exit_are_unreachable():
    assert build_distance_map(maze_with_closed_cells()) == [[-1, 0], [-1, 1]]


@pytest.mark.parametrize("maze", [example_maze(), open_room()], ids=["example", "open room"])
def test_every_cell_is_one_step_more_than_its_smallest_open_neighbour(maze):
    steps = build_distance_map(maze)
    for row in range(maze.rows):
        for col in range(maze.cols):
            if (row, col) != maze.exit_cell:
                assert steps[row][col] == 1 + min(open_neighbour_steps(maze, steps, row, col))


def test_distance_map_of_a_maze_that_is_not_valid_is_refused():
    open_border = dataclasses.replace(example_maze(), walls=((10, 14), (9, 3)))
    with pytest.raises(ValueError):
        build_distance_map(open_border)
