"""Tests of the fixture publisher's own behaviour: playing the data files and answering commands (issue #87).

TEST PLAN
The publisher has no maze or controller logic, so these tests only check that it plays the files and obeys
data/behaviour.json. No broker is needed. The content of the data files is checked in test_fixture_data.py.

1. Player      plays lines at their time; a loop starts again and keeps its rate; a stream switched on later
               joins at the right place; a one-shot finishes.
2. Variables   a value above max is clamped and the owner republishes its spec; wrong names and types are skipped.
3. Engine      the start sends the maze, the specs and the streams at their rates; nothing from game_manager.
4. Commands    e_stop and clear_e_stop change platform/state through the override of behaviour.json; read_maze
               plays its file and returns to the normal stream; replay and unknown commands are ignored;
               with respond off nothing is answered (E-T4).
5. Keys        h stops the route and shows hand_present; c sends the new maze and its routes; an offline
               program publishes nothing; events.json presses keys at their time.
6. Bad data    a missing file, a bad action and a game_manager topic stop the start with the file name.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))  # repo root, for `import shared`

from engine import DataError, Engine  # noqa: E402
from player import Player  # noqa: E402
from shared import topics as T  # noqa: E402
from topic_table import STAND_IN_PROGRAMS  # noqa: E402
from variables import VariableSpecs  # noqa: E402

DATA = HERE / "data"
TICK_S = 0.005
EXPECTED_RATE_HZ = {T.VISION_BALL: 30, T.PLAN_ROUTE: 30, T.CONTROL_TARGET_TILT: 30, T.PLATFORM_STATE: 50, T.GLOVE_STATE: 50,
                    T.AI_STATUS: 10, T.VISION_STATUS: 1, T.VISION_EDIT_STATE: 1}


def line(t_s, topic=T.VISION_BALL, **msg):
    return {"t_s": t_s, "topic": topic, "msg": msg}


def run(engine, seconds, start_s=0.0):
    out, now_s = [], start_s
    while now_s <= start_s + seconds:
        out += engine.tick(now_s)
        now_s += TICK_S
    return out


def of_topic(publications, topic):
    return [p for p in publications if p.topic == topic]


def command(cmd, writer="cs_app"):
    return {"timestamp_s": 1.0, "seq": 0, "version": 1, "writer": writer, "cmd": cmd, "mode": None, "file": None, "speed": None}


@pytest.fixture
def engine():
    return Engine(DATA)


@pytest.fixture
def data_copy(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    return tmp_path / "data"


# ---------------------------------------------------------------- 1 player
def test_player_plays_lines_at_their_time():
    player = Player([line(0.0, x=1), line(1.0, x=2)], None, 10.0, 10.0)
    assert [item["msg"]["x"] for item in player.due(10.5)] == [1]
    assert [item["msg"]["x"] for item in player.due(11.2)] == [2]
    assert player.is_finished


def test_player_loops_with_the_same_rate():
    player = Player([line(0.0), line(0.5)], 1.0, 0.0, 0.0)
    assert len(player.due(0.0)) == 1
    assert len(player.due(3.2)) == 6  # 0.5, 1.0, 1.5, 2.0, 2.5, 3.0
    assert not player.is_finished


def test_player_started_later_joins_at_the_right_place_of_the_loop():
    lines = [line(0.0, x=0), line(0.25, x=1), line(0.5, x=2), line(0.75, x=3)]
    player = Player(lines, 1.0, 0.0, 2.4)  # phase 0.4: next is the line at 0.5
    assert [item["msg"]["x"] for item in player.due(2.6)] == [2]


def test_empty_player_is_finished():
    assert Player([], 1.0, 0.0, 0.0).is_finished


# ---------------------------------------------------------------- 2 variables
def spec(name, value, **extra):
    return {"name": name, "value": value, "default": value, "min": None, "max": None, "step": None, "choices": None,
            "is_live": True, "description": "", **extra}


def test_value_above_max_is_clamped_and_the_owner_republishes():
    specs = VariableSpecs({"platform": [spec("max_tilt_deg", 10, min=0, max=15)]})
    (publication,) = specs.answer("platform", {"max_tilt_deg": 99})
    assert publication.program == "bridge" and publication.topic == T.variables_spec("platform")
    assert publication.fields["variables"][0]["value"] == 15


def test_wrong_names_and_types_are_skipped():
    specs = VariableSpecs({"platform": [spec("max_tilt_deg", 10, min=0, max=15), spec("serial_port", "COM3", choices=["COM3", "COM4"])]})
    (publication,) = specs.answer("platform", {"no_such": 3, "max_tilt_deg": "high", "serial_port": "COM99"})
    assert [v["value"] for v in publication.fields["variables"]] == [10, "COM3"]
    assert specs.answer("game", {"not_moving_time_s": 1}) == []


# ---------------------------------------------------------------- 3 engine start
def test_start_sends_maze_specs_and_streams_at_their_rates(engine):
    publications = run(engine, 1.0)
    assert of_topic(publications, T.VISION_MAZE)[0].fields["maze_id"] == "demo"
    assert len(of_topic(publications, T.PLAN_DISTANCE_MAP)) == 1
    assert {p.topic for p in publications if p.topic.endswith("/variables_spec")}
    for topic, rate_hz in EXPECTED_RATE_HZ.items():
        assert abs(len(of_topic(publications, topic)) - rate_hz) <= 2, topic


def test_nothing_from_game_manager_and_only_stand_in_programs(engine):
    publications = run(engine, 3.0)
    engine.on_command(command("e_stop"), 3.0)
    publications += run(engine, 1.0, 3.01)
    assert not [p for p in publications if p.topic in (T.GAME_STATE, T.GAME_WARNING)]
    assert {p.program for p in publications} <= STAND_IN_PROGRAMS


def test_the_loop_starts_again(engine):
    loop_s = json.loads((DATA / "behaviour.json").read_text(encoding="utf-8"))["loop_s"]
    balls = of_topic(run(engine, loop_s + 1.0), T.VISION_BALL)
    samples_per_loop = round(loop_s * EXPECTED_RATE_HZ[T.VISION_BALL])
    assert len({(b.fields["x_mm"], b.fields["y_mm"]) for b in balls}) > 1  # the ball moves during the loop
    assert balls[samples_per_loop].fields == balls[0].fields  # and the second loop starts with the first sample
    assert abs(len(balls) - EXPECTED_RATE_HZ[T.VISION_BALL] * (loop_s + 1.0)) <= 2


# ---------------------------------------------------------------- 4 commands
def last_platform(publications):
    return of_topic(publications, T.PLATFORM_STATE)[-1].fields


def test_e_stop_and_clear_e_stop_change_platform_state(engine):
    run(engine, 0.5)
    engine.on_command(command("e_stop"), 0.5)
    stopped = last_platform(run(engine, 0.1, 0.51))
    assert stopped["is_e_stop"] is True and stopped["applied_tilt_x_deg"] == 0
    engine.on_command(command("clear_e_stop"), 0.7)
    assert last_platform(run(engine, 0.1, 0.71))["is_e_stop"] is False


def test_no_answer_without_respond_for_replay_and_for_unknown_commands(engine):
    run(engine, 0.5)
    for ignored in (command("start"), command("e_stop", writer="replay")):
        engine.on_command(ignored, 0.5)
    engine.respond = False
    engine.on_command(command("e_stop"), 0.5)
    assert engine.on_variables("platform", {"writer": "cs_app", "max_tilt_deg": 1}) == []
    assert last_platform(run(engine, 0.5, 0.51))["is_e_stop"] is False


def test_read_maze_rescans_then_returns_to_the_normal_stream(engine):
    behaviour = json.loads((DATA / "behaviour.json").read_text(encoding="utf-8"))
    rescan_s = next(a["after_s"] for a in behaviour["commands"]["read_maze"] if "after_s" in a)
    run(engine, 0.5)
    engine.on_command(command("read_maze"), 0.5)
    during = run(engine, rescan_s - 0.3, 0.51)
    assert {p.fields["state"] for p in of_topic(during, T.VISION_EDIT_STATE)} == {"rescanning"}
    after = run(engine, 0.5, 0.51 + rescan_s - 0.3)  # clear comes at once, not with the next 1 Hz line
    assert [p.fields["state"] for p in of_topic(after, T.VISION_EDIT_STATE)][0] == "clear"
    assert of_topic(after, T.VISION_MAZE)[0].fields["source"] == "scan"


# ---------------------------------------------------------------- 5 keys
def test_hand_stops_the_route_and_c_sends_the_new_maze(engine):
    run(engine, 0.5)
    assert engine.press("h", 0.5)
    hand = run(engine, 1.5, 0.51)
    assert {p.fields["state"] for p in of_topic(hand, T.VISION_EDIT_STATE)} == {"hand_present"}
    assert not of_topic(hand, T.PLAN_ROUTE)

    assert engine.press("c", 2.1)
    changed = run(engine, 1.5, 2.11)
    assert of_topic(changed, T.VISION_EDIT_STATE)[0].fields["state"] == "clear"  # at once after the maze
    assert of_topic(changed, T.VISION_MAZE)[0].fields["maze_id"] == "demo-changed"
    assert {p.fields["maze_id"] for p in of_topic(changed, T.PLAN_ROUTE)} == {"demo-changed"}
    assert {p.fields["state"] for p in of_topic(changed, T.VISION_EDIT_STATE)} == {"clear"}


def test_unknown_key_is_not_pressed(engine):
    assert engine.press("zz", 0.0) is False


def test_offline_program_publishes_nothing_until_it_is_back(engine):
    run(engine, 0.5)
    engine.press("v", 0.5)
    assert engine.offline_programs == frozenset({"vision"})
    assert not [p for p in run(engine, 1.0, 0.51) if p.program == "vision"]
    engine.press("V", 1.6)
    assert of_topic(run(engine, 0.5, 1.61), T.VISION_BALL)


def test_events_press_keys_at_their_time(data_copy):
    (data_copy / "events.json").write_text(json.dumps([{"t_s": 1.0, "key": "h"}, {"t_s": 2.0, "key": "c"}]), encoding="utf-8")
    publications = run(Engine(data_copy), 3.0)
    assert len(of_topic(publications, T.VISION_MAZE)) == 2
    assert "hand_present" in {p.fields["state"] for p in of_topic(publications, T.VISION_EDIT_STATE)}


# ---------------------------------------------------------------- 6 bad data
def test_missing_file_names_the_file(data_copy):
    (data_copy / "samples.jsonl").unlink()
    with pytest.raises(DataError, match="samples.jsonl"):
        Engine(data_copy)


def test_unknown_action_is_refused(data_copy):
    behaviour = json.loads((data_copy / "behaviour.json").read_text(encoding="utf-8"))
    behaviour["triggers"]["h"]["do"].append({"explode": True})
    (data_copy / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")
    with pytest.raises(DataError, match="explode"):
        Engine(data_copy)


def change_variable_specs(data_copy, change):
    path = data_copy / "variables_spec.json"
    specs = json.loads(path.read_text(encoding="utf-8"))
    change(specs)
    path.write_text(json.dumps(specs), encoding="utf-8")


def test_variable_specs_of_another_program_are_refused_with_a_data_error(data_copy):
    change_variable_specs(data_copy, lambda specs: specs.update({"game": specs["pid"]}))  # GameManager's own key
    with pytest.raises(DataError, match="variables_spec.json.*game"):
        Engine(data_copy)


def test_unknown_variable_key_is_refused_with_a_data_error(data_copy):
    change_variable_specs(data_copy, lambda specs: specs.update({"no_such_key": specs["pid"]}))
    with pytest.raises(DataError, match="no_such_key"):
        Engine(data_copy)


def test_variable_with_a_missing_field_is_refused_with_a_data_error(data_copy):
    change_variable_specs(data_copy, lambda specs: specs["pid"][0].pop("choices"))
    with pytest.raises(DataError, match="variables_spec.json.*pid"):
        Engine(data_copy)


def test_a_game_manager_topic_in_a_file_is_refused(data_copy):
    state = {"state": "playing", "mode": "ai", "game_id": "20261204-140500", "maze_id": "demo", "elapsed_s": 1.0, "cell": None,
             "distance_to_exit_cells": None, "progress_pct": 0.0, "result": "none"}
    with open(data_copy / "hand.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"t_s": 0.5, "topic": T.GAME_STATE, "msg": state}) + "\n")
    with pytest.raises(DataError, match="game/state"):
        Engine(data_copy)
