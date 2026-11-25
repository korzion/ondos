"""Preparation tool for the fixture publisher (issue #87). The publisher and the tests never import this file.

    python control-station/fixtures/fixture_publisher/make_fixture.py

Reads the simple input files in inputs/ and writes the ready data files in data/ that fixture_publisher.py plays:
  inputs/maze.txt, maze_after_change.txt   text grid: # wall, . open, S start, E exit (top line = north, +y)
  inputs/ball_path.json                    cells the ball walks through, seconds per cell, hold at the end
  inputs/platform.json                     a few numbers: cell size, tilt limit and gain, rescan time, battery
All geometry (distance map, route, tilt) is computed here, so the publisher has no maze or controller logic.
The output is checked before it is written; data/variables_spec.json is edited by hand and left alone.
"""
import json
import math
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))  # repo root, for `import shared`

from shared import topics as T  # noqa: E402
from shared.interfaces import ValidationError, validate  # noqa: E402

INPUT_DIR, DATA_DIR = HERE / "inputs", HERE / "data"
MAZE_FILES = ("maze.txt", "maze_after_change.txt")
MAZE_IDS = ("demo", "demo-changed")
BALL_HZ, PLATFORM_HZ, AI_STATUS_HZ, EDIT_STATE_HZ, VISION_STATUS_HZ = 30, 50, 10, 1, 1
NORTH, EAST, SOUTH, WEST = 1, 2, 4, 8
SIDES = ((NORTH, 1, 0), (EAST, 0, 1), (SOUTH, -1, 0), (WEST, 0, -1))  # flag, row step, col step
UNREACHABLE = -1
ROUTE_POINTS_MAX = 3
DECIMALS = 3
HAND_STATE, RESCAN_STATE, CLEAR_STATE = "hand_present", "rescanning", "clear"
ENVELOPE = {"timestamp_s": 0.0, "seq": 0, "version": 1}


class FixtureError(Exception):
    """An input file is wrong; the message says which one and why."""


# ---------------------------------------------------------------------- maze
def parse_maze(text: str, maze_id: str, platform: dict, name: str) -> dict:
    """The vision/maze fields (without source) of a text grid with a wall or open mark between and around cells."""
    cell_size_mm = platform["cell_size_mm"]
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) % 2 == 0 or any(len(line) != len(lines[0]) for line in lines) or len(lines[0]) % 2 == 0:
        raise FixtureError(f"{name}: needs an odd number of lines of one odd length (2 x cells + 1)")
    rows, cols = len(lines) // 2, len(lines[0]) // 2
    grid = lines[::-1]  # grid[0] = south line, so row r sits at grid[2r+1]
    _check_frame(grid, rows, cols, name)
    cells = {(r, c): grid[2 * r + 1][2 * c + 1] for r in range(rows) for c in range(cols)}
    start, exit_ = _single(cells, "S", name), _single(cells, "E", name)
    walls = [[_wall_flags(grid, r, c) for c in range(cols)] for r in range(rows)]
    exit_cell = {"row": exit_[0], "col": exit_[1]}
    origin_x_mm, origin_y_mm = -cols * cell_size_mm / 2, -rows * cell_size_mm / 2
    maze = {"maze_id": maze_id, "cell_size_mm": cell_size_mm, "rows": rows, "cols": cols, "origin_x_mm": origin_x_mm,
            "origin_y_mm": origin_y_mm, "walls": walls, "wall_thickness_mm": platform["wall_thickness_mm"],
            "wall_height_mm": platform["wall_height_mm"], "start_cell": {"row": start[0], "col": start[1]}, "exit_cell": exit_cell}
    exit_x_mm, exit_y_mm = cell_centre_mm(maze, exit_cell)
    return {**maze, "exit_x_mm": exit_x_mm, "exit_y_mm": exit_y_mm, "exit_radius_mm": platform["exit_radius_mm"],
            "ball_diameter_mm": platform["ball_diameter_mm"]}


def _check_frame(grid: list[str], rows: int, cols: int, name: str) -> None:
    for pos_row in range(2 * rows + 1):
        for pos_col in range(2 * cols + 1):
            mark = grid[pos_row][pos_col]
            on_border = pos_row in (0, 2 * rows) or pos_col in (0, 2 * cols)
            is_corner = pos_row % 2 == 0 and pos_col % 2 == 0
            if (on_border or is_corner) and mark != "#":
                raise FixtureError(f"{name}: line {2 * rows - pos_row + 1}, column {pos_col + 1} must be # (border or corner)")
            if pos_row % 2 == 1 and pos_col % 2 == 1 and mark not in ".SE":
                raise FixtureError(f"{name}: a cell must be . S or E, got {mark!r}")
            if (pos_row + pos_col) % 2 == 1 and mark not in "#.":
                raise FixtureError(f"{name}: a wall mark must be # or ., got {mark!r}")


def _single(cells: dict, mark: str, name: str) -> tuple[int, int]:
    found = [cell for cell, char in cells.items() if char == mark]
    if len(found) != 1:
        raise FixtureError(f"{name}: needs exactly one {mark}, found {len(found)}")
    return found[0]


def _wall_flags(grid: list[str], row: int, col: int) -> int:
    pos_row, pos_col = 2 * row + 1, 2 * col + 1
    return sum(flag for flag, d_row, d_col in SIDES if grid[pos_row + d_row][pos_col + d_col] == "#")


def cell_centre_mm(maze: dict, cell: dict) -> tuple[float, float]:
    size = maze["cell_size_mm"]
    return (maze["origin_x_mm"] + (cell["col"] + 0.5) * size, maze["origin_y_mm"] + (cell["row"] + 0.5) * size)


def cell_at_mm(maze: dict, x_mm: float, y_mm: float) -> dict | None:
    size = maze["cell_size_mm"]
    row, col = math.floor((y_mm - maze["origin_y_mm"]) / size), math.floor((x_mm - maze["origin_x_mm"]) / size)
    return {"row": row, "col": col} if 0 <= row < maze["rows"] and 0 <= col < maze["cols"] else None


def open_neighbours(maze: dict, row: int, col: int) -> list[tuple[int, int]]:
    return [(row + d_row, col + d_col) for flag, d_row, d_col in SIDES if not maze["walls"][row][col] & flag]


def distance_steps(maze: dict) -> list[list[int]]:
    """Breadth-first search from the exit: cells to walk to the exit, -1 = unreachable."""
    steps = [[UNREACHABLE] * maze["cols"] for _ in range(maze["rows"])]
    exit_cell = maze["exit_cell"]
    steps[exit_cell["row"]][exit_cell["col"]] = 0
    queue = deque([(exit_cell["row"], exit_cell["col"])])
    while queue:
        row, col = queue.popleft()
        for n_row, n_col in open_neighbours(maze, row, col):
            if steps[n_row][n_col] == UNREACHABLE:
                steps[n_row][n_col] = steps[row][col] + 1
                queue.append((n_row, n_col))
    return steps


def route_cells(maze: dict, cell: dict, steps: list[list[int]]) -> list[tuple[int, int]]:
    """The next cells towards the exit (up to ROUTE_POINTS_MAX); empty at the exit or without a path."""
    row, col = cell["row"], cell["col"]
    cells = []
    while steps[row][col] > 0 and len(cells) < ROUTE_POINTS_MAX:
        row, col = next(n for n in open_neighbours(maze, row, col) if steps[n[0]][n[1]] == steps[row][col] - 1)
        cells.append((row, col))
    return cells


# ---------------------------------------------------------------------- ball and platform
class BallTrack:
    """The ball walks from cell centre to cell centre; the same cell twice in a row means it waits there."""

    def __init__(self, maze: dict, path: dict, platform: dict) -> None:
        self.waypoints = [cell_centre_mm(maze, {"row": r, "col": c}) for r, c in path["cells"]]
        self.seconds_per_cell = path["seconds_per_cell"]
        self.duration_s = (len(self.waypoints) - 1) * self.seconds_per_cell + path["end_hold_s"]
        self.gain, self.limit_deg = platform["tilt_gain_deg_per_mm"], platform["tilt_limit_deg"]

    def at(self, t_s: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
        """Position, velocity and tilt (deg) of the ball at t_s."""
        segment = int(t_s // self.seconds_per_cell)
        if segment >= len(self.waypoints) - 1:
            return self.waypoints[-1], (0.0, 0.0), (0.0, 0.0)
        start, end = self.waypoints[segment], self.waypoints[segment + 1]
        fraction = (t_s - segment * self.seconds_per_cell) / self.seconds_per_cell
        position = (start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction)
        velocity = ((end[0] - start[0]) / self.seconds_per_cell, (end[1] - start[1]) / self.seconds_per_cell)
        if velocity == (0.0, 0.0):
            return position, velocity, (0.0, 0.0)
        return position, velocity, (self._clamp(end[0] - position[0]), self._clamp(end[1] - position[1]))

    def _clamp(self, distance_mm: float) -> float:
        return max(-self.limit_deg, min(self.limit_deg, self.gain * distance_mm))


def sample_times(rate_hz: int, duration_s: float) -> list[float]:
    return [i / rate_hz for i in range(int(duration_s * rate_hz))]


def line(t_s: float, topic: str, msg: dict) -> dict:
    return {"t_s": round(t_s, DECIMALS), "topic": topic, "msg": _rounded(msg)}


def _rounded(value):
    if isinstance(value, float):
        return round(value, DECIMALS)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(item) for item in value]
    return value


def sorted_lines(lines: list[dict]) -> list[dict]:
    return sorted(lines, key=lambda item: item["t_s"])


def platform_samples(track: BallTrack, maze: dict, platform: dict) -> list[dict]:
    """Ball, platform and glove samples: the same for both mazes."""
    out = []
    for t_s in sample_times(BALL_HZ, track.duration_s):
        position, velocity, _ = track.at(t_s)
        on_exit = math.hypot(position[0] - maze["exit_x_mm"], position[1] - maze["exit_y_mm"]) <= maze["exit_radius_mm"]
        out.append(line(t_s, T.VISION_BALL, {
            "x_mm": position[0], "y_mm": position[1], "vx_mm_s": velocity[0], "vy_mm_s": velocity[1], "is_visible": True,
            "is_predicted": False, "is_on_exit": on_exit, "frame_age_ms": 22.0, "meas_x_mm": position[0], "meas_y_mm": position[1]}))
    for t_s in sample_times(PLATFORM_HZ, track.duration_s):
        tilt = track.at(t_s)[2]
        out.append(line(t_s, T.PLATFORM_STATE, {
            "tilt_x_deg": tilt[0], "tilt_y_deg": tilt[1], "applied_tilt_x_deg": tilt[0], "applied_tilt_y_deg": tilt[1],
            "source": "ai", "mode": "ai", "mode_button_presses": 0, "is_e_stop": False, "is_laptop_connected": True,
            "is_glove_connected": True, "fault": "none"}))
        out.append(line(t_s, T.GLOVE_STATE, {
            "hand_tilt_x_deg": tilt[0], "hand_tilt_y_deg": tilt[1], "ax_m_s2": 0.0, "ay_m_s2": 0.0, "az_m_s2": 9.8,
            "gx_deg_s": 0.0, "gy_deg_s": 0.0, "gz_deg_s": 0.0, "battery_pct": platform["battery_pct"], "rssi_dbm": -55,
            "is_calibrated": True, "is_connected": True, "firmware_version": 1}))
    return sorted_lines(out)


# ---------------------------------------------------------------------- per-maze streams
def route_message(maze: dict, steps: list[list[int]], position: tuple[float, float], ball_seq: int) -> dict:
    cell = cell_at_mm(maze, *position)
    message = {"maze_id": maze["maze_id"], "ball_seq": ball_seq, "status": "invalid", "ball_cell": cell,
               "target_points_mm": [], "distance_to_exit_cells": None}
    if cell is None:
        return message
    distance = steps[cell["row"]][cell["col"]]
    if distance == UNREACHABLE:
        return {**message, "status": "no_path"}
    points = [list(cell_centre_mm(maze, {"row": r, "col": c})) for r, c in route_cells(maze, cell, steps)]
    return {**message, "status": "valid", "distance_to_exit_cells": distance, "target_points_mm": points}


def route_stream(maze: dict, steps: list[list[int]], track: BallTrack) -> list[dict]:
    return [line(t_s, T.PLAN_ROUTE, route_message(maze, steps, track.at(t_s)[0], i))
            for i, t_s in enumerate(sample_times(BALL_HZ, track.duration_s))]


def controller_stream(maze: dict, steps: list[list[int]], track: BallTrack) -> list[dict]:
    """Control tilt, AI status and Vision status of one maze (they carry the maze id or the route)."""
    out = []
    for i, t_s in enumerate(sample_times(BALL_HZ, track.duration_s)):
        tilt = track.at(t_s)[2]
        out.append(line(t_s, T.CONTROL_TARGET_TILT, {"target_tilt_x_deg": tilt[0], "target_tilt_y_deg": tilt[1],
                                                      "ball_seq": i, "maze_id": maze["maze_id"]}))
    for t_s in sample_times(AI_STATUS_HZ, track.duration_s):
        points = route_message(maze, steps, track.at(t_s)[0], 0)["target_points_mm"]
        out.append(line(t_s, T.AI_STATUS, {"active_controller": "pid", "status": "active", "policy": "imitation",
                                           "model_version": "imitation-1", "target_points_mm": points}))
    for t_s in sample_times(VISION_STATUS_HZ, track.duration_s):
        out.append(line(t_s, T.VISION_STATUS, {"fps_hz": 30.0, "frame_age_ms": 21.0, "is_camera_ok": True, "is_calibrated": True,
                                               "markers_found": 4, "reprojection_error_mm": 0.8, "maze_match": maze["maze_id"],
                                               "cpu_pct": 35.0}))
    return sorted_lines(out)


def edit_state_message(state: str, reason: str | None, maze_id: str | None) -> dict:
    return {"state": state, "maze_id": maze_id, "game_id": None, "reason": reason}



def edit_stream(state: str, reason: str | None, maze_id: str | None, duration_s: float) -> list[dict]:
    return [line(t_s, T.VISION_EDIT_STATE, edit_state_message(state, reason, maze_id)) for t_s in sample_times(EDIT_STATE_HZ, duration_s)]


def clear_line(t_s: float, maze: dict) -> dict:
    """edit_state is published at once when it changes, not only at the next 1 Hz line."""
    return line(t_s, T.VISION_EDIT_STATE, edit_state_message(CLEAR_STATE, None, maze["maze_id"]))


def maze_lines(t_s: float, maze: dict, steps: list[list[int]], source: str) -> list[dict]:
    return [line(t_s, T.VISION_MAZE, {**maze, "source": source}),
            line(t_s, T.PLAN_DISTANCE_MAP, {"maze_id": maze["maze_id"], "rows": maze["rows"], "cols": maze["cols"], "steps": steps})]


# ---------------------------------------------------------------------- what the app can do
def behaviour(duration_s: float, rescan_s: float) -> dict:
    """Which file plays after which command or key; edited by hand if you want other behaviour."""
    start_streams = ["samples.jsonl", "route_start.jsonl", "controller_start.jsonl", "edit_start.jsonl"]
    changed_streams = ["samples.jsonl", "route_changed.jsonl", "controller_changed.jsonl", "edit_changed.jsonl"]
    rescan_streams = ["samples.jsonl", "route_start.jsonl", "controller_start.jsonl", "edit_rescanning.jsonl"]
    hand_streams = ["samples.jsonl", "controller_start.jsonl", "edit_hand.jsonl"]
    stopped_platform = {"tilt_x_deg": 0.0, "tilt_y_deg": 0.0, "applied_tilt_x_deg": 0.0, "applied_tilt_y_deg": 0.0}
    return {
        "loop_s": round(duration_s, DECIMALS),
        "start": [{"play": "start.jsonl"}, {"streams": start_streams}],
        "commands": {
            "e_stop": [{"override": {T.PLATFORM_STATE: {**stopped_platform, "is_e_stop": True}}}],
            "clear_e_stop": [{"clear_override": [T.PLATFORM_STATE]}],
            "read_maze": [{"play": "read_maze.jsonl"}, {"streams": rescan_streams},
                          {"after_s": rescan_s, "do": [{"streams": start_streams}]}],
        },
        "triggers": {
            "h": {"description": "A hand enters the playfield: hand_present, the route stops",
                  "do": [{"play": "hand.jsonl"}, {"streams": hand_streams}]},
            "c": {"description": "The hand leaves: new maze, distance map and route",
                  "do": [{"play": "maze_changed.jsonl"}, {"streams": changed_streams}]},
        },
    }


# ---------------------------------------------------------------------- checks
def distance_map_problems(maze: dict, steps: list[list[int]]) -> list[str]:
    """Every cell is 1 + its smallest open neighbour (the exit is 0, a cell with only unreachable neighbours is -1)."""
    problems = []
    exit_cell = maze["exit_cell"]
    for row in range(maze["rows"]):
        for col in range(maze["cols"]):
            if (row, col) == (exit_cell["row"], exit_cell["col"]):
                expected = 0
            else:
                reachable = [steps[r][c] for r, c in open_neighbours(maze, row, col) if steps[r][c] != UNREACHABLE]
                expected = 1 + min(reachable) if reachable else UNREACHABLE
            if steps[row][col] != expected:
                problems.append(f"{maze['maze_id']}: cell ({row},{col}) has {steps[row][col]}, expected {expected}")
    return problems


def route_problems(maze: dict, steps: list[list[int]], route_lines: list[dict]) -> list[str]:
    """A valid route starts next to the ball cell, moves through open cells and gets one step closer each time."""
    problems = []
    for item in route_lines:
        msg = item["msg"]
        if msg["status"] != "valid":
            continue
        row, col = msg["ball_cell"]["row"], msg["ball_cell"]["col"]
        for x_mm, y_mm in msg["target_points_mm"]:
            cell = cell_at_mm(maze, x_mm, y_mm)
            if cell is None or (cell["row"], cell["col"]) not in open_neighbours(maze, row, col) \
                    or steps[cell["row"]][cell["col"]] != steps[row][col] - 1:
                problems.append(f"{maze['maze_id']}: route at t={item['t_s']} leaves the open cells")
                break
            row, col = cell["row"], cell["col"]
    return problems


def schema_problems(files: dict[str, list[dict]]) -> list[str]:
    problems = []
    for name, lines in files.items():
        for item in lines:
            try:
                validate(item["topic"], {**ENVELOPE, "writer": T.topic_info(item["topic"])["writer"], **item["msg"]})
            except ValidationError as error:
                problems.append(f"{name}: t={item['t_s']} {item['topic']}: {error.message}")
                break
    return problems


# ---------------------------------------------------------------------- main
def read_inputs() -> tuple[list[dict], dict, dict]:
    def read_json(name: str) -> dict:
        try:
            return json.loads((INPUT_DIR / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise FixtureError(f"{name}: {error}") from None

    platform, path = read_json("platform.json"), read_json("ball_path.json")
    try:
        mazes = [parse_maze((INPUT_DIR / name).read_text(encoding="utf-8"), maze_id, platform, name)
                 for name, maze_id in zip(MAZE_FILES, MAZE_IDS)]
    except (OSError, KeyError) as error:
        raise FixtureError(f"maze or platform input: {error}") from None
    first, second = mazes
    if (first["rows"], first["cols"], first["exit_cell"]) != (second["rows"], second["cols"], second["exit_cell"]):
        raise FixtureError("the two mazes must have the same size and the same exit (the ball samples are shared)")
    if first["ball_diameter_mm"] >= first["cell_size_mm"] - first["wall_thickness_mm"]:
        raise FixtureError("platform.json: ball_diameter_mm does not fit between two walls (cell_size_mm - wall_thickness_mm)")
    if first["exit_radius_mm"] > first["cell_size_mm"] / 2:
        raise FixtureError("platform.json: exit_radius_mm is larger than half a cell")
    cells = [tuple(cell) for cell in path["cells"]]
    for row, col in cells:
        if cell_at_mm(first, *cell_centre_mm(first, {"row": row, "col": col})) is None:
            raise FixtureError(f"ball_path.json: cell ({row},{col}) is outside the maze")
    for before, after in zip(cells, cells[1:]):
        if before != after and after not in open_neighbours(first, *before):
            raise FixtureError(f"ball_path.json: {before} to {after} crosses a wall (first maze)")
    return mazes, path, platform


def build(mazes: list[dict], path: dict, platform: dict) -> dict[str, list[dict]]:
    track = BallTrack(mazes[0], path, platform)
    steps = [distance_steps(maze) for maze in mazes]
    duration_s = track.duration_s
    files = {"samples.jsonl": platform_samples(track, mazes[0], platform),
             "start.jsonl": maze_lines(0.0, mazes[0], steps[0], "file_checked"),
             "maze_changed.jsonl": maze_lines(0.0, mazes[1], steps[1], "scan") + [clear_line(0.0, mazes[1])],
             "hand.jsonl": [line(0.0, T.VISION_EDIT_STATE, edit_state_message(HAND_STATE, "hand", None))],
             "read_maze.jsonl": [line(0.0, T.VISION_EDIT_STATE, edit_state_message(RESCAN_STATE, None, None))]
             + maze_lines(platform["rescan_s"], mazes[0], steps[0], "scan") + [clear_line(platform["rescan_s"], mazes[0])],
             "edit_hand.jsonl": edit_stream(HAND_STATE, "hand", None, duration_s),
             "edit_rescanning.jsonl": edit_stream(RESCAN_STATE, None, None, duration_s)}
    for suffix, maze, maze_steps in (("start", mazes[0], steps[0]), ("changed", mazes[1], steps[1])):
        files[f"route_{suffix}.jsonl"] = route_stream(maze, maze_steps, track)
        files[f"controller_{suffix}.jsonl"] = controller_stream(maze, maze_steps, track)
        files[f"edit_{suffix}.jsonl"] = edit_stream(CLEAR_STATE, None, maze["maze_id"], duration_s)
    return files


def check(mazes: list[dict], files: dict[str, list[dict]]) -> list[str]:
    problems = []
    for maze, suffix in zip(mazes, ("start", "changed")):
        steps = distance_steps(maze)
        problems += distance_map_problems(maze, steps) + route_problems(maze, steps, files[f"route_{suffix}.jsonl"])
    return problems + schema_problems(files)


def write(files: dict[str, list[dict]], behaviour_data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for name, lines in files.items():
        (DATA_DIR / name).write_text("".join(json.dumps(item, separators=(",", ":")) + "\n" for item in lines), encoding="utf-8")
    (DATA_DIR / "behaviour.json").write_text(json.dumps(behaviour_data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    try:
        mazes, path, platform = read_inputs()
        files = build(mazes, path, platform)
        problems = check(mazes, files)
    except FixtureError as error:
        print(f"input error: {error}", file=sys.stderr)
        return 2
    if problems:
        print("\n".join(["The generated data failed its checks, nothing was written:"] + problems[:10]), file=sys.stderr)
        return 1
    duration_s = BallTrack(mazes[0], path, platform).duration_s
    write(files, behaviour(duration_s, platform["rescan_s"]))
    print(f"wrote {len(files) + 1} files to {DATA_DIR} (loop {duration_s:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
