"""Plays timed lines ({"t_s", "topic", "msg"}, the format of the playback tool's fixture mode)."""
import bisect


class Player:
    """One file, played once from now_s, or in a loop on a clock shared by all looping players.

    A looping player created later joins at the right place of the loop, so a stream that is switched on
    in the middle of the demo stays in step with the others.
    """

    def __init__(self, lines: list[dict], loop_s: float | None, clock_start_s: float, now_s: float) -> None:
        self._lines = lines
        self._loop_s = loop_s
        self._origin_s = clock_start_s if loop_s else now_s
        elapsed_s = now_s - self._origin_s
        self._cycle = int(elapsed_s // loop_s) if loop_s else 0
        phase_s = elapsed_s - self._cycle * loop_s if loop_s else 0.0
        self._index = bisect.bisect_left([line["t_s"] for line in lines], phase_s)
        self._wrap_if_at_end()

    @property
    def is_finished(self) -> bool:
        return not self._lines or (self._loop_s is None and self._index >= len(self._lines))

    def due(self, now_s: float) -> list[dict]:
        """The lines whose time has come since the last call."""
        out = []
        while not self.is_finished and self._time_of_next_s() <= now_s:
            out.append(self._lines[self._index])
            self._index += 1
            self._wrap_if_at_end()
        return out

    def _time_of_next_s(self) -> float:
        return self._origin_s + self._cycle * (self._loop_s or 0.0) + self._lines[self._index]["t_s"]

    def _wrap_if_at_end(self) -> None:
        if self._loop_s and self._lines and self._index >= len(self._lines):
            self._index, self._cycle = 0, self._cycle + 1
