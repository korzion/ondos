"""FrameStats: frame rate and frame age for vision/status (IF-04)."""
from __future__ import annotations

from collections import deque

STATS_WINDOW_S = 1.0  # vision/status reports the frame rate now and the average frame age over the last second
MS_PER_S = 1000.0


class FrameStats:
    """Frame rate and mean frame age over the last STATS_WINDOW_S, from the frames' arrival times."""

    def __init__(self) -> None:
        self._frames: deque[tuple[float, float]] = deque()  # (t_arrival_s, frame_age_ms)

    def record_frame(self, t_arrival_s: float, t_done_s: float) -> None:
        """A frame that arrived at t_arrival_s and was finished at t_done_s (laptop clock)."""
        self._frames.append((t_arrival_s, frame_age_ms(t_arrival_s, t_done_s)))
        self._drop_frames_before(t_arrival_s - STATS_WINDOW_S)

    def fps_hz(self, now_s: float) -> float:
        self._drop_frames_before(now_s - STATS_WINDOW_S)
        return len(self._frames) / STATS_WINDOW_S

    def mean_frame_age_ms(self, now_s: float) -> float:
        self._drop_frames_before(now_s - STATS_WINDOW_S)
        if not self._frames:
            return 0.0
        return sum(frame_age_ms for _, frame_age_ms in self._frames) / len(self._frames)

    def _drop_frames_before(self, oldest_s: float) -> None:
        while self._frames and self._frames[0][0] <= oldest_s:
            self._frames.popleft()


def frame_age_ms(t_arrival_s: float, t_now_s: float) -> float:
    """Time since a frame arrived at the laptop (IF-04 frame_age_ms); never below 0."""
    return max(0.0, (t_now_s - t_arrival_s) * MS_PER_S)
