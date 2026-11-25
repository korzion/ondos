"""Rule checks on the ready data files in data/ (issue #87, design document section 3 "rule checks").

TEST PLAN
These tests read the committed files only. They import neither fixture_publisher nor make_fixture, so a
mistake in the generator cannot hide itself. Every expected value is computed here from the files.

1. Files          every line is a valid fixture line and a valid message of its topic; only the topics of the
                  bridge, Vision and the Auto Controller; never game/state or game/warning.
2. Maze           border closed, neighbouring walls agree; both mazes have the same size and exit.
3. Distance map   exit = 0, every other cell = 1 + its smallest open neighbour (-1 = unreachable).
4. Routes         every valid route starts next to the ball cell, stays on open cells and gets one step closer
                  at each point; the stated distance is the distance map's value; maze ids match the stream.
5. Ball           moves as its velocity says, stays inside the maze, ends on the exit and stands still there.
   Demo steps    the ball waits in the start cell (Start is accepted only there) and stops long enough before
                  the exit for the not_moving warning; edit_state has no game_id.
6. Rates          samples per loop: ball, route, control tilt 30 Hz; platform, glove 50 Hz; AI status 10 Hz;
                  Vision status and edit_state 1 Hz; every stream ends inside one loop.
7. Behaviour      every file named in behaviour.json exists; the e_stop override only sets fields of platform/state;
                  variables_spec values are inside their limits.
"""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(ROOT))  # repo root, for `import shared`

from shared import topics as T  # noqa: E402
from shared.interfaces import validate  # noqa: E402

NORTH, EAST, SOUTH, WEST = 1, 2, 4, 8
SIDES = ((NORTH, 1, 0, SOUTH), (EAST, 0, 1, WEST), (SOUTH, -1, 0, NORTH), (WEST, 0, -1, EAST))
ENVELOPE = {"timestamp_s": 0.0, "seq": 0, "version": 1}
EXPECTED_RATE_HZ = {T.VISION_BALL: 30, T.PLAN_ROUTE: 30, T.CONTROL_TARGET_TILT: 30, T.PLATFORM_STATE: 50, T.GLOVE_STATE: 50,
                    T.AI_STATUS: 10, T.VISION_STATUS: 1, T.VISION_EDIT_STATE: 1}
STREAM_FILES = ("samples.jsonl", "route_start.jsonl", "route_changed.jsonl", "controller_start.jsonl",
                "controller_changed.jsonl", "edit_start.jsonl", "edit_changed.jsonl", "edit_hand.jsonl", "edit_rescanning.jsonl")
ONE_SHOT_FILES = ("start.jsonl", "maze_changed.jsonl", "hand.jsonl", "read_maze.jsonl")
TOPICS_JSON = ROOT / "shared" / "interfaces" / "topics.json"
POSITION_TOLERANCE_MM = 0.01
START_WINDOW_MIN_S = 3.0  # time to press Start while the ball is in the start cell
NOT_MOVING_TIME_S, NOT_MOVING_RADIUS_MM = 3.0, 5.0  # start values of E.7
WARNING_MARGIN_S = 0.5  # E-R10: warnings within 0.5 s of their thresholds


def read_lines(name: str) -> list[dict]:
    return [json.loads(text) for text in (DATA / name).read_text(encoding="utf-8").splitlines() if text.strip()]


def of_topic(lines: list[dict], topic: str) -> list[dict]:
    return [line["msg"] for line in lines if line["topic"] == topic]


def behaviour() -> dict:
    return json.loads((DATA / "behaviour.json").read_text(encoding="utf-8"))


def maze_and_steps(name: str) -> tuple[dict, list[list[int]]]:
    lines = read_lines(name)
    return of_topic(lines, T.VISION_MAZE)[0], of_topic(lines, T.PLAN_DISTANCE_MAP)[0]["steps"]


def open_neighbours(maze: dict, row: int, col: int) -> list[tuple[int, int]]:
    return [(row + d_row, col + d_col) for flag, d_row, d_col, _ in SIDES if not maze["walls"][row][col] & flag]


def cell_centre(maze: dict, row: int, col: int) -> tuple[float, float]:
    size = maze["cell_size_mm"]
    return maze["origin_x_mm"] + (col + 0.5) * size, maze["origin_y_mm"] + (row + 0.5) * size


MAZE_FILES = {"start": "start.jsonl", "changed": "maze_changed.jsonl"}


# ---------------------------------------------------------------- 1 files
@pytest.mark.parametrize("name", [*STREAM_FILES, *ONE_SHOT_FILES])
def test_every_line_is_a_valid_message_of_a_stand_in_program(name):
    topics = {entry["name"]: entry for entry in json.loads(TOPICS_JSON.read_text(encoding="utf-8"))["topics"]}
    stand_in = {entry["writer"] for entry in topics.values() if entry["interface"] in ("IF-02", "IF-04", "IF-06")}
    lines = read_lines(name)
    assert lines, f"{name} is empty"
    assert [line["t_s"] for line in lines] == sorted(line["t_s"] for line in lines)
    for line in lines:
        assert set(line) == {"t_s", "topic", "msg"}
        assert topics[line["topic"]]["writer"] in stand_in
        assert line["topic"] not in (T.GAME_STATE, T.GAME_WARNING)
        validate(line["topic"], {**ENVELOPE, "writer": topics[line["topic"]]["writer"], **line["msg"]})


# ---------------------------------------------------------------- 2 maze
@pytest.mark.parametrize("name", MAZE_FILES.values())
def test_maze_border_is_closed_and_neighbours_agree(name):
    maze, _ = maze_and_steps(name)
    for row in range(maze["rows"]):
        for col in range(maze["cols"]):
            for flag, d_row, d_col, opposite in SIDES:
                n_row, n_col = row + d_row, col + d_col
                has_wall = bool(maze["walls"][row][col] & flag)
                if 0 <= n_row < maze["rows"] and 0 <= n_col < maze["cols"]:
                    assert has_wall == bool(maze["walls"][n_row][n_col] & opposite), (row, col, flag)
                else:
                    assert has_wall, f"open border at ({row},{col})"


def test_both_mazes_have_the_same_size_and_exit():
    start, _ = maze_and_steps("start.jsonl")
    changed, _ = maze_and_steps("maze_changed.jsonl")
    assert (start["rows"], start["cols"], start["exit_cell"]) == (changed["rows"], changed["cols"], changed["exit_cell"])
    assert start["maze_id"] != changed["maze_id"]


# ---------------------------------------------------------------- 3 distance map
@pytest.mark.parametrize("name", MAZE_FILES.values())
def test_distance_map_is_one_more_than_the_smallest_open_neighbour(name):
    maze, steps = maze_and_steps(name)
    exit_cell = (maze["exit_cell"]["row"], maze["exit_cell"]["col"])
    for row in range(maze["rows"]):
        for col in range(maze["cols"]):
            if (row, col) == exit_cell:
                assert steps[row][col] == 0
                continue
            reachable = [steps[r][c] for r, c in open_neighbours(maze, row, col) if steps[r][c] >= 0]
            assert steps[row][col] == (1 + min(reachable) if reachable else -1), (row, col)


# ---------------------------------------------------------------- 4 routes
@pytest.mark.parametrize("route_file, maze_file", [("route_start.jsonl", "start.jsonl"), ("route_changed.jsonl", "maze_changed.jsonl")])
def test_routes_stay_on_open_cells_towards_the_exit(route_file, maze_file):
    maze, steps = maze_and_steps(maze_file)
    routes = of_topic(read_lines(route_file), T.PLAN_ROUTE)
    assert any(route["status"] == "valid" and route["target_points_mm"] for route in routes)
    for route in routes:
        assert route["maze_id"] == maze["maze_id"]
        if route["status"] != "valid":
            assert route["target_points_mm"] == []
            continue
        row, col = route["ball_cell"]["row"], route["ball_cell"]["col"]
        assert route["distance_to_exit_cells"] == steps[row][col]
        for x_mm, y_mm in route["target_points_mm"]:
            next_cells = open_neighbours(maze, row, col)
            matching = [cell for cell in next_cells if math.dist(cell_centre(maze, *cell), (x_mm, y_mm)) < POSITION_TOLERANCE_MM]
            assert matching, f"route point ({x_mm},{y_mm}) is not an open neighbour of ({row},{col})"
            assert steps[matching[0][0]][matching[0][1]] == steps[row][col] - 1
            row, col = matching[0]


@pytest.mark.parametrize("name, maze_file", [("controller_start.jsonl", "start.jsonl"), ("controller_changed.jsonl", "maze_changed.jsonl"),
                                             ("edit_start.jsonl", "start.jsonl"), ("edit_changed.jsonl", "maze_changed.jsonl")])
def test_streams_carry_the_id_of_their_maze(name, maze_file):
    maze, _ = maze_and_steps(maze_file)
    ids = [msg.get("maze_id") or msg.get("maze_match") for msg in (line["msg"] for line in read_lines(name))]
    carrying_an_id = [maze_id for maze_id in ids if maze_id is not None]  # ai/status has no maze id
    assert carrying_an_id and set(carrying_an_id) == {maze["maze_id"]}


# ---------------------------------------------------------------- 5 ball
def test_ball_moves_as_its_velocity_says_and_ends_on_the_exit():
    maze, _ = maze_and_steps("start.jsonl")
    balls = of_topic(read_lines("samples.jsonl"), T.VISION_BALL)
    dt_s = 1 / EXPECTED_RATE_HZ[T.VISION_BALL]
    for before, after in zip(balls, balls[1:]):
        assert after["x_mm"] - before["x_mm"] == pytest.approx(before["vx_mm_s"] * dt_s, abs=POSITION_TOLERANCE_MM)
        assert after["y_mm"] - before["y_mm"] == pytest.approx(before["vy_mm_s"] * dt_s, abs=POSITION_TOLERANCE_MM)
    half = maze["cols"] * maze["cell_size_mm"] / 2
    assert all(abs(b["x_mm"]) <= half and abs(b["y_mm"]) <= maze["rows"] * maze["cell_size_mm"] / 2 for b in balls)
    last = balls[-1]
    assert last["is_on_exit"] and last["vx_mm_s"] == 0 == last["vy_mm_s"]
    assert not balls[0]["is_on_exit"]


def inside_cell(maze: dict, cell: dict, ball: dict) -> bool:
    centre_x, centre_y = cell_centre(maze, cell["row"], cell["col"])
    half = maze["cell_size_mm"] / 2
    return abs(ball["x_mm"] - centre_x) <= half and abs(ball["y_mm"] - centre_y) <= half


def test_ball_waits_in_the_start_cell_long_enough_to_press_start():
    """GameManager accepts Start only while the ball is in the start cell (section 5)."""
    maze, _ = maze_and_steps("start.jsonl")
    balls = of_topic(read_lines("samples.jsonl"), T.VISION_BALL)
    samples_in_start = next(i for i, ball in enumerate(balls) if not inside_cell(maze, maze["start_cell"], ball))
    assert samples_in_start / EXPECTED_RATE_HZ[T.VISION_BALL] >= START_WINDOW_MIN_S


def still_runs(balls: list[dict]) -> list[tuple[int, int]]:
    """Index ranges in which the ball stays inside NOT_MOVING_RADIUS_MM of the first sample of the range."""
    runs, first = [], 0
    for i in range(1, len(balls)):
        if math.dist((balls[i]["x_mm"], balls[i]["y_mm"]), (balls[first]["x_mm"], balls[first]["y_mm"])) > NOT_MOVING_RADIUS_MM:
            runs.append((first, i - 1))
            first = i
    return runs + [(first, len(balls) - 1)]


def test_ball_stands_still_long_enough_for_not_moving_before_the_exit():
    """E.7 start values: not_moving_time_s and not_moving_radius_mm; E-R10 allows 0.5 s margin."""
    maze, _ = maze_and_steps("start.jsonl")
    balls = of_topic(read_lines("samples.jsonl"), T.VISION_BALL)
    needed_s = NOT_MOVING_TIME_S + WARNING_MARGIN_S
    stops = [(first, last) for first, last in still_runs(balls)
             if not inside_cell(maze, maze["start_cell"], balls[first])
             and not any(ball["is_on_exit"] for ball in balls[first:last + 1])
             and (last - first + 1) / EXPECTED_RATE_HZ[T.VISION_BALL] >= needed_s]
    assert stops, f"no stop of {needed_s} s outside the start cell and before the exit"


def test_edit_state_has_no_game_id():
    """The publisher does not know which game runs, so the field is null."""
    for name in (*STREAM_FILES, *ONE_SHOT_FILES):
        for msg in of_topic(read_lines(name), T.VISION_EDIT_STATE):
            assert msg["game_id"] is None, name


@pytest.mark.parametrize("name", MAZE_FILES.values())
def test_maze_message_carries_the_sizes_of_the_platform_input(name):
    sizes = json.loads((HERE / "inputs" / "platform.json").read_text(encoding="utf-8"))
    maze, _ = maze_and_steps(name)
    for field in ("cell_size_mm", "wall_thickness_mm", "wall_height_mm", "ball_diameter_mm", "exit_radius_mm"):
        assert maze[field] == sizes[field], field


def test_the_ball_fits_through_a_cell_and_the_exit_marker_fits_in_it():
    maze, _ = maze_and_steps("start.jsonl")
    free_width_mm = maze["cell_size_mm"] - maze["wall_thickness_mm"]
    assert maze["ball_diameter_mm"] < free_width_mm
    assert maze["exit_radius_mm"] <= maze["cell_size_mm"] / 2


def test_the_ball_only_crosses_open_edges():
    maze, _ = maze_and_steps("start.jsonl")
    size = maze["cell_size_mm"]

    def cell_of(ball: dict) -> tuple[int, int]:
        return (math.floor((ball["y_mm"] - maze["origin_y_mm"]) / size), math.floor((ball["x_mm"] - maze["origin_x_mm"]) / size))

    balls = of_topic(read_lines("samples.jsonl"), T.VISION_BALL)
    for before, after in zip(balls, balls[1:]):
        if cell_of(before) != cell_of(after):
            assert cell_of(after) in open_neighbours(maze, *cell_of(before)), (cell_of(before), cell_of(after))


def test_tilt_stays_inside_the_limit_of_the_platform_input():
    limit = json.loads((HERE / "inputs" / "platform.json").read_text(encoding="utf-8"))["tilt_limit_deg"]
    for platform in of_topic(read_lines("samples.jsonl"), T.PLATFORM_STATE):
        assert abs(platform["tilt_x_deg"]) <= limit and abs(platform["tilt_y_deg"]) <= limit


# ---------------------------------------------------------------- 6 rates
def stream_topic_counts() -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for name in STREAM_FILES:
        for line in read_lines(name):
            counts.setdefault(name, {}).setdefault(line["topic"], 0)
            counts[name][line["topic"]] += 1
    return counts


def test_samples_per_loop_match_the_rates():
    loop_s = behaviour()["loop_s"]
    counts = stream_topic_counts()
    found = {}
    for per_file in counts.values():
        for topic, count in per_file.items():
            found.setdefault(topic, set()).add(count)
    for topic, rate_hz in EXPECTED_RATE_HZ.items():
        assert found[topic] == {int(loop_s * rate_hz)}, f"{topic}: {found[topic]}, wanted {int(loop_s * rate_hz)} per loop"


def test_every_stream_ends_inside_one_loop():
    loop_s = behaviour()["loop_s"]
    for name in STREAM_FILES:
        times = [line["t_s"] for line in read_lines(name)]
        assert 0 <= times[0] and times[-1] < loop_s, name


# ---------------------------------------------------------------- 7 behaviour
def action_lists(data: dict) -> list[list[dict]]:
    found = [data["start"], *data["commands"].values(), *(t["do"] for t in data["triggers"].values())]
    for actions in list(found):
        found += [action["do"] for action in actions if "after_s" in action]
    return found


def test_every_file_in_behaviour_exists_and_is_listed_here():
    named = set()
    for actions in action_lists(behaviour()):
        for action in actions:
            named |= {action["play"]} if "play" in action else set(action.get("streams", []))
    assert named
    assert {name for name in named if not (DATA / name).exists()} == set()
    assert named <= {*STREAM_FILES, *ONE_SHOT_FILES}


def test_e_stop_override_only_sets_fields_of_platform_state():
    override = behaviour()["commands"]["e_stop"][0]["override"]
    assert set(override) == {T.PLATFORM_STATE}
    platform = of_topic(read_lines("samples.jsonl"), T.PLATFORM_STATE)[0]
    assert set(override[T.PLATFORM_STATE]) <= set(platform)
    assert override[T.PLATFORM_STATE]["is_e_stop"] is True


def test_pid_has_every_variable_of_the_design():
    """D.7 lists four PID variables."""
    specs = json.loads((DATA / "variables_spec.json").read_text(encoding="utf-8"))
    assert {variable["name"] for variable in specs["pid"]} == set(T.VARIABLES["pid"])


def test_variables_are_inside_their_limits_and_known():
    specs = json.loads((DATA / "variables_spec.json").read_text(encoding="utf-8"))
    for key, variables in specs.items():
        for variable in variables:
            assert variable["name"] in T.VARIABLES[key]
            if variable["choices"] is not None:
                assert variable["value"] in variable["choices"]
            elif not isinstance(variable["value"], bool):
                assert variable["min"] <= variable["value"] <= variable["max"]
