"""ClipWriter: FrameGrabber's record mode (C.5)."""
from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

from vision.clip_format import (ARRIVAL_TIME_COLUMN, ARRIVAL_TIMES_FILE_NAME, FRAME_INDEX_COLUMN,
                                VIDEO_FILE_NAME, VIDEO_FOURCC)


class ClipWriter:
    """Saves frames and their arrival times to a clip folder, so tests can play them back."""

    def __init__(self, clip_dir: Path, fps_hz: float) -> None:
        clip_dir = Path(clip_dir)
        if (clip_dir / VIDEO_FILE_NAME).exists():
            raise FileExistsError(f"{clip_dir} already holds a clip; choose another folder")
        clip_dir.mkdir(parents=True, exist_ok=True)
        self._video_path = clip_dir / VIDEO_FILE_NAME
        self._fps_hz = fps_hz
        self._video: cv2.VideoWriter | None = None  # opened with the first frame, which gives the frame size
        self._times_file = open(clip_dir / ARRIVAL_TIMES_FILE_NAME, "w", newline="", encoding="utf-8")
        self._times = csv.writer(self._times_file)
        self._times.writerow([FRAME_INDEX_COLUMN, ARRIVAL_TIME_COLUMN])
        self._frame_count = 0

    def write(self, frame: np.ndarray, t_arrival_s: float) -> None:
        if self._video is None:
            self._video = self._open_video(frame)
        self._video.write(frame)
        self._times.writerow([self._frame_count, f"{t_arrival_s:.6f}"])
        self._frame_count += 1

    def close(self) -> None:
        if self._video is not None:
            self._video.release()
        self._times_file.close()

    def _open_video(self, frame: np.ndarray) -> cv2.VideoWriter:
        height_px, width_px = frame.shape[:2]
        is_color = frame.ndim == 3
        fourcc = cv2.VideoWriter_fourcc(*VIDEO_FOURCC)
        video = cv2.VideoWriter(str(self._video_path), fourcc, self._fps_hz, (width_px, height_px), is_color)
        if not video.isOpened():
            raise OSError(f"cannot write {self._video_path}")
        return video
