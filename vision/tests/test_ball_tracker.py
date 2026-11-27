"""Unit tests for BallTracker, on synthetic frames: the markers and a ball-coloured disc at a known board position."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from vision.ball_state import BallState
from vision.ball_tracker import BallTracker
from vision.board_calibrator import BoardCalibrator
from vision.tests.test_board_calibrator import PIXELS_PER_MM, board_to_pixel_matrix, draw_frame, pixel_of
from vision.vision_config import VisionConfig, load_vision_config
from vision.vision_variables import VisionVariables

BALL_HSV = (15, 200, 150)  # orange, in OpenCV units (H 0-179, S and V 0-255)
# The saturation and value ranges differ, so that the ball is not found when the two are mixed up.
BALL_THRESHOLDS = {"ball_h_min": 5, "ball_h_max": 25, "ball_s_min": 160, "ball_s_max": 240,
                   "ball_v_min": 110, "ball_v_max": 190}
# Each colour is outside the thresholds in one channel only.
OTHER_COLOURS_HSV = {"hue below": (0, 200, 150), "hue above": (40, 200, 150),
                     "saturation below": (15, 120, 150), "saturation above": (15, 255, 150),
                     "value below": (15, 200, 70), "value above": (15, 200, 230)}
BALL_DIAMETER_MM = 12.0  # the default of ball_diameter_mm
SUBPIXEL_SHIFT = 4  # the disc is drawn with 1/16 pixel steps, so its centre is not rounded to a pixel
T_S = 10.0
POSITION_TOLERANCE_MM = 0.5


@pytest.fixture(scope="module")
def config() -> VisionConfig:
    return load_vision_config()


def ball_variables() -> VisionVariables:
    variables = VisionVariables.load()
    variables.apply(BALL_THRESHOLDS)
    return variables


def bgr_of(hsv: tuple[int, int, int]) -> tuple[int, ...]:
    pixel = np.array([[hsv]], dtype=np.uint8)
    return tuple(int(channel) for channel in cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0, 0])


def scene(config: VisionConfig, *discs: tuple[float, float, float], disc_hsv: tuple = BALL_HSV) -> np.ndarray:
    """A colour frame, seen from above, with the markers and a disc for each (x_mm, y_mm, diameter_mm)."""
    matrix = board_to_pixel_matrix()
    frame = cv2.cvtColor(draw_frame(config, matrix), cv2.COLOR_GRAY2BGR)
    disc_bgr = bgr_of(disc_hsv)
    steps = 2 ** SUBPIXEL_SHIFT
    for x_mm, y_mm, diameter_mm in discs:
        u_px, v_px = pixel_of(matrix, x_mm, y_mm)
        cv2.circle(frame, (round(u_px * steps), round(v_px * steps)), round(diameter_mm * PIXELS_PER_MM / 2 * steps),
                   disc_bgr, thickness=cv2.FILLED, shift=SUBPIXEL_SHIFT)
    return frame


def track(tracker: BallTracker, calibrator: BoardCalibrator, frame: np.ndarray) -> BallState:
    """One frame as VisionNode handles it: the calibration first, then the ball."""
    calibrator.update(frame)
    return tracker.update(frame, T_S)


def measurement(config: VisionConfig, frame: np.ndarray) -> tuple[float | None, float | None]:
    """What a new tracker measures in one frame."""
    calibrator = BoardCalibrator(config)
    state = track(BallTracker(ball_variables(), calibrator), calibrator, frame)
    return state.meas_x_mm, state.meas_y_mm


@pytest.mark.parametrize("x_mm, y_mm", [(0.0, 0.0), (50.0, -30.0), (-83.0, 61.5)])
def test_ball_is_measured_at_its_board_position(config, x_mm, y_mm):
    frame = scene(config, (x_mm, y_mm, BALL_DIAMETER_MM))
    assert measurement(config, frame) == pytest.approx((x_mm, y_mm), abs=POSITION_TOLERANCE_MM)


def test_no_measurement_without_a_ball(config):
    assert measurement(config, scene(config)) == (None, None)


@pytest.mark.parametrize("disc_hsv", OTHER_COLOURS_HSV.values(), ids=OTHER_COLOURS_HSV.keys())
def test_a_disc_of_another_colour_is_not_the_ball(config, disc_hsv):
    frame = scene(config, (0.0, 0.0, BALL_DIAMETER_MM), disc_hsv=disc_hsv)
    assert measurement(config, frame) == (None, None)


@pytest.mark.parametrize("diameter_mm", [4.0, 20.0])
def test_a_blob_of_the_wrong_size_is_not_the_ball(config, diameter_mm):
    assert measurement(config, scene(config, (30.0, 30.0, diameter_mm))) == (None, None)


@pytest.mark.parametrize("diameter_mm", [8.0, 16.0])
def test_a_blob_near_the_ball_size_is_the_ball(config, diameter_mm):
    frame = scene(config, (30.0, 30.0, diameter_mm))
    assert measurement(config, frame) == pytest.approx((30.0, 30.0), abs=POSITION_TOLERANCE_MM)


@pytest.mark.parametrize("ball_y_mm, other_y_mm", [(-40.0, 40.0), (40.0, -40.0)])
def test_the_blob_nearest_to_the_ball_size_is_the_ball(config, ball_y_mm, other_y_mm):
    frame = scene(config, (20.0, ball_y_mm, BALL_DIAMETER_MM), (20.0, other_y_mm, 16.0))
    assert measurement(config, frame) == pytest.approx((20.0, ball_y_mm), abs=POSITION_TOLERANCE_MM)


def test_a_single_pixel_of_the_ball_colour_is_ignored(config):
    frame = scene(config, (0.0, 0.0, BALL_DIAMETER_MM))
    frame[100, 320] = bgr_of(BALL_HSV)
    assert measurement(config, frame) == pytest.approx((0.0, 0.0), abs=POSITION_TOLERANCE_MM)


def test_colour_thresholds_are_live(config):
    """With the default thresholds every pixel has the ball colour, so no blob has the ball size."""
    variables, calibrator = VisionVariables.load(), BoardCalibrator(config)
    tracker = BallTracker(variables, calibrator)
    frame = scene(config, (0.0, 0.0, BALL_DIAMETER_MM))
    assert track(tracker, calibrator, frame).meas_x_mm is None
    variables.apply(BALL_THRESHOLDS)
    assert track(tracker, calibrator, frame).meas_x_mm == pytest.approx(0.0, abs=POSITION_TOLERANCE_MM)


def test_ball_diameter_is_read_once_at_the_start(config):
    variables, calibrator = ball_variables(), BoardCalibrator(config)
    tracker = BallTracker(variables, calibrator)
    variables.apply({"ball_diameter_mm": 3 * BALL_DIAMETER_MM})
    state = track(tracker, calibrator, scene(config, (0.0, 0.0, BALL_DIAMETER_MM)))
    assert state.meas_x_mm == pytest.approx(0.0, abs=POSITION_TOLERANCE_MM)


def test_no_measurement_while_the_markers_are_not_seen(config):
    """Without the pixel -> board mapping the ball has no board position; the frame loop must not stop."""
    tracker = BallTracker(ball_variables(), BoardCalibrator(config))
    state = tracker.update(scene(config, (0.0, 0.0, BALL_DIAMETER_MM)), T_S)
    assert (state.meas_x_mm, state.meas_y_mm) == (None, None)
