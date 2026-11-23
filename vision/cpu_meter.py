"""CpuMeter: CPU used by the Vision process, for vision/status cpu_pct (IF-04)."""
from __future__ import annotations

import os
import time

MAX_PCT = 100.0


class CpuMeter:
    """CPU time used by this process since the last sample, as a share of all CPU cores (0-100 %)."""

    def __init__(self) -> None:
        self._cpu_count = os.cpu_count() or 1
        self._last_cpu_s = time.process_time()
        self._last_wall_s = time.perf_counter()

    def sample_pct(self) -> float:
        cpu_s, wall_s = time.process_time(), time.perf_counter()
        used_cpu_s = cpu_s - self._last_cpu_s
        elapsed_wall_s = wall_s - self._last_wall_s
        self._last_cpu_s, self._last_wall_s = cpu_s, wall_s
        if elapsed_wall_s <= 0:
            return 0.0
        return min(MAX_PCT, MAX_PCT * used_cpu_s / (elapsed_wall_s * self._cpu_count))
