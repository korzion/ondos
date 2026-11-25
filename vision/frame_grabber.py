"""FrameGrabber (C.5): reads frames from the USB camera or from a recorded clip."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import cv2
import numpy as np

from shared.bus import now_s
from vision.clip_reader import ClipReader
from vision.clip_writer import ClipWriter

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
# DirectShow on Windows (the default backend there opens slowly and ignores manual exposure); V4L2 on Linux.
CAMERA_BACKEND = cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_V4L2
# CAP_PROP_AUTO_EXPOSURE value that switches the camera to manual exposure; each backend uses its own value.
MANUAL_EXPOSURE_MODE = 0.25 if IS_WINDOWS else 1


class FrameGrabber:
    """Reads frames from a frame source (USB camera or recorded clip); in record mode it also saves
    every frame with its arrival time, so tests can play it back."""

    def __init__(self, frame_width_px: int, frame_height_px: int, camera_fps_hz: float) -> None:
        self._frame_width_px = frame_width_px
        self._frame_height_px = frame_height_px
        self._camera_fps_hz = camera_fps_hz
        self._camera: cv2.VideoCapture | None = None
        self._clip: ClipReader | None = None
        self._recorder: ClipWriter | None = None

    def open(self, camera_index: int) -> bool:
        """Open a USB camera (the previous source is closed); False if it cannot be opened."""
        self._close_source()
        camera = cv2.VideoCapture(camera_index, CAMERA_BACKEND)
        if not camera.isOpened():
            camera.release()
            return False
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, self._frame_width_px)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self._frame_height_px)
        camera.set(cv2.CAP_PROP_FPS, self._camera_fps_hz)
        self._camera = camera
        return True

    def open_clip(self, clip_dir: Path) -> bool:
        """Play a recorded clip folder instead of the camera; False if it cannot be read."""
        self._close_source()
        try:
            self._clip = ClipReader(clip_dir)
        except (OSError, KeyError, ValueError) as error:
            log.error("cannot open clip %s: %s", clip_dir, error)
            return False
        return True

    def read(self) -> tuple[np.ndarray, float] | None:
        """The next frame and its laptop arrival time, or None if no frame came."""
        sample = self._read_source()
        if sample is not None and self._recorder is not None:
            self._recorder.write(*sample)
        return sample

    def set_exposure(self, exposure: float, gain: float) -> None:
        """Lock the camera exposure and gain (raw OpenCV values); no effect on a clip."""
        if self._camera is None:
            return
        self._camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, MANUAL_EXPOSURE_MODE)
        self._camera.set(cv2.CAP_PROP_EXPOSURE, exposure)
        self._camera.set(cv2.CAP_PROP_GAIN, gain)

    def is_clip_finished(self) -> bool:
        return self._clip is not None and self._clip.is_finished()

    def start_recording(self, clip_dir: Path) -> None:
        """Record mode: save every frame read from now on to clip_dir."""
        self.stop_recording()
        self._recorder = ClipWriter(clip_dir, self._camera_fps_hz)

    def stop_recording(self) -> None:
        if self._recorder is not None:
            self._recorder.close()
            self._recorder = None

    def close(self) -> None:
        self._close_source()
        self.stop_recording()

    def _read_source(self) -> tuple[np.ndarray, float] | None:
        if self._clip is not None:
            return self._clip.read()
        if self._camera is not None:
            return self._read_camera()
        return None

    def _read_camera(self) -> tuple[np.ndarray, float] | None:
        # The arrival time is taken right after grab(), before decoding, so it is the time the frame
        # reached the laptop (frame_age_ms, IF-04).
        if not self._camera.grab():
            return None
        t_arrival_s = now_s()
        is_decoded, frame = self._camera.retrieve()
        return (frame, t_arrival_s) if is_decoded else None

    def _close_source(self) -> None:
        if self._camera is not None:
            self._camera.release()
            self._camera = None
        if self._clip is not None:
            self._clip.close()
            self._clip = None
