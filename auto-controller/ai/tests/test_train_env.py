import dataclasses

import numpy as np
import pytest

from ai.episode_params import nominal_episode_params
from ai.plate_world import PHYSICS_HZ, PlateWorld
from ai.train_env import TrainEnv
from ai.train_env_config import load_train_env_config
from shared.mazes import MazeGrid
from shared.mazes.maze_grid import WALL_E, WALL_N, WALL_S, WALL_W

CELL_SIZE_MM = 25.0
EXIT_RADIUS_MM = 8.0
BALL_DIAMETER_MM = 14.0
STEPS_TO_ROLL = 30  # one second at the slowest camera rate; enough to roll at least one cell
ALWAYS_PER_S = 1e6  # an occlusion rate that starts an occlusion in every frame near a wall
LONGER_THAN_LOST_TIMEOUT_MS = 300.0  # occlusion length above the default lost_timeout_ms (200 ms)
RANDOM_STEPS = 300  # ten seconds of random actions at the slowest camera rate
PYBULLET_DEFAULT_RESTITUTION_SPEED_MM_S = 200.0  # PyBullet bounces only faster hits by default
WALL_FACE_GAP_MM = 20.0  # the ball starts this far from the east wall face of the start cell
BOUNCE_SPEED_MM_S = 20.0  # a speed back from the wall that is clearly a bounce
TWO_SECONDS_OF_PHYSICS = 2 * PHYSICS_HZ
TOO_LARGE_CELL_MM = 150.0  # 3 x 150 mm does not fit on the 208 mm plate


def open_maze(rows: int, cols: int, start_cell, exit_cell) -> MazeGrid:
    """A maze with only its outer walls, centred on the board origin (D4)."""
    walls = []
    for row in range(rows):
        walls.append(tuple(
            (WALL_S if row == 0 else 0) | (WALL_N if row == rows - 1 else 0)
            | (WALL_W if col == 0 else 0) | (WALL_E if col == cols - 1 else 0)
            for col in range(cols)))
    origin_x_mm, origin_y_mm = -cols * CELL_SIZE_MM / 2.0, -rows * CELL_SIZE_MM / 2.0
    exit_x_mm = origin_x_mm + (exit_cell[1] + 0.5) * CELL_SIZE_MM
    exit_y_mm = origin_y_mm + (exit_cell[0] + 0.5) * CELL_SIZE_MM
    return MazeGrid(
        maze_id="test-open", cell_size_mm=CELL_SIZE_MM, rows=rows, cols=cols,
        origin_x_mm=origin_x_mm, origin_y_mm=origin_y_mm, walls=tuple(walls),
        wall_thickness_mm=2.0, wall_height_mm=10.0, start_cell=start_cell, exit_cell=exit_cell,
        exit_x_mm=exit_x_mm, exit_y_mm=exit_y_mm, exit_radius_mm=EXIT_RADIUS_MM, ball_diameter_mm=BALL_DIAMETER_MM)


# A 3 x 3 room: start in the middle, exit in a corner.
ROOM = open_maze(3, 3, start_cell=(1, 1), exit_cell=(2, 2))
# A corridor along +x: start at the west end, exit at the east end.
CORRIDOR = open_maze(1, 4, start_cell=(0, 0), exit_cell=(0, 3))


@pytest.fixture
def env():
    environment = TrainEnv()
    yield environment
    environment.close()


def env_with(**changes) -> TrainEnv:
    """A TrainEnv whose configuration differs from config/train_env.json in the given fields."""
    return TrainEnv(dataclasses.replace(load_train_env_config(), **changes))


def roll(env: TrainEnv, action_deg, steps: int = STEPS_TO_ROLL):
    """Apply the same target tilt for some steps; returns the last step's outputs."""
    for _ in range(steps):
        observation, reward, terminated, truncated, info = env.step(np.array(action_deg))
        if terminated or truncated:
            break
    return observation, reward, terminated, truncated, info


def test_reset_gives_the_if08_raw_state(env):
    observation, info = env.reset(seed=1, options={"maze": ROOM})
    assert env.observation_space.contains(observation)
    assert set(info) == {"maze", "env_params", "target_points_mm"}
    assert info["maze"] is ROOM
    assert info["env_params"]["max_tilt_deg"] == env.config.max_tilt_deg
    # The ball is seen at the start, and Vision's filter starts a new track at rest (shared/ball_filter).
    assert observation["is_visible"] == 1 and observation["is_predicted"] == 0
    assert observation["vx_mm_s"] == 0.0 and observation["vy_mm_s"] == 0.0


def test_route_targets_come_from_the_shared_route_function(env):
    _, info = env.reset(seed=1, options={"maze": CORRIDOR, "randomize": False})
    # From the west end the next three cell centres along the corridor (C.5, plan/route).
    assert info["target_points_mm"] == [[-12.5, 0.0], [12.5, 0.0], [37.5, 0.0]]


def test_positive_tilt_x_rolls_the_ball_to_plus_x(env):
    observation, _ = env.reset(seed=1, options={"maze": ROOM, "randomize": False})
    start_x_mm, start_y_mm = float(observation["x_mm"]), float(observation["y_mm"])
    observation, *_ = roll(env, [env.config.max_tilt_deg, 0.0])
    assert observation["x_mm"] > start_x_mm + CELL_SIZE_MM / 2.0
    assert abs(observation["y_mm"] - start_y_mm) < CELL_SIZE_MM / 2.0


def test_positive_tilt_y_rolls_the_ball_to_plus_y(env):
    observation, _ = env.reset(seed=1, options={"maze": ROOM, "randomize": False})
    start_x_mm, start_y_mm = float(observation["x_mm"]), float(observation["y_mm"])
    observation, *_ = roll(env, [0.0, env.config.max_tilt_deg])
    assert observation["y_mm"] > start_y_mm + CELL_SIZE_MM / 2.0
    assert abs(observation["x_mm"] - start_x_mm) < CELL_SIZE_MM / 2.0


def test_ball_rolling_into_a_wall_is_a_wall_hit(env):
    env.reset(seed=1, options={"maze": ROOM, "randomize": False})
    wall_sides = []
    for _ in range(STEPS_TO_ROLL):
        *_, info = env.step(np.array([env.config.max_tilt_deg, 0.0]))
        wall_sides += [hit["wall_side"] for hit in info["wall_hits"]]
    assert "e" in wall_sides


def test_ball_held_on_the_exit_ends_the_episode(env):
    env.reset(seed=1, options={"maze": CORRIDOR, "randomize": False})
    *_, terminated, truncated, info = roll(env, [env.config.max_tilt_deg, 0.0], steps=10 * STEPS_TO_ROLL)
    assert terminated and not truncated
    assert info["is_on_exit"]
    assert info["cell"] == {"row": 0, "col": 3}
    assert info["distance_to_exit_cells"] == 0


def test_same_seed_repeats_the_episode():
    observations = []
    for _ in range(2):
        environment = TrainEnv()
        environment.reset(seed=7, options={"maze": ROOM})
        observation, *_ = roll(environment, [1.0, -2.0], steps=10)
        observations.append(observation)
        environment.close()
    for name in observations[0]:
        assert observations[0][name] == observations[1][name]


def test_maze_without_start_cell_starts_somewhere_else_than_the_exit(env):
    maze = open_maze(2, 2, start_cell=None, exit_cell=(1, 1))
    for seed in range(10):
        observation, _ = env.reset(seed=seed, options={"maze": maze, "randomize": False})
        assert maze.cell_of(float(observation["x_mm"]), float(observation["y_mm"])) != maze.exit_cell


def test_unknown_reset_option_is_refused(env):
    with pytest.raises(ValueError):
        env.reset(seed=1, options={"maze": ROOM, "randomise": False})


def test_action_must_be_two_finite_numbers(env):
    env.reset(seed=1, options={"maze": ROOM})
    with pytest.raises(ValueError):
        env.step(np.array([1.0, np.nan]))
    with pytest.raises(ValueError):
        env.step(np.array([1.0, 2.0, 3.0]))


def test_velocity_comes_from_the_filter_and_follows_the_ball(env):
    env.reset(seed=1, options={"maze": ROOM, "randomize": False})
    observation, *_ = roll(env, [env.config.max_tilt_deg, 0.0], steps=STEPS_TO_ROLL // 3)
    assert observation["vx_mm_s"] > 0.0
    assert abs(observation["vy_mm_s"]) < observation["vx_mm_s"]


def test_occlusion_near_a_wall_is_bridged_then_the_ball_is_lost_and_found_again():
    env = env_with(occlusion_rate_per_s=ALWAYS_PER_S, occlusion_min_ms=LONGER_THAN_LOST_TIMEOUT_MS,
                   occlusion_max_ms=LONGER_THAN_LOST_TIMEOUT_MS)
    env.reset(seed=1, options={"maze": ROOM, "randomize": False})
    into_wall = [env.step(np.array([env.config.max_tilt_deg, 0.0])) for _ in range(STEPS_TO_ROLL)]
    away_from_wall = [env.step(np.array([-env.config.max_tilt_deg / 4.0, 0.0])) for _ in range(STEPS_TO_ROLL)]
    env.close()
    bridged = [obs for obs, *_ in into_wall if obs["is_visible"] == 1 and obs["is_predicted"] == 1]
    lost = [(obs, info) for obs, *_, info in into_wall if obs["is_visible"] == 0]
    assert bridged and lost
    for obs, info in lost:
        # vision/ball: velocity 0 while not visible; plan/route: invalid, so no distance (C.5)
        assert obs["vx_mm_s"] == 0.0 and obs["vy_mm_s"] == 0.0
        assert info["distance_to_exit_cells"] is None and not info["is_on_exit"]
    assert any(obs["is_visible"] == 1 and obs["is_predicted"] == 0 for obs, *_ in away_from_wall)


def test_reset_forgets_a_lost_ball():
    env = env_with(occlusion_rate_per_s=ALWAYS_PER_S, occlusion_min_ms=LONGER_THAN_LOST_TIMEOUT_MS,
                   occlusion_max_ms=LONGER_THAN_LOST_TIMEOUT_MS)
    env.reset(seed=1, options={"maze": ROOM, "randomize": False})
    observation, *_ = roll(env, [env.config.max_tilt_deg, 0.0])
    assert observation["is_visible"] == 0
    observation, _ = env.reset(seed=1, options={"maze": ROOM, "randomize": False})
    env.close()
    assert observation["is_visible"] == 1 and observation["is_predicted"] == 0


def test_a_dropped_frame_makes_the_step_last_two_frame_periods():
    distances_mm = []
    for chance in (0.0, 1.0):
        env = env_with(frame_drop_chance=chance)
        observation, _ = env.reset(seed=1, options={"maze": CORRIDOR, "randomize": False})
        start_x_mm = float(observation["x_mm"])
        observation, *_ = roll(env, [env.config.max_tilt_deg, 0.0], steps=STEPS_TO_ROLL // 3)
        distances_mm.append(float(observation["x_mm"]) - start_x_mm)
        env.close()
    no_drops_mm, every_frame_dropped_mm = distances_mm
    assert every_frame_dropped_mm > no_drops_mm


def test_bad_occlusion_range_is_refused():
    with pytest.raises(ValueError):
        env_with(occlusion_min_ms=100.0, occlusion_max_ms=50.0)


def test_ball_stays_inside_the_maze_with_random_actions():
    env = TrainEnv()
    for seed in range(3):
        env.reset(seed=seed, options={"maze": ROOM})
        for _ in range(RANDOM_STEPS):
            *_, info = env.step(env.np_random.uniform(-env.config.max_tilt_deg, env.config.max_tilt_deg, size=2))
            assert info["cell"] is not None
    env.close()


def wall_bounce(restitution: float) -> tuple[float, float]:
    """Hit speed and the speed back from the east wall (mm/s) for a ball rolling in at max tilt."""
    config = load_train_env_config()
    params = dataclasses.replace(nominal_episode_params(config, CELL_SIZE_MM), restitution=restitution)
    world = PlateWorld()
    world.build(ROOM, config, params)
    contact_x_mm = CELL_SIZE_MM * 1.5 - ROOM.wall_thickness_mm / 2.0 - BALL_DIAMETER_MM / 2.0
    world.place_ball(contact_x_mm - WALL_FACE_GAP_MM, 0.0)
    world.set_tilt(config.max_tilt_deg, 0.0)
    speeds_mm_s = []
    for _ in range(TWO_SECONDS_OF_PHYSICS):
        world.step()
        speeds_mm_s.append(float(world.ball_velocity_mm_s()[0]))
    world.close()
    return max(speeds_mm_s), -min(speeds_mm_s)


def test_slow_wall_hit_bounces_with_restitution():
    hit_mm_s, back_with_restitution_mm_s = wall_bounce(restitution=load_train_env_config().restitution.nominal)
    _, back_without_restitution_mm_s = wall_bounce(restitution=0.0)
    assert hit_mm_s < PYBULLET_DEFAULT_RESTITUTION_SPEED_MM_S
    assert back_with_restitution_mm_s > BOUNCE_SPEED_MM_S > back_without_restitution_mm_s


def test_maze_larger_than_the_plate_is_refused(env):
    # The same 3 x 3 room, centred on the origin, with cells of TOO_LARGE_CELL_MM; the exit stays in cell (2, 2).
    large = dataclasses.replace(ROOM, cell_size_mm=TOO_LARGE_CELL_MM,
                                origin_x_mm=-1.5 * TOO_LARGE_CELL_MM, origin_y_mm=-1.5 * TOO_LARGE_CELL_MM,
                                exit_x_mm=TOO_LARGE_CELL_MM, exit_y_mm=TOO_LARGE_CELL_MM)
    assert large.validate()
    with pytest.raises(ValueError, match="does not fit"):
        env.reset(seed=1, options={"maze": large})


def test_randomize_must_be_a_bool(env):
    with pytest.raises(ValueError):
        env.reset(seed=1, options={"maze": ROOM, "randomize": "false"})


def test_step_before_reset_is_refused():
    env = TrainEnv()
    with pytest.raises(RuntimeError):
        env.step(np.zeros(2))
    env.close()


def test_close_twice_does_nothing_the_second_time():
    env = TrainEnv()
    env.close()
    env.close()
