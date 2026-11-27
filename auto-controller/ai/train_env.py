"""TrainEnv: the training environment of Learning (IF-08).

    reset(seed, options) -> observation, info
    step(action)         -> observation, reward, terminated, truncated, info

A Gymnasium environment; the physics is in PlateWorld (PyBullet) and the ball as Vision sees it
(noise, short occlusions near walls, Vision's filter) in SimulatedVision. The observation is the raw
state of IF-08 with the bus names and units (D4). ObservationBuilder (D.5) turns it into the
network input with the same code as at runtime. Used only for training and offline evaluation,
never during a game.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import gymnasium
import numpy as np
from gymnasium import spaces

from ai.episode_params import EpisodeParams, nominal_episode_params, random_episode_params
from ai.plate_world import EAST, NORTH, PHYSICS_HZ, SOUTH, WEST, PlateWorld
from ai.simulated_vision import SimulatedVision
from ai.tilt_actuator import TiltActuator
from ai.train_env_config import TrainEnvConfig, load_train_env_config
from ai.wall_segment import WallSegment
from shared.ball_filter import BallEstimate
from shared.mazes import MazeGrid, Route, build_distance_map, plan_route  # shared maze helper (IF-04, C.5)
from shared.mazes.maze_grid import Cell
from shared.mazes.route import ROUTE_INVALID, ROUTE_VALID

MAZES_DIR = Path(__file__).resolve().parents[2] / "shared" / "mazes"
MS_PER_S = 1000.0
RESET_OPTIONS = frozenset({"maze", "randomize"})  # IF-08 reset options
FLOAT_FIELDS = ("x_mm", "y_mm", "vx_mm_s", "vy_mm_s", "tilt_x_deg", "tilt_y_deg",
                "applied_tilt_x_deg", "applied_tilt_y_deg")
BOOL_FIELDS = ("is_visible", "is_predicted")
BOOL_VALUE_COUNT = 2  # a bool field is 0 or 1 in the observation space
NO_ROUTE = Route(ROUTE_INVALID, None, (), None)  # plan/route: invalid = no valid maze or ball not visible (C.5)
AXES = 2  # x and y (D4)
FIRST_FRAME_DT_S = 0.0  # the frame at reset has no previous frame
FRAMES_IN_A_DROP = 2  # a dropped camera frame makes the step last two frame periods


class TrainEnv(gymnasium.Env):
    """Plate, maze and ball for training and offline evaluation (IF-08)."""

    metadata = {"render_modes": []}

    def __init__(self, config: TrainEnvConfig | None = None) -> None:
        self.config = config or load_train_env_config()
        limit_deg = self.config.max_tilt_deg
        self.action_space = spaces.Box(-limit_deg, limit_deg, shape=(AXES,), dtype=np.float32)
        self.observation_space = _observation_space()
        self._world = PlateWorld()
        self._vision = SimulatedVision(self.config)

    # ------------------------------------------------------------------ IF-08

    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple[dict, dict]:
        """Start an episode. options: maze (MazeGrid; default a random file from shared/mazes/),
        randomize (bool, default true)."""
        super().reset(seed=seed)
        options = _checked_options(options)
        self._maze = self._checked_maze(options.get("maze"))
        self._steps_to_exit = build_distance_map(self._maze)  # once per maze; plan_route reads it every step
        self._params = self._episode_params(options.get("randomize", True))
        self._world.build(self._maze, self.config, self._params)
        self._world.place_ball(*self._start_position_mm())
        self._actuator = TiltActuator(self.config.max_tilt_speed_deg_s, self._params.latency_ms / MS_PER_S)
        self._substeps = round(self._params.step_dt_s * PHYSICS_HZ)
        self._time_s = 0.0
        self._exit_frames = 0
        self._previous_action_deg = np.zeros(AXES)
        self._vision.reset(self._maze, self._world.walls, self._params.noise_std_mm, self.np_random)
        self._see_ball(FIRST_FRAME_DT_S)
        self._route = self._plan_route()
        self._route_distance_mm = self._distance_along_route_mm()
        return self._observation(), self._reset_info()

    def step(self, action: np.ndarray) -> tuple[dict, float, bool, bool, dict]:
        """Apply a target tilt (deg, as ai/target_tilt) until the next camera frame.

        While the ball is not visible the route is invalid, as in plan/route: target_points_mm is empty and
        distance_to_exit_cells is None. At runtime the controller then sends nothing (D.5) and the platform's
        command timeout levels the plate, so the trainer's wrapper (#67) decides the action for such a step."""
        applied_deg = self._limited_action(action)
        self._actuator.command(self._time_s, applied_deg)
        frame_dt_s, wall_hits = self._run_frame_period()
        self._see_ball(frame_dt_s)
        self._count_exit_frames()
        self._route = self._plan_route()
        tilt_change_deg = applied_deg - self._previous_action_deg
        reward = self._reward(self._take_progress_mm(), frame_dt_s, len(wall_hits), tilt_change_deg)
        self._previous_action_deg = applied_deg
        terminated = self._exit_frames >= self.config.exit_hold_frames
        truncated = self._time_s >= self.config.time_limit_s
        return self._observation(), reward, terminated, truncated, self._step_info(wall_hits)

    def close(self) -> None:
        """Free the physics library."""
        self._world.close()

    # ------------------------------------------------------------------ episode set-up

    def _checked_maze(self, maze: MazeGrid | None) -> MazeGrid:
        if maze is None:
            maze = self._random_maze_file()
        if not maze.validate():
            raise ValueError(f"maze {maze.maze_id} is not valid")
        return maze

    def _random_maze_file(self) -> MazeGrid:
        paths = sorted(MAZES_DIR.glob("*.json"))
        if not paths:
            raise FileNotFoundError(f"no maze files in {MAZES_DIR}")
        return MazeGrid.load(str(paths[self.np_random.integers(len(paths))]))

    def _episode_params(self, randomize: bool) -> EpisodeParams:
        if randomize:
            params = random_episode_params(self.config, self.np_random, self._maze.cell_size_mm)
        else:
            params = nominal_episode_params(self.config, self._maze.cell_size_mm)
        # A frame period lasts a whole number of physics steps, so step_dt_s is rounded to that; the reset
        # info then shows the frame period that is really used (a step with a frame drop lasts two).
        physics_steps = round(params.step_dt_s * PHYSICS_HZ)
        return dataclasses.replace(params, step_dt_s=physics_steps / PHYSICS_HZ)

    def _start_position_mm(self) -> tuple[float, float]:
        cell = self._maze.start_cell or self._random_cell_except_exit()
        centre_x_mm, centre_y_mm = self._maze.cell_centre_mm(*cell)
        offset_x_mm, offset_y_mm = self._params.start_offset_mm
        return centre_x_mm + offset_x_mm, centre_y_mm + offset_y_mm

    def _random_cell_except_exit(self) -> Cell:
        """A maze file may leave start_cell out; then any cell can be the start (IF-04)."""
        cells = [(row, col) for row in range(self._maze.rows) for col in range(self._maze.cols)]
        cells.remove(self._maze.exit_cell)
        return cells[self.np_random.integers(len(cells))]

    # ------------------------------------------------------------------ one step

    def _limited_action(self, action: np.ndarray) -> np.ndarray:
        """The target tilt after the limits, as the platform applies it."""
        action_deg = np.asarray(action, dtype=float)
        if action_deg.shape != (AXES,) or not np.all(np.isfinite(action_deg)):
            raise ValueError(f"action must be two finite numbers (deg), got {action!r}")
        return np.clip(action_deg, -self.config.max_tilt_deg, self.config.max_tilt_deg)

    def _run_frame_period(self) -> tuple[float, list[dict]]:
        """Run the physics until the next camera frame; returns the time this took and the wall hits."""
        physics_dt_s = 1.0 / PHYSICS_HZ
        # ASSUMPTION: IF-08 asks for "occasional frame drops" without a rate. With frame_drop_chance the camera
        # drops a frame, so the AI gets its next observation, and acts again, two frame periods later.
        frames = FRAMES_IN_A_DROP if self.np_random.random() < self.config.frame_drop_chance else 1
        physics_steps = frames * self._substeps
        # The real plate is off by a small offset from what the platform measures (IF-08).
        tilt_offset_deg = np.array(self._params.tilt_offset_deg)
        wall_hits = []
        for _ in range(physics_steps):
            self._time_s += physics_dt_s
            self._actuator.advance(self._time_s, physics_dt_s)
            self._world.set_tilt(*(self._actuator.tilt_deg + tilt_offset_deg))
            wall_hits += [self._wall_hit(wall, velocity) for wall, velocity in self._world.step()]
        return physics_steps * physics_dt_s, [hit for hit in wall_hits if hit is not None]

    def _wall_hit(self, wall: WallSegment, velocity_before_mm_s: np.ndarray) -> dict | None:
        """A contact counts as a hit only if the ball came fast enough, as in Vision (IF-04, vision/event)."""
        x_mm, y_mm = self._world.ball_position_mm()
        vx_mm_s, vy_mm_s = velocity_before_mm_s
        if wall.is_along_x:
            wall_side = NORTH if wall.centre_y_mm > y_mm else SOUTH
            speed_towards_wall_mm_s = vy_mm_s if wall_side == NORTH else -vy_mm_s
        else:
            wall_side = EAST if wall.centre_x_mm > x_mm else WEST
            speed_towards_wall_mm_s = vx_mm_s if wall_side == EAST else -vx_mm_s
        if speed_towards_wall_mm_s < self.config.wall_hit_min_speed_mm_s:
            return None
        return {"cell": self._cell_of(x_mm, y_mm), "wall_side": wall_side,
                "impact_speed_mm_s": float(speed_towards_wall_mm_s)}

    def _see_ball(self, frame_dt_s: float) -> None:
        """The ball as Vision reports it in this frame (filtered estimate, IF-04 vision/ball)."""
        self._ball: BallEstimate = self._vision.see(self._world.ball_position_mm(), self._time_s, frame_dt_s)
        self._ball_position_mm = np.array([self._ball.x_mm, self._ball.y_mm])

    def _is_on_exit(self) -> bool:
        """Same rule as Vision's is_on_exit (IF-04): measured centre within exit_radius_mm; false when the
        ball was not detected in this frame (is_predicted or not visible)."""
        measured_mm = self._vision.measured_mm
        if measured_mm is None:
            return False
        exit_mm = np.array([self._maze.exit_x_mm, self._maze.exit_y_mm])
        return bool(np.linalg.norm(measured_mm - exit_mm) <= self._maze.exit_radius_mm)

    def _count_exit_frames(self) -> None:
        """Consecutive frames on the exit, the same count as GameManager (5.3)."""
        self._exit_frames = self._exit_frames + 1 if self._is_on_exit() else 0

    # ------------------------------------------------------------------ route and reward

    def _plan_route(self) -> Route:
        """The same route function and input as Vision's PathPlanner (C.5): the filtered ball position,
        and no route while the ball is not visible. So the AI sees the same routes as in a game (IF-04)."""
        if not self._ball.is_visible:
            return NO_ROUTE
        return plan_route(self._maze, self._steps_to_exit, self._ball.x_mm, self._ball.y_mm)

    def _distance_along_route_mm(self) -> float | None:
        """Distance from the ball to the exit along the route: to the first route point, then one
        cell size per remaining step. None without a valid route."""
        if self._route.status != ROUTE_VALID:
            return None
        first_point_mm = np.array(self._route.target_points_mm[0])
        steps_after_first_point = max(self._route.distance_to_exit_cells - 1, 0)
        distance_to_first_point_mm = np.linalg.norm(first_point_mm - self._ball_position_mm)
        return float(distance_to_first_point_mm + steps_after_first_point * self._maze.cell_size_mm)

    def _take_progress_mm(self) -> float:
        """How much closer to the exit the ball came in this step; 0 without a valid route."""
        distance_mm = self._distance_along_route_mm()
        previous_mm = self._route_distance_mm
        self._route_distance_mm = distance_mm
        if distance_mm is None or previous_mm is None:
            return 0.0
        return previous_mm - distance_mm

    def _reward(self, progress_mm: float, frame_dt_s: float, wall_hit_count: int,
                tilt_change_deg: np.ndarray) -> float:
        """Progress along the route, minus time, wall hits and large changes in tilt (D.5).
        The tilt change is squared, so large changes cost much more than small ones."""
        return float(
            self.config.progress_reward_per_mm * progress_mm
            - self.config.time_penalty_per_s * frame_dt_s
            - self.config.wall_hit_penalty * wall_hit_count
            - self.config.tilt_change_penalty_per_deg2 * np.sum(tilt_change_deg ** 2)
        )

    # ------------------------------------------------------------------ outputs

    def _observation(self) -> dict:
        """The raw state of IF-08 (step table), with the bus names."""
        x_mm, y_mm, vx_mm_s, vy_mm_s = self._ball.x_mm, self._ball.y_mm, self._ball.vx_mm_s, self._ball.vy_mm_s
        tilt_x_deg, tilt_y_deg = self._actuator.tilt_deg
        # applied tilt is the target after the angle and speed limits (IF-02). The plate follows it
        # exactly here (the motor is modelled by the speed limit, IF-06), so it equals the measured tilt.
        applied_x_deg, applied_y_deg = tilt_x_deg, tilt_y_deg
        floats = (x_mm, y_mm, vx_mm_s, vy_mm_s, tilt_x_deg, tilt_y_deg, applied_x_deg, applied_y_deg)
        pairs = zip(FLOAT_FIELDS, floats, strict=True)
        observation = {name: np.array(value, dtype=np.float32) for name, value in pairs}
        observation["is_visible"] = int(self._ball.is_visible)
        observation["is_predicted"] = int(self._ball.is_predicted)
        return observation

    def _step_info(self, wall_hits: list[dict]) -> dict:
        return {
            "cell": self._cell_of(*self._ball_position_mm),
            "distance_to_exit_cells": self._route.distance_to_exit_cells,
            "is_on_exit": self._is_on_exit(),
            "wall_hits": wall_hits,
            "target_points_mm": _as_message_points(self._route),
        }

    def _reset_info(self) -> dict:
        """The test maze, the environment parameters and the route targets (IF-08)."""
        return {
            "maze": self._maze,
            "env_params": {**self.config.to_dict(), **self._params.to_dict()},
            "target_points_mm": _as_message_points(self._route),
        }

    def _cell_of(self, x_mm: float, y_mm: float) -> dict | None:
        """The cell as in the messages ({row, col}, IF-04); None when the point is outside the grid,
        as the shared helper reports it (cell_of)."""
        cell = self._maze.cell_of(float(x_mm), float(y_mm))
        if cell is None:
            return None
        row, col = cell
        return {"row": row, "col": col}


def _checked_options(options: dict | None) -> dict:
    """reset options of IF-08; a misspelt option must not be ignored silently."""
    options = options or {}
    unknown = set(options) - RESET_OPTIONS
    if unknown:
        raise ValueError(f"unknown reset option(s) {sorted(unknown)}; known: {sorted(RESET_OPTIONS)}")
    return options


def _as_message_points(route: Route) -> list[list[float]]:
    """Route points as plan/route sends them: a list of [x_mm, y_mm] (IF-04)."""
    return [[x_mm, y_mm] for x_mm, y_mm in route.target_points_mm]


def _observation_space() -> spaces.Dict:
    """gymnasium.spaces.Dict with the IF-08 names (IF-08, Format)."""
    floats = {name: spaces.Box(-np.inf, np.inf, shape=(), dtype=np.float32) for name in FLOAT_FIELDS}
    bools = {name: spaces.Discrete(BOOL_VALUE_COUNT) for name in BOOL_FIELDS}
    return spaces.Dict({**floats, **bools})
