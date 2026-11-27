"""BallTracker (C.5): finds the ball by colour, corrects the parallax and filters position and speed."""
from __future__ import annotations

import math

import cv2
import numpy as np

from shared.ball_filter import BallFilter
from vision.ball_state import BallState
from vision.board_calibrator import BoardCalibrator
from vision.vision_variables import VisionVariables

LOWEST_COLOUR_VARIABLES = ("ball_h_min", "ball_s_min", "ball_v_min")
HIGHEST_COLOUR_VARIABLES = ("ball_h_max", "ball_s_max", "ball_v_max")

# ASSUMPTION (#47): the ball is found by colour and size (C.5, C.8), but no size limit is given. A blob is the ball
# when its diameter differs from ball_diameter_mm by at most this part of it; of several such blobs the one nearest
# to the ball size is taken. STARTING VALUE, to be tuned in tests.
BALL_SIZE_TOLERANCE = 0.5


class BallTracker:
    """Finds the ball in each frame and gives its state in the board frame."""

    def __init__(self, variables: VisionVariables, calibrator: BoardCalibrator) -> None:
        self._variables = variables
        self._calibrator = calibrator
        # ASSUMPTION (#47): C.7 uses a new ball_diameter_mm from the next read_maze. Until MazeReader (#48) is
        # connected, the value is read once, at the start.
        self._ball_diameter_mm = variables.get("ball_diameter_mm")
        self._filter = BallFilter(variables.get("filter_noise"), variables.get("lost_timeout_ms"))

    def update(self, frame: np.ndarray, t_s: float) -> BallState:
        """Ball state for the frame taken at t_s. The calibrator must have seen this frame before."""
        # ASSUMPTION (#47): meas_x_mm and meas_y_mm (IF-04: the unfiltered measurement) are parallax corrected, like
        # x_mm and y_mm: they are what the filter gets.
        meas_x_mm, meas_y_mm = self._measure(frame)
        self._use_live_filter_settings()
        estimate = self._filter.update(meas_x_mm, meas_y_mm, t_s)
        return BallState(*estimate, meas_x_mm, meas_y_mm)

    def _use_live_filter_settings(self) -> None:
        # The variables change on the bus thread and the filter has no lock, so they are copied here, in update().
        self._filter.filter_noise = self._variables.get("filter_noise")
        self._filter.lost_timeout_ms = self._variables.get("lost_timeout_ms")

    def _measure(self, frame: np.ndarray) -> tuple[float, float] | tuple[None, None]:
        """Board position of the ball in this frame; (None, None) when no blob has the ball colour and size (C.8)."""
        if not self._calibrator.is_calibrated:
            return None, None  # without the pixel -> board mapping neither the size nor the position is known
        ball_centre_px = self._find_ball_px(frame)
        if ball_centre_px is None:
            return None, None
        return self._correct_parallax(*self._calibrator.to_board_mm(*ball_centre_px))

    def _correct_parallax(self, seen_x_mm: float, seen_y_mm: float) -> tuple[float, float]:
        """Board position under the ball centre, from the plate position where the camera sees that centre."""
        camera_height_mm = self._calibrator.camera_height_mm
        if camera_height_mm is None:  # calibrate_camera has not run yet
            return seen_x_mm, seen_y_mm
        # ASSUMPTION (#47): the camera is above the board origin (C.4: fixed above the maze centre) and the plate is
        # level. The ball centre is half a diameter above the plate, so it is seen further from the origin than it is.
        ball_centre_height_mm = self._ball_diameter_mm / 2
        scale = (camera_height_mm - ball_centre_height_mm) / camera_height_mm
        return seen_x_mm * scale, seen_y_mm * scale

    def _find_ball_px(self, frame: np.ndarray) -> tuple[float, float] | None:
        """Image centre of the ball-coloured blob nearest to the ball size; None when no blob is near enough."""
        ball_centre_px = None
        smallest_size_error_mm = BALL_SIZE_TOLERANCE * self._ball_diameter_mm
        for contour in self._ball_coloured_contours(frame):
            moments = cv2.moments(contour)
            area_px2 = moments["m00"]
            if area_px2 <= 0.0:  # a single pixel or a line has no area and no centre
                continue
            centre_px = (moments["m10"] / area_px2, moments["m01"] / area_px2)
            size_error_mm = abs(self._diameter_mm(centre_px, area_px2) - self._ball_diameter_mm)
            if size_error_mm <= smallest_size_error_mm:
                ball_centre_px, smallest_size_error_mm = centre_px, size_error_mm
        return ball_centre_px

    def _diameter_mm(self, centre_px: tuple[float, float], area_px2: float) -> float:
        """Diameter on the board of a round blob with this image centre and area."""
        u_px, v_px = centre_px
        radius_px = math.sqrt(area_px2 / math.pi)
        return math.dist(self._calibrator.to_board_mm(u_px - radius_px, v_px),
                         self._calibrator.to_board_mm(u_px + radius_px, v_px))

    def _ball_coloured_contours(self, frame: np.ndarray) -> tuple[np.ndarray, ...]:
        """Outlines of the image regions whose colour is inside the ball colour thresholds (C.7)."""
        lowest_hsv = np.array([self._variables.get(name) for name in LOWEST_COLOUR_VARIABLES], dtype=np.uint8)
        highest_hsv = np.array([self._variables.get(name) for name in HIGHEST_COLOUR_VARIABLES], dtype=np.uint8)
        mask = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), lowest_hsv, highest_hsv)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return contours
