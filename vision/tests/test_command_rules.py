import pytest

from shared import topics as T
from vision.command_rules import VISION_COMMAND_STATES, is_command_allowed, is_vision_command
from vision.tests.message_helpers import with_envelope

NOW_S = 1_000_000.0
FRESH_AGE_S = 0.05
STALE_AGE_S = T.GAME_STATE_MAX_AGE_MS / 1000.0 + 0.1

# Expected from the design document (IF-07 command table), written out independently of the code.
EXPECTED_STATES = {
    "read_maze": {"setup", "ready", "paused"},
    "calibrate_camera": {"setup", "ready"},
}


def game_state(state: str, age_s: float) -> dict:
    fields = {"state": state, "mode": "glove", "game_id": None, "maze_id": None, "elapsed_s": 0.0, "cell": None,
              "distance_to_exit_cells": None, "progress_pct": 0.0, "result": "none"}
    return with_envelope(T.GAME_STATE, fields, writer="game_manager", timestamp_s=NOW_S - age_s)


def test_rule_names_come_from_the_shared_interfaces():
    assert set(VISION_COMMAND_STATES) <= set(T.COMMAND_VALUES)
    for states in VISION_COMMAND_STATES.values():
        assert states <= set(T.STATE_VALUES)


@pytest.mark.parametrize("cmd", sorted(EXPECTED_STATES))
@pytest.mark.parametrize("state", T.STATE_VALUES)
def test_fresh_game_state_decides(cmd, state):
    assert is_command_allowed(cmd, game_state(state, FRESH_AGE_S), NOW_S) == (state in EXPECTED_STATES[cmd])


@pytest.mark.parametrize("cmd", sorted(EXPECTED_STATES))
def test_without_game_state_both_commands_are_accepted(cmd):
    assert is_command_allowed(cmd, None, NOW_S)


@pytest.mark.parametrize("cmd", sorted(EXPECTED_STATES))
def test_stale_game_state_counts_as_missing(cmd):
    assert is_command_allowed(cmd, game_state("playing", STALE_AGE_S), NOW_S)


def test_only_vision_commands_are_vision_commands():
    assert {cmd for cmd in T.COMMAND_VALUES if is_vision_command(cmd)} == set(EXPECTED_STATES)
