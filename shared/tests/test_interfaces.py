import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from shared import topics as T
from shared.interfaces import ValidationError, validate, validate_file

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = json.loads((ROOT / "shared/interfaces/examples/messages.json").read_text(encoding="utf-8"))["examples"]


def example(topic):
    return copy.deepcopy(next(e["msg"] for e in EXAMPLES if e["topic"] == topic))


def test_generated_files_are_up_to_date():
    r = subprocess.run([sys.executable, str(ROOT / "shared/interfaces/gen.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda e: e["topic"])
def test_examples_are_valid(ex):
    validate(ex["topic"], ex["msg"])


def test_every_json_topic_has_an_example():
    names = {T.topic_info(e["topic"])["name"] for e in EXAMPLES}
    missing = {t["name"] for t in T.TOPIC_TABLE if t["payload"] != "jpeg"} - names
    assert not missing


def test_maze_example_file():
    validate_file("maze_file", json.loads((ROOT / "shared/interfaces/examples/maze_file.json").read_text()))


@pytest.mark.parametrize("topic,change,why", [
    ("vision/ball", lambda m: m.pop("frame_age_ms"), "missing field (D4: never left out)"),
    ("vision/ball", lambda m: m.update(extra=1), "unknown field"),
    ("vision/ball", lambda m: m.update(version=2), "unsupported version"),
    ("vision/ball", lambda m: m.update(is_visible=None), "null in a required field"),
    ("vision/ball", lambda m: m.pop("writer"), "missing envelope field"),
    ("game/state", lambda m: m.update(state="running"), "unknown enum value"),
    ("game/state", lambda m: m.update(game_id="2026-12-04"), "bad game_id"),
    ("plan/route", lambda m: m.update(target_points_mm=[[0, 0]] * 4), "more than 3 route points"),
    ("cs/command", lambda m: m.update(mode=None), "set_mode without mode"),
    ("cs/command", lambda m: m.update(cmd="replay", mode=None), "replay without file/speed"),
    ("cs/variables/platform", lambda m: m.update(max_tilt=3), "unknown variable name"),
    ("platform/variables_spec", lambda m: m["variables"][0].update(name="tilt_max"), "unknown variable in spec"),
    ("glove/state", lambda m: m.update(battery_pct=120), "percent out of range"),
])
def test_invalid_messages_are_rejected(topic, change, why):
    msg = example(topic)
    change(msg)
    with pytest.raises(ValidationError):
        validate(topic, msg)


def test_topic_info_patterns():
    assert T.topic_info("platform/variables_spec")["writer"] == "bridge"
    assert T.topic_info("pid/variables_spec")["writer"] == "auto_controller"
    assert T.topic_info("game/variables_spec")["writer"] == "game_manager"
    assert T.topic_info("cs/variables/vision")["retained"] is True
    assert T.topic_info("sys/online/vision")["writer"] == "vision"
    with pytest.raises(KeyError):
        T.topic_info("sys/online/simulator")
    with pytest.raises(KeyError):
        T.topic_info("vision/balls")


def test_retained_and_qos_match_if03():
    retained = {t["name"] for t in T.TOPIC_TABLE if t["retained"]}
    assert retained == {"game/state", "plan/distance_map", "vision/maze", "vision/status", "vision/edit_state",
                        "cs/variables/{key}", "{key}/variables_spec", "sys/online/{program}"}
    qos1 = {t["name"] for t in T.TOPIC_TABLE if t["qos"] == 1}
    assert qos1 == retained | {"cs/command", "vision/event", "game/warning"}
