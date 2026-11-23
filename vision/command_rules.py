"""When Vision accepts a cs/command (IF-04 vision/maze rules, IF-07 command table)."""
from __future__ import annotations

from shared import topics as T
from shared.bus import age_s

MS_PER_S = 1000.0

# Game states in which each Vision command is accepted.
VISION_COMMAND_STATES = {
    "read_maze": frozenset({"setup", "ready", "paused"}),
    "calibrate_camera": frozenset({"setup", "ready"}),
}


def is_vision_command(cmd: str) -> bool:
    """True for the cs/command commands that Vision acts on."""
    return cmd in VISION_COMMAND_STATES


def is_command_allowed(cmd: str, game_state: dict | None, now_s: float) -> bool:
    """Whether Vision runs cmd now. Without a fresh game/state Vision accepts both commands
    (IF-05 game/state readers: "Vision: keep tracking; accept read_maze / calibrate_camera")."""
    if game_state is None or _is_stale(game_state, now_s):
        return True
    return game_state["state"] in VISION_COMMAND_STATES[cmd]


def _is_stale(game_state: dict, now_s: float) -> bool:
    return age_s(game_state, now_s) * MS_PER_S > T.GAME_STATE_MAX_AGE_MS
