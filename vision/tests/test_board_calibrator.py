"""Unit tests for BoardCalibrator, on synthetic frames: the 4 markers drawn through a known plate -> image mapping."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from vision.board_calibrator import (
    LAST_HOMOGRAPHY_HOLD_FRAMES,
    NOMINAL_HORIZONTAL_FOV_DEG,
    BoardCalibrator,
    NotCalibratedError,
)
from vision.vision_config import VisionConfig, load_vision_config

FRAME_WIDTH_PX = 640
FRAME_HEIGHT_PX = 480
PIXELS_PER_MM = 1.4
MARKER_PIXEL_SIZE = 100
WHITE = 255
POINT_TOLERANCE_MM = 0.5
HEIGHT_TOLERANCE_MM = 15.0


@pytest.fixture(scope="module")
def config() -> VisionConfig:
    return load_vision_config()


def board_to_pixel_matrix(offset_px: tuple[float, float] = (0.0, 0.0)) -> np.ndarray:
    """Top-down view: board +x is image right, board +y is image up, the board centre is the image centre."""
    return np.array([
        [PIXELS_PER_MM, 0.0, FRAME_WIDTH_PX / 2 + offset_px[0]],
        [0.0, -PIXELS_PER_MM, FRAME_HEIGHT_PX / 2 + offset_px[1]],
        [0.0, 0.0, 1.0],
    ])


def draw_frame(config: VisionConfig, board_to_pixel: np.ndarray, hidden_ids: tuple[int, ...] = ()) -> np.ndarray:
    """A grey frame with the configured markers drawn where board_to_pixel puts them."""
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, config.marker_dictionary))
    frame = np.full((FRAME_HEIGHT_PX, FRAME_WIDTH_PX), 128, dtype=np.uint8)
    half_mm = config.marker_size_mm / 2
    for marker in config.markers:
        if marker.marker_id in hidden_ids:
            continue
        image = cv2.aruco.generateImageMarker(dictionary, marker.marker_id, MARKER_PIXEL_SIZE)
        source = np.array([[0, 0], [MARKER_PIXEL_SIZE, 0], [MARKER_PIXEL_SIZE, MARKER_PIXEL_SIZE],
                           [0, MARKER_PIXEL_SIZE]], dtype=np.float32)
        board = np.array([[marker.centre_x_mm - half_mm, marker.centre_y_mm + half_mm],
                          [marker.centre_x_mm + half_mm, marker.centre_y_mm + half_mm],
                          [marker.centre_x_mm + half_mm, marker.centre_y_mm - half_mm],
                          [marker.centre_x_mm - half_mm, marker.centre_y_mm - half_mm]], dtype=np.float32)
        target = cv2.perspectiveTransform(board.reshape(-1, 1, 2), board_to_pixel).reshape(-1, 2)
        warp = cv2.getPerspectiveTransform(source, target.astype(np.float32))
        warped = cv2.warpPerspective(image, warp, (FRAME_WIDTH_PX, FRAME_HEIGHT_PX))
        mask = cv2.warpPerspective(np.full_like(image, WHITE), warp, (FRAME_WIDTH_PX, FRAME_HEIGHT_PX))
        frame[mask > 0] = warped[mask > 0]
    return frame


def pixel_of(board_to_pixel: np.ndarray, x_mm: float, y_mm: float) -> tuple[float, float]:
    u_px, v_px = cv2.perspectiveTransform(np.array([[[x_mm, y_mm]]], dtype=np.float64), board_to_pixel)[0, 0]
    return float(u_px), float(v_px)


def test_not_calibrated_before_any_frame(config):
    calibrator = BoardCalibrator(config)
    assert calibrator.is_calibrated is False and calibrator.markers_found == 0
    with pytest.raises(NotCalibratedError):
        calibrator.to_board_mm(10.0, 10.0)


def test_update_finds_all_markers(config):
    calibrator = BoardCalibrator(config)
    assert calibrator.update(draw_frame(config, board_to_pixel_matrix())) is True
    assert calibrator.markers_found == 4


def test_to_board_mm_inverts_the_known_mapping(config):
    matrix = board_to_pixel_matrix()
    calibrator = BoardCalibrator(config)
    calibrator.update(draw_frame(config, matrix))
    for x_mm, y_mm in [(0.0, 0.0), (50.0, -30.0), (-100.0, 80.0)]:
        got_x_mm, got_y_mm = calibrator.to_board_mm(*pixel_of(matrix, x_mm, y_mm))
        assert got_x_mm == pytest.approx(x_mm, abs=POINT_TOLERANCE_MM)
        assert got_y_mm == pytest.approx(y_mm, abs=POINT_TOLERANCE_MM)


def test_homography_follows_a_moved_plate(config):
    matrix = board_to_pixel_matrix(offset_px=(25.0, -15.0))
    calibrator = BoardCalibrator(config)
    calibrator.update(draw_frame(config, matrix))
    got_x_mm, got_y_mm = calibrator.to_board_mm(*pixel_of(matrix, 40.0, 20.0))
    assert (got_x_mm, got_y_mm) == pytest.approx((40.0, 20.0), abs=POINT_TOLERANCE_MM)


def test_last_homography_is_kept_briefly_then_dropped(config):
    matrix = board_to_pixel_matrix()
    calibrator = BoardCalibrator(config)
    calibrator.update(draw_frame(config, matrix))
    hidden = draw_frame(config, matrix, hidden_ids=(config.markers[0].marker_id,))
    for _ in range(LAST_HOMOGRAPHY_HOLD_FRAMES):
        assert calibrator.update(hidden) is True
    assert calibrator.markers_found == 3
    assert calibrator.update(hidden) is False
    with pytest.raises(NotCalibratedError):
        calibrator.to_board_mm(0.0, 0.0)


def test_markers_coming_back_restores_calibration(config):
    matrix = board_to_pixel_matrix()
    calibrator = BoardCalibrator(config)
    empty = np.full((FRAME_HEIGHT_PX, FRAME_WIDTH_PX), 128, dtype=np.uint8)
    for _ in range(LAST_HOMOGRAPHY_HOLD_FRAMES + 2):
        calibrator.update(empty)
    assert calibrator.is_calibrated is False
    assert calibrator.update(draw_frame(config, matrix)) is True


def test_calibrate_reports_a_small_error(config):
    calibrator = BoardCalibrator(config)
    error_mm, _ = calibrator.calibrate(draw_frame(config, board_to_pixel_matrix()))
    assert error_mm < POINT_TOLERANCE_MM
    assert calibrator.reprojection_error_mm == error_mm


def test_calibrate_needs_all_markers(config):
    frame = draw_frame(config, board_to_pixel_matrix(), hidden_ids=(config.markers[0].marker_id,))
    with pytest.raises(NotCalibratedError):
        BoardCalibrator(config).calibrate(frame)


def test_calibrate_measures_the_camera_height(config):
    """Pinhole camera: scale = focal / height, so the height is what produces PIXELS_PER_MM."""
    focal_px = (FRAME_WIDTH_PX / 2) / np.tan(np.radians(NOMINAL_HORIZONTAL_FOV_DEG) / 2)
    expected_height_mm = focal_px / PIXELS_PER_MM
    _, height_mm = BoardCalibrator(config).calibrate(draw_frame(config, board_to_pixel_matrix()))
    assert height_mm == pytest.approx(expected_height_mm, abs=HEIGHT_TOLERANCE_MM)


def test_colour_frames_are_accepted(config):
    gray = draw_frame(config, board_to_pixel_matrix())
    assert BoardCalibrator(config).update(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)) is True
