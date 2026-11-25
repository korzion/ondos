import json

import pytest

from shared import topics as T
from shared.interfaces import validate
from vision.config_file import ConfigError
from vision.tests.message_helpers import with_envelope
from vision.vision_variables import CONFIG_KEY, DEFAULT_VARIABLES_PATH, VisionVariables

SPEC_TOPIC = T.variables_spec(CONFIG_KEY)


def default_specs() -> list[dict]:
    return json.loads(DEFAULT_VARIABLES_PATH.read_text(encoding="utf-8"))["variables"]


def spec_value(variables: VisionVariables, name: str):
    return next(entry["value"] for entry in variables.to_spec()["variables"] if entry["name"] == name)


def test_file_defines_exactly_the_shared_variable_names():
    names = [entry["name"] for entry in VisionVariables.load().to_spec()["variables"]]
    assert sorted(names) == sorted(T.VARIABLES[CONFIG_KEY])


def test_spec_is_a_valid_variables_spec_message():
    validate(SPEC_TOPIC, with_envelope(SPEC_TOPIC, VisionVariables.load().to_spec(), writer="vision"))


def test_value_above_max_is_clamped():
    variables = VisionVariables.load()
    spec = next(s for s in default_specs() if s["name"] == "lost_timeout_ms")
    assert variables.apply({"lost_timeout_ms": spec["max"] + 1000}) == ["lost_timeout_ms"]
    assert variables.get("lost_timeout_ms") == spec["max"]
    assert spec_value(variables, "lost_timeout_ms") == spec["max"]


def test_integer_variable_stays_integer_and_float_variable_becomes_float():
    variables = VisionVariables.load()
    variables.apply({"edit_enter_frames": 3.4, "edit_clear_time_s": 2})
    assert variables.get("edit_enter_frames") == 3 and isinstance(variables.get("edit_enter_frames"), int)
    assert isinstance(variables.get("edit_clear_time_s"), float)


@pytest.mark.parametrize("name, value", [
    ("edit_detection_enabled", 1),         # a bool variable needs a bool
    ("lost_timeout_ms", True),             # a number variable never takes a bool
    ("lost_timeout_ms", "300"),
    ("lost_timeout_ms", float("nan")),
    ("camera_index", 7),                   # not one of the choices
    ("camera_index", True),                # True == 1, but it is not a camera index
    ("no_such_variable", 1),
])
def test_wrong_values_are_ignored(name, value):
    variables = VisionVariables.load()
    before = variables.to_spec()
    assert variables.apply({name: value}) == []
    assert variables.to_spec() == before


def test_unchanged_value_is_not_reported_as_changed():
    variables = VisionVariables.load()
    assert variables.apply({"gain": variables.get("gain")}) == []


def test_default_override_sets_default_and_value():
    variables = VisionVariables.load(default_overrides={"camera_index": 2})
    entry = next(e for e in variables.to_spec()["variables"] if e["name"] == "camera_index")
    assert entry["value"] == 2 and entry["default"] == 2


def test_default_override_outside_the_spec_is_an_error():
    with pytest.raises(ConfigError, match="camera_index"):
        VisionVariables.load(default_overrides={"camera_index": 9})


def test_missing_variable_is_an_error():
    specs = [s for s in default_specs() if s["name"] != "gain"]
    with pytest.raises(ConfigError, match="gain"):
        VisionVariables(specs)


def test_default_outside_range_is_an_error():
    specs = default_specs()
    next(s for s in specs if s["name"] == "gain")["default"] = -1
    with pytest.raises(ConfigError, match="gain"):
        VisionVariables(specs)
