"""TiltActuator: the plate follows the commanded tilt like the real platform (IF-08).

A command takes effect latency_ms after it was sent, and the plate then turns towards it at
most max_tilt_speed_deg_s. latency_ms is the camera + Vision + bus + serial delay; the motor's
own time is modelled by the speed limit (IF-06, Delay budget).
"""
from __future__ import annotations

from collections import deque

import numpy as np


class TiltActuator:
    """Plate tilt (x, y) in deg, following the commands after the delay and within the speed limit."""

    def __init__(self, max_tilt_speed_deg_s: float, latency_s: float) -> None:
        self._max_tilt_speed_deg_s = max_tilt_speed_deg_s
        self._latency_s = latency_s
        self._pending: deque[tuple[float, np.ndarray]] = deque()  # (time it takes effect, target)
        self._target_deg = np.zeros(2)  # the latest command that has arrived
        self.tilt_deg = np.zeros(2)  # where the plate is now, after the delay and the speed limit

    def command(self, now_s: float, target_tilt_deg: np.ndarray) -> None:
        """A new target tilt, sent at now_s."""
        self._pending.append((now_s + self._latency_s, np.array(target_tilt_deg, dtype=float)))

    def advance(self, now_s: float, dt_s: float) -> None:
        """Move the plate for dt_s; now_s is the time at the end of this interval."""
        self._take_arrived_commands(now_s)
        largest_change_deg = self._max_tilt_speed_deg_s * dt_s
        change_deg = np.clip(self._target_deg - self.tilt_deg, -largest_change_deg, largest_change_deg)
        self.tilt_deg = self.tilt_deg + change_deg

    def _take_arrived_commands(self, now_s: float) -> None:
        """Commands whose delay has passed reach the platform; the newest of them is the target."""
        while self._pending and self._pending[0][0] <= now_s:
            _, self._target_deg = self._pending.popleft()
