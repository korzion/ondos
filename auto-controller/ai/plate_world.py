"""PlateWorld: the plate, the walls and the ball inside TrainEnv, simulated with PyBullet (IF-08).

Only this file talks to the physics library, so another library can be used without changing
TrainEnv (D.10, "Chosen physics library does not fit"). PyBullet works in metres and kilograms;
everything that leaves this file is in mm, mm/s and deg (D4).

The plate stays fixed and gravity is turned instead: seen from the plate, a tilted plate is the
same as tilted gravity. So the ball position is directly in the board frame, as Vision reports
it (IF-04). What this leaves out are the small forces caused by the plate's own turning speed.
"""
from __future__ import annotations

import itertools
import math
from typing import TYPE_CHECKING

import numpy as np
import pybullet

from ai.episode_params import EpisodeParams
from ai.train_env_config import TrainEnvConfig
from ai.wall_segment import WallSegment
from shared import topics
from shared.mazes.maze_grid import WALL_E, WALL_N, WALL_S, WALL_W

if TYPE_CHECKING:  # only for the type hints; the maze object itself comes from TrainEnv
    from shared.mazes import MazeGrid

PHYSICS_HZ = 240  # IF-08: the physics runs at 240 Hz inside each step
AXES = 2  # x and y of the board frame (D4)
GRAVITY_M_S2 = 9.81
MM_PER_M = 1000.0
MS_PER_S = 1000.0
G_PER_KG = 1000.0
STATIC_MASS_KG = 0.0  # mass 0 makes a body static in PyBullet
PLATE_THICKNESS_MM = 5.0  # collision body only; the ball rolls on its top face at z = 0
# PyBullet multiplies the sliding friction and the restitution of the two bodies in a contact and
# adds their rolling friction. The static bodies get 1 and 0, so the ball's values are the ones
# that act. The plate gets restitution 0, so the ball does not bounce on the floor.
STATIC_FRICTION = 1.0
STATIC_ROLLING_FRICTION_M = 0.0
WALL_RESTITUTION = 1.0
PLATE_RESTITUTION = 0.0
# friction_coeff is the rolling resistance: it is what slows a rolling ball. Sliding friction makes
# the ball roll, which needs only (2/7)·tan(tilt) < 0.05; along a wall it also slows the ball, with
# the same result for any realistic value (0.3 to 1 tested), so it is a fixed value.
BALL_GRIP_FRICTION = 1.0
NO_DAMPING = 0.0  # PyBullet adds damping by default; friction is the only loss we model
BASE_LINK = -1  # PyBullet's index for the body itself (it has no other links)
NO_BODY = -1  # PyBullet body id before the body is created
NO_ROTATION = [0.0, 0.0, 0.0, 1.0]  # quaternion of an unturned body
AT_REST = [0.0, 0.0, 0.0]  # zero linear or angular velocity
WALL_KEY_DECIMALS = 3  # walls closer than 0.001 mm are the same wall
# PyBullet applies restitution only to contacts faster than this speed (its default is 0.2 m/s). With a
# max tilt of a few degrees most wall hits are slower, so the default would make restitution useless.
# ASSUMPTION: 0.01 m/s lets the slow wall hits bounce and still lets a ball rest against a wall without jitter.
RESTITUTION_VELOCITY_THRESHOLD_M_S = 0.01

NORTH, EAST, SOUTH, WEST = topics.WALL_SIDE_VALUES  # wall_side names of vision/event (IF-04)
WALL_BITS = {NORTH: WALL_N, EAST: WALL_E, SOUTH: WALL_S, WEST: WALL_W}  # walls[row][col] bit flags (IF-04)


class PlateWorld:
    """The simulated plate with its maze walls and the ball."""

    def __init__(self) -> None:
        self._client = pybullet.connect(pybullet.DIRECT)  # no window; one client per environment
        self._ball_id = NO_BODY
        self._ball_radius_mm = 0.0
        self._walls: dict[int, WallSegment] = {}  # PyBullet body id -> wall
        self._touching_wall_ids: set[int] = set()

    def build(self, maze: MazeGrid, config: TrainEnvConfig, params: EpisodeParams) -> None:
        """Create the plate, the walls of the maze and the ball for a new episode."""
        pybullet.resetSimulation(physicsClientId=self._client)
        pybullet.setTimeStep(1.0 / PHYSICS_HZ, physicsClientId=self._client)
        pybullet.setPhysicsEngineParameter(restitutionVelocityThreshold=RESTITUTION_VELOCITY_THRESHOLD_M_S,
                                           physicsClientId=self._client)
        self.set_tilt(0.0, 0.0)
        self._add_plate(config.plate_width_mm, config.plate_height_mm)
        self._walls = {self._add_wall(wall, maze): wall for wall in _wall_segments(maze)}
        self._ball_radius_mm = maze.ball_diameter_mm / 2.0
        self._ball_id = self._add_ball(self._ball_radius_mm, config.ball_mass_g, params)
        self._touching_wall_ids = set()

    def close(self) -> None:
        """End the PyBullet connection of this environment; a second call does nothing."""
        if pybullet.isConnected(physicsClientId=self._client):
            pybullet.disconnect(physicsClientId=self._client)

    def place_ball(self, x_mm: float, y_mm: float) -> None:
        """Put the ball at rest on the plate at (x_mm, y_mm)."""
        position_m = _to_m([x_mm, y_mm, self._ball_radius_mm])
        pybullet.resetBasePositionAndOrientation(self._ball_id, position_m, NO_ROTATION, physicsClientId=self._client)
        pybullet.resetBaseVelocity(self._ball_id, AT_REST, AT_REST, physicsClientId=self._client)

    def set_tilt(self, tilt_x_deg: float, tilt_y_deg: float) -> None:
        """Tilt the plate (D4 signs) by turning gravity."""
        gravity_m_s2 = gravity_in_plate_frame_m_s2(tilt_x_deg, tilt_y_deg)
        pybullet.setGravity(*gravity_m_s2, physicsClientId=self._client)

    def step(self) -> list[tuple[WallSegment, np.ndarray]]:
        """One physics step of 1/PHYSICS_HZ s. Returns the walls the ball started to touch in this
        step, each with the ball velocity (mm/s) just before the contact."""
        velocity_before_mm_s = self.ball_velocity_mm_s()
        pybullet.stepSimulation(physicsClientId=self._client)
        touching_now = self._touching_walls()
        new_contacts = touching_now - self._touching_wall_ids
        self._touching_wall_ids = touching_now
        return [(self._walls[wall_id], velocity_before_mm_s) for wall_id in new_contacts]

    @property
    def walls(self) -> list[WallSegment]:
        """Every wall of the maze once, as built by build()."""
        return list(self._walls.values())

    def ball_position_mm(self) -> np.ndarray:
        """True ball centre (x, y) in the board frame, without noise."""
        position_m, _ = pybullet.getBasePositionAndOrientation(self._ball_id, physicsClientId=self._client)
        return np.array(position_m[:2]) * MM_PER_M

    def ball_velocity_mm_s(self) -> np.ndarray:
        """True ball velocity (vx, vy)."""
        velocity_m_s, _ = pybullet.getBaseVelocity(self._ball_id, physicsClientId=self._client)
        return np.array(velocity_m_s[:2]) * MM_PER_M

    def _touching_walls(self) -> set[int]:
        contacts = pybullet.getContactPoints(bodyA=self._ball_id, physicsClientId=self._client)
        other_body_index = 2  # PyBullet's contact point tuple: (flag, bodyA, bodyB, ...)
        return {contact[other_body_index] for contact in contacts if contact[other_body_index] in self._walls}

    def _add_plate(self, width_mm: float, height_mm: float) -> None:
        half_extents_mm = [width_mm / 2.0, height_mm / 2.0, PLATE_THICKNESS_MM / 2.0]
        centre_mm = [0.0, 0.0, -PLATE_THICKNESS_MM / 2.0]
        plate_id = self._add_static_box(half_extents_mm, centre_mm)
        self._set_contact(plate_id, STATIC_FRICTION, STATIC_ROLLING_FRICTION_M, PLATE_RESTITUTION)

    def _add_wall(self, wall: WallSegment, maze: MazeGrid) -> int:
        # A wall is one cell long plus its thickness, so walls meeting at a corner close it.
        length_mm = maze.cell_size_mm + maze.wall_thickness_mm
        if wall.is_along_x:
            along_x_mm, along_y_mm = length_mm, maze.wall_thickness_mm
        else:
            along_x_mm, along_y_mm = maze.wall_thickness_mm, length_mm
        half_extents_mm = [along_x_mm / 2.0, along_y_mm / 2.0, maze.wall_height_mm / 2.0]
        centre_mm = [wall.centre_x_mm, wall.centre_y_mm, maze.wall_height_mm / 2.0]
        wall_id = self._add_static_box(half_extents_mm, centre_mm)
        self._set_contact(wall_id, STATIC_FRICTION, STATIC_ROLLING_FRICTION_M, WALL_RESTITUTION)
        return wall_id

    def _add_static_box(self, half_extents_mm: list[float], centre_mm: list[float]) -> int:
        shape = pybullet.createCollisionShape(
            pybullet.GEOM_BOX, halfExtents=_to_m(half_extents_mm), physicsClientId=self._client)
        return pybullet.createMultiBody(
            baseMass=STATIC_MASS_KG, baseCollisionShapeIndex=shape, basePosition=_to_m(centre_mm),
            physicsClientId=self._client)

    def _add_ball(self, radius_mm: float, mass_g: float, params: EpisodeParams) -> int:
        shape = pybullet.createCollisionShape(
            pybullet.GEOM_SPHERE, radius=radius_mm / MM_PER_M, physicsClientId=self._client)
        ball_id = pybullet.createMultiBody(
            baseMass=mass_g / G_PER_KG, baseCollisionShapeIndex=shape, basePosition=_to_m([0.0, 0.0, radius_mm]),
            physicsClientId=self._client)
        # PyBullet's rolling friction is a lever arm in metres: rolling resistance × radius.
        rolling_friction_m = params.friction_coeff * radius_mm / MM_PER_M
        self._set_contact(ball_id, BALL_GRIP_FRICTION, rolling_friction_m, params.restitution)
        pybullet.changeDynamics(
            ball_id, BASE_LINK, linearDamping=NO_DAMPING, angularDamping=NO_DAMPING, physicsClientId=self._client)
        return ball_id

    def _set_contact(self, body_id: int, friction: float, rolling_friction_m: float, restitution: float) -> None:
        pybullet.changeDynamics(
            body_id, BASE_LINK, lateralFriction=friction, rollingFriction=rolling_friction_m,
            restitution=restitution, physicsClientId=self._client)


def gravity_in_plate_frame_m_s2(tilt_x_deg: float, tilt_y_deg: float) -> np.ndarray:
    """Gravity seen from a plate turned by tilt_x_deg about +y and by -tilt_y_deg about +x (D4).
    tilt_x_deg > 0 gives a +x component, so the ball rolls to +x; the same for y."""
    turn_about_y = _rotation_about_y(math.radians(tilt_x_deg))
    turn_about_x = _rotation_about_x(-math.radians(tilt_y_deg))
    plate_rotation = turn_about_y @ turn_about_x
    gravity_world_m_s2 = np.array([0.0, 0.0, -GRAVITY_M_S2])
    return plate_rotation.T @ gravity_world_m_s2


def _rotation_about_x(angle_rad: float) -> np.ndarray:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _rotation_about_y(angle_rad: float) -> np.ndarray:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _to_m(values_mm: list[float]) -> list[float]:
    return [value / MM_PER_M for value in values_mm]


def _wall_segments(maze: MazeGrid) -> list[WallSegment]:
    """Every wall of the maze once. An inner wall is flagged in both neighbouring cells (IF-04)."""
    segments: dict[tuple[bool, float, float], WallSegment] = {}
    for row, col in itertools.product(range(maze.rows), range(maze.cols)):
        for wall in _walls_of_cell(maze, row, col):
            segments[_wall_key(wall)] = wall
    return list(segments.values())


def _wall_key(wall: WallSegment) -> tuple[bool, float, float]:
    return (wall.is_along_x, round(wall.centre_x_mm, WALL_KEY_DECIMALS), round(wall.centre_y_mm, WALL_KEY_DECIMALS))


def _walls_of_cell(maze: MazeGrid, row: int, col: int) -> list[WallSegment]:
    flags = maze.walls[row][col]
    return [_wall_on_side(maze, row, col, side) for side, bit in WALL_BITS.items() if flags & bit]


def _wall_on_side(maze: MazeGrid, row: int, col: int, side: str) -> WallSegment:
    centre_x_mm, centre_y_mm = maze.cell_centre_mm(row, col)
    half_cell_mm = maze.cell_size_mm / 2.0
    offsets_mm = {
        NORTH: (0.0, half_cell_mm), EAST: (half_cell_mm, 0.0),
        SOUTH: (0.0, -half_cell_mm), WEST: (-half_cell_mm, 0.0),
    }
    offset_x_mm, offset_y_mm = offsets_mm[side]
    return WallSegment(side in (NORTH, SOUTH), centre_x_mm + offset_x_mm, centre_y_mm + offset_y_mm)
