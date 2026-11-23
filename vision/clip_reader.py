"""ClipReader: plays a recorded clip as FrameGrabber's frame source (C.5)."""
from __future__ import annotations

import csv
import time
from pathlib import Path

import cv2
import numpy as np

from shared.bus import now_s
from vision.clip_format import ARRIVAL_TIME_COLUMN, ARRIVAL_TIMES_FILE_NAME, VIDEO_FILE_NAME


class ClipReader:
    """Gives the frames of a clip folder in real time, with the recorded gaps between frames.

    The arrival time of a frame is the playback start plus its recorded offset, so the time
    between two frames is the same as when the clip was recorded.
    """

    def __init__(self, clip_dir: Path) -> None:
        clip_dir = Path(clip_dir)
        self._arrival_times_s = _read_arrival_times(clip_dir / ARRIVAL_TIMES_FILE_NAME)
        self._video = cv2.VideoCapture(str(clip_dir / VIDEO_FILE_NAME))
        if not self._video.isOpened():
            raise FileNotFoundError(f"cannot open {clip_dir / VIDEO_FILE_NAME}")
        self._next_index = 0
        self._playback_start_s: float | None = None

    def read(self) -> tuple[np.ndarray, float] | None:
        """The next frame and its arrival time, or None at the end of the clip."""
        if self.is_finished():
            return None
        is_read, frame = self._video.read()
        if not is_read:  # the video has fewer frames than the arrival-times file
            self._next_index = len(self._arrival_times_s)
            return None
        t_arrival_s = self._playback_time_s(self._next_index)
        _wait_until(t_arrival_s)
        self._next_index += 1
        return frame, t_arrival_s

    def is_finished(self) -> bool:
        return self._next_index >= len(self._arrival_times_s)

    def close(self) -> None:
        self._video.release()

    def _playback_time_s(self, frame_index: int) -> float:
        if self._playback_start_s is None:
            self._playback_start_s = now_s()
        recorded_offset_s = self._arrival_times_s[frame_index] - self._arrival_times_s[0]
        return self._playback_start_s + recorded_offset_s


def _read_arrival_times(path: Path) -> list[float]:
    with open(path, newline="", encoding="utf-8") as times_file:
        return [float(row[ARRIVAL_TIME_COLUMN]) for row in csv.DictReader(times_file)]


def _wait_until(t_s: float) -> None:
    delay_s = t_s - now_s()
    if delay_s > 0:
        time.sleep(delay_s)
