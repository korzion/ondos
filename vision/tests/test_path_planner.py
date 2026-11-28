import dataclasses
from pathlib import Path

from shared.mazes import MazeGrid, Route
from shared.mazes.route import ROUTE_INVALID, ROUTE_VALID
from vision.ball_state import BallState
from vision.path_planner import PathPlanner

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = ROOT / "shared/interfaces/examples/maze_file.json"
START_MM = (-20.0, -20.0)  # centre of the start cell (0, 0) of the example maze
NO_ROUTE = Route(ROUTE_INVALID, None, (), None)


def example_maze() -> MazeGrid:
    return MazeGrid.load(str(EXAMPLE_PATH))


def ball_at(x_mm: float, y_mm: float, is_visible: bool = True, is_predicted: bool = False) -> BallState:
    """A ball at rest at a board-frame point; a predicted or lost ball has no measurement in this frame."""
    is_measured = is_visible and not is_predicted
    return BallState(x_mm=x_mm, y_mm=y_mm, vx_mm_s=0.0, vy_mm_s=0.0, is_visible=is_visible,
                     is_predicted=is_predicted, meas_x_mm=x_mm if is_measured else None,
                     meas_y_mm=y_mm if is_measured else None)


def planner_with_example_maze() -> PathPlanner:
    planner = PathPlanner()
    planner.build(example_maze())
    return planner


def test_build_gives_the_distance_map_of_the_maze():
    assert PathPlanner().build(example_maze()) == [[3, 0], [2, 1]]


def test_route_for_a_visible_ball():
    route = planner_with_example_maze().route(ball_at(*START_MM))
    assert route == Route(ROUTE_VALID, (0, 0), ((-20.0, 20.0), (20.0, 20.0), (20.0, -20.0)), 3)


def test_route_continues_while_the_filter_predicts_the_ball():
    route = planner_with_example_maze().route(ball_at(*START_MM, is_predicted=True))
    assert route.status == ROUTE_VALID


def test_route_is_invalid_while_the_ball_is_not_visible():
    assert planner_with_example_maze().route(ball_at(*START_MM, is_visible=False)) == NO_ROUTE


def test_route_is_invalid_before_a_maze_is_built():
    assert PathPlanner().route(ball_at(*START_MM)) == NO_ROUTE


def test_route_is_invalid_after_invalidate():
    planner = planner_with_example_maze()
    planner.invalidate()
    assert planner.route(ball_at(*START_MM)) == NO_ROUTE


def test_a_maze_that_is_not_valid_gives_no_map_and_replaces_the_old_maze():
    planner = planner_with_example_maze()
    open_border = dataclasses.replace(example_maze(), walls=((10, 14), (9, 3)))
    assert planner.build(open_border) is None
    assert planner.route(ball_at(*START_MM)) == NO_ROUTE


def test_maze_id_is_the_id_of_the_built_maze():
    assert planner_with_example_maze().maze_id == "example-2x2"


def test_maze_id_is_none_before_a_maze_is_built():
    assert PathPlanner().maze_id is None


def test_maze_id_is_none_after_invalidate():
    planner = planner_with_example_maze()
    planner.invalidate()
    assert planner.maze_id is None


def test_maze_id_is_none_after_a_maze_that_is_not_valid():
    planner = planner_with_example_maze()
    planner.build(dataclasses.replace(example_maze(), walls=((10, 14), (9, 3))))
    assert planner.maze_id is None
