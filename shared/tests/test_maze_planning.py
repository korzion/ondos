import dataclasses
import json
from pathlib import Path

import pytest

from shared import topics as T
from shared.mazes import MazeGrid, Route, build_distance_map, plan_route
from shared.mazes.route import ROUTE_INVALID, ROUTE_NO_PATH, ROUTE_VALID

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


def route_at(maze, x_mm, y_mm):
    return plan_route(maze, build_distance_map(maze), x_mm, y_mm)


def test_route_from_the_start_of_the_example_maze():
    route = route_at(example_maze(), -20.0, -20.0)
    assert route == Route(status=ROUTE_VALID, ball_cell=(0, 0),
                          target_points_mm=((-20.0, 20.0), (20.0, 20.0), (20.0, -20.0)), distance_to_exit_cells=3)


def test_route_from_the_start_of_the_example_maze_is_the_example_message():
    route = route_at(example_maze(), -20.0, -20.0)
    message = example_message("plan/route")
    assert route.status == message["status"]
    assert {"row": route.ball_cell[0], "col": route.ball_cell[1]} == message["ball_cell"]
    assert [list(point) for point in route.target_points_mm] == message["target_points_mm"]
    assert route.distance_to_exit_cells == message["distance_to_exit_cells"]


@pytest.mark.parametrize("exit_cell,exit_mm,ball_mm,first_point_mm,why", [
    ((2, 2), (40.0, 40.0), (-40.0, -40.0), (-40.0, 0.0), "from (0, 0) N and E are both 3 steps away: N wins"),
    ((0, 2), (40.0, -40.0), (0.0, 0.0), (40.0, 0.0), "from (1, 1) E and S are both 1 step away: E wins"),
    ((0, 0), (-40.0, -40.0), (0.0, 0.0), (0.0, -40.0), "from (1, 1) S and W are both 1 step away: S wins"),
])
def test_equal_distances_are_decided_in_the_order_n_e_s_w(exit_cell, exit_mm, ball_mm, first_point_mm, why):
    room = dataclasses.replace(open_room(), exit_cell=exit_cell, exit_x_mm=exit_mm[0], exit_y_mm=exit_mm[1])
    assert route_at(room, *ball_mm).target_points_mm[0] == first_point_mm, why


def test_route_has_at_most_three_points():
    # from (2, 0) the exit is 4 steps away; E wins the tie twice, then the only shorter way is S
    route = route_at(open_room(), -40.0, 40.0)
    assert route.target_points_mm == ((0.0, 40.0), (40.0, 40.0), (40.0, 0.0))
    assert route.distance_to_exit_cells == 4


def test_route_next_to_the_exit_ends_at_the_centre_of_the_exit_cell():
    off_centre_marker = dataclasses.replace(example_maze(), exit_x_mm=25.0, exit_y_mm=-15.0)
    route = route_at(off_centre_marker, 20.0, 20.0)
    assert route == Route(ROUTE_VALID, (1, 1), ((20.0, -20.0),), 1)


def test_route_in_the_exit_cell_is_the_exit_marker():
    off_centre_marker = dataclasses.replace(example_maze(), exit_x_mm=25.0, exit_y_mm=-15.0)
    route = route_at(off_centre_marker, 10.0, -30.0)
    assert route == Route(ROUTE_VALID, (0, 1), ((25.0, -15.0),), 0)


def test_ball_in_a_cell_without_a_path_gives_no_path():
    assert route_at(maze_with_closed_cells(), -20.0, -20.0) == Route(ROUTE_NO_PATH, (0, 0), (), None)


def test_ball_outside_the_grid_gives_invalid():
    assert route_at(example_maze(), -50.0, 0.0) == Route(ROUTE_INVALID, None, (), None)


def test_route_status_values_are_the_ones_of_the_interface():
    assert {ROUTE_VALID, ROUTE_NO_PATH, ROUTE_INVALID} == set(T.ROUTE_STATUS_VALUES)
