"""BoardCalibrator (C.5): finds the 4 ArUco markers and keeps the pixel -> board mapping.

The four markers sit on the corners of the maze plate, so they move with the plate: a point
mapped through the homography is a position in the board frame (D4) even when the plate is tilted.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from vision.config_file import ConfigError
from vision.vision_config import MARKER_COUNT, MarkerConfig, VisionConfig

HALF = 0.5
POINTS_PER_MARKER = 4

# OpenCV returns the corners of a marker as top-left, top-right, bottom-right, bottom-left of the
# printed marker. The markers are printed upright, so "up" is board +y and "right" is board +x.
# Each pair is the (x, y) direction of that corner from the marker centre.
MARKER_CORNER_DIRECTIONS = ((-1, 1), (1, 1), (1, -1), (-1, -1))

# C.8: when fewer than 4 markers are seen, the last homography is kept for a short time.
# STARTING VALUE (about 1 s at 30 fps), to be tuned in tests.
LAST_HOMOGRAPHY_HOLD_FRAMES = 30

# The camera height needs the focal length, which depends on the camera (D8 is open).
# STARTING VALUE until the camera is chosen; replace it with the measured field of view.
NOMINAL_HORIZONTAL_FOV_DEG = 60.0

CORNER_REFINEMENT = cv2.aruco.CORNER_REFINE_SUBPIX  # corner accuracy matters for the 3 mm target (C-R1)


class NotCalibratedError(RuntimeError):
    """There is no valid pixel -> board mapping: the markers are not (or no longer) seen."""


class BoardCalibrator:
    """Finds the ArUco markers in each frame and converts pixel positions to board positions in mm."""

    def __init__(self, config: VisionConfig) -> None:
        self._detector = _make_detector(config.marker_dictionary)
        self._board_corners_mm = {
            marker.marker_id: _board_corners_mm(marker, config.marker_size_mm) for marker in config.markers
        }
        self._homography: np.ndarray | None = None
        self._frames_without_all_markers = 0
        self._markers_found = 0
        self._reprojection_error_mm = 0.0
        self._camera_height_mm: float | None = None

    @property
    def is_calibrated(self) -> bool:
        """True while the homography is valid: all markers seen now, or lost only for a short time."""
        return self._homography is not None and self._frames_without_all_markers <= LAST_HOMOGRAPHY_HOLD_FRAMES

    @property
    def markers_found(self) -> int:
        """Configured markers seen in the last frame (0-4)."""
        return self._markers_found

    @property
    def reprojection_error_mm(self) -> float:
        """Quality of the last calibrate() run; 0.0 before the first run."""
        return self._reprojection_error_mm

    @property
    def camera_height_mm(self) -> float | None:
        """Camera height from the last successful calibrate() (for the parallax correction); None before that."""
        return self._camera_height_mm

    def update(self, frame: np.ndarray) -> bool:
        """Look for the markers in this frame and refresh the homography; True if it is valid."""
        self._register_markers(self._detect_markers(frame))
        return self.is_calibrated

    def to_board_mm(self, u_px: float, v_px: float) -> tuple[float, float]:
        """Board position (x_mm, y_mm) of an image pixel; raises NotCalibratedError without a valid homography."""
        if not self.is_calibrated:
            raise NotCalibratedError("the markers are not seen, so there is no pixel -> board mapping")
        pixel = np.array([[[u_px, v_px]]], dtype=np.float64)
        x_mm, y_mm = cv2.perspectiveTransform(pixel, self._homography)[0, 0]
        return float(x_mm), float(y_mm)

    def calibrate(self, frame: np.ndarray) -> tuple[float, float]:
        """calibrate_camera (plate flat): returns (reprojection_error_mm, camera_height_mm).

        Raises NotCalibratedError when not all markers are seen."""
        detected = self._detect_markers(frame)
        if len(detected) != MARKER_COUNT:
            raise NotCalibratedError(f"calibrate_camera needs {MARKER_COUNT} markers, {len(detected)} seen")
        self._register_markers(detected)
        image_points, board_points = self._matching_points(detected)
        self._reprojection_error_mm = _reprojection_error_mm(self._homography, image_points, board_points)
        self._camera_height_mm = _camera_height_mm(frame.shape, image_points, board_points)
        return self._reprojection_error_mm, self._camera_height_mm

    def _register_markers(self, detected: dict[int, np.ndarray]) -> None:
        self._markers_found = len(detected)
        if len(detected) == MARKER_COUNT:
            image_points, board_points = self._matching_points(detected)
            self._homography, _ = cv2.findHomography(image_points, board_points)
            self._frames_without_all_markers = 0
        else:
            self._frames_without_all_markers += 1

    def _detect_markers(self, frame: np.ndarray) -> dict[int, np.ndarray]:
        """Image corners (4 x 2) of every configured marker seen in the frame, by marker ID."""
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return {}
        seen = {int(marker_id): marker.reshape(POINTS_PER_MARKER, 2) for marker, marker_id in zip(corners, ids.flatten())}
        return {marker_id: seen[marker_id] for marker_id in self._board_corners_mm if marker_id in seen}

    def _matching_points(self, detected: dict[int, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        """Image corners and their known board positions, in the same order (4 per marker)."""
        marker_ids = sorted(detected)
        image_points = np.vstack([detected[marker_id] for marker_id in marker_ids])
        board_points = np.vstack([self._board_corners_mm[marker_id] for marker_id in marker_ids])
        return image_points, board_points


def _make_detector(dictionary_name: str) -> cv2.aruco.ArucoDetector:
    dictionary_id = getattr(cv2.aruco, dictionary_name, None)
    if not isinstance(dictionary_id, int):
        raise ConfigError(f"marker_dictionary {dictionary_name!r} is not an OpenCV ArUco dictionary")
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = CORNER_REFINEMENT
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(dictionary_id), parameters)


def _board_corners_mm(marker: MarkerConfig, marker_size_mm: float) -> np.ndarray:
    """The 4 corners of a marker in the board frame, in OpenCV's corner order."""
    half_size_mm = marker_size_mm * HALF
    return np.array(
        [[marker.centre_x_mm + x_direction * half_size_mm, marker.centre_y_mm + y_direction * half_size_mm]
         for x_direction, y_direction in MARKER_CORNER_DIRECTIONS],
        dtype=np.float64,
    )


def _reprojection_error_mm(homography: np.ndarray, image_points: np.ndarray, board_points: np.ndarray) -> float:
    """Root mean square distance between the mapped marker corners and their known board positions."""
    mapped_points = cv2.perspectiveTransform(image_points.reshape(-1, 1, 2), homography).reshape(-1, 2)
    distances_mm = np.linalg.norm(mapped_points - board_points, axis=1)
    return float(math.sqrt(np.mean(distances_mm ** 2)))


def _camera_height_mm(frame_shape: tuple, image_points: np.ndarray, board_points: np.ndarray) -> float:
    """Distance of the camera from the plate, for the parallax correction (needs NOMINAL_HORIZONTAL_FOV_DEG)."""
    height_px, width_px = frame_shape[:2]
    focal_px = (width_px * HALF) / math.tan(math.radians(NOMINAL_HORIZONTAL_FOV_DEG) * HALF)
    camera_matrix = np.array([[focal_px, 0.0, width_px * HALF], [0.0, focal_px, height_px * HALF], [0.0, 0.0, 1.0]])
    plate_points = np.hstack([board_points, np.zeros((len(board_points), 1))])
    is_solved, rotation_vector, translation_vector = cv2.solvePnP(
        plate_points, image_points, camera_matrix, None, flags=cv2.SOLVEPNP_IPPE)
    if not is_solved:
        raise NotCalibratedError("the camera height could not be estimated from the markers")
    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    camera_position_mm = -rotation_matrix.T @ translation_vector
    return abs(float(camera_position_mm[2, 0]))
