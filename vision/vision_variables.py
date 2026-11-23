"""Control variables of Vision (C.7) and their vision/variables_spec (IF-07).

The variable definitions (default, range, live or not, description) are data in
config/variables.json; this class holds the values in use and checks every change.
"""
from __future__ import annotations

import logging
import math
import threading
from pathlib import Path

from shared import topics as T
from vision.config_file import ConfigError, check_fields, is_number, read_json_object

log = logging.getLogger(__name__)

CONFIG_KEY = "vision"  # configuration key of Vision: cs/variables/vision, vision/variables_spec (IF-03)
DEFAULT_VARIABLES_PATH = Path(__file__).resolve().parent / "config" / "variables.json"
SPEC_FIELDS = frozenset({"name", "default", "min", "max", "step", "choices", "is_live", "description"})

Value = bool | int | float | str


class VisionVariables:
    """Holds the value in use of every Vision control variable; checks and clamps every change (IF-07)."""

    def __init__(self, specs: list[dict], default_overrides: dict[str, Value] | None = None) -> None:
        _check_specs(specs)
        self._specs = {spec["name"]: dict(spec) for spec in specs}
        self._values: dict[str, Value] = {name: spec["default"] for name, spec in self._specs.items()}
        self._lock = threading.Lock()
        for name, value in (default_overrides or {}).items():
            self._override_default(name, value)

    @classmethod
    def load(cls, path: Path = DEFAULT_VARIABLES_PATH,
             default_overrides: dict[str, Value] | None = None) -> VisionVariables:
        """Read the definitions from a file. default_overrides replaces defaults that start from another file
        (camera_index starts from the configuration file, IF-03)."""
        data = read_json_object(path)
        check_fields(data, frozenset({"variables"}), str(path))
        return cls(data["variables"], default_overrides)

    def get(self, name: str) -> Value:
        with self._lock:
            return self._values[name]

    def apply(self, changes: dict[str, object]) -> list[str]:
        """Check, clamp and apply the requested values; return the names whose value changed.
        Unknown names and values of the wrong type are ignored with a warning."""
        changed = []
        with self._lock:
            for name, requested in changes.items():
                value = self._accepted_value(name, requested)
                if value is None or value == self._values[name]:
                    continue
                self._values[name] = value
                changed.append(name)
        return changed

    def to_spec(self) -> dict:
        """Payload of vision/variables_spec with the values in use."""
        with self._lock:
            return {"variables": [self._spec_entry(name) for name in self._specs]}

    def _spec_entry(self, name: str) -> dict:
        spec = self._specs[name]
        return {
            "name": name,
            "value": self._values[name],
            "default": spec["default"],
            "min": spec["min"],
            "max": spec["max"],
            "step": spec["step"],
            "choices": spec["choices"],
            "is_live": spec["is_live"],
            "description": spec["description"],
        }

    def _override_default(self, name: str, requested: Value) -> None:
        value = self._accepted_value(name, requested)
        if value is None:
            raise ConfigError(f"{name}: starting value {requested!r} is not allowed by its spec")
        self._specs[name]["default"] = value
        self._values[name] = value

    def _accepted_value(self, name: str, requested: object) -> Value | None:
        spec = self._specs.get(name)
        if spec is None:
            log.warning("unknown variable %r ignored", name)
            return None
        value = _accepted_value_for(spec, requested)
        if value is None:
            log.warning("%s: value %r rejected", name, requested)
        return value


def _accepted_value_for(spec: dict, requested: object) -> Value | None:
    """The value to use for a requested one, or None when it is not allowed (IF-07: check and clamp)."""
    if spec["choices"] is not None:
        return _matching_choice(spec["choices"], requested)
    default = spec["default"]
    if isinstance(default, bool):
        return requested if isinstance(requested, bool) else None
    if not is_number(requested) or not math.isfinite(requested):
        return None
    clamped = min(max(requested, spec["min"]), spec["max"])
    return round(clamped) if isinstance(default, int) else float(clamped)


def _matching_choice(choices: list, requested: object) -> Value | None:
    if isinstance(requested, bool):  # True == 1 in Python, but a bool is never a valid choice
        return None
    for choice in choices:
        if choice == requested:
            return choice
    return None


def _check_specs(specs: object) -> None:
    if not isinstance(specs, list):
        raise ConfigError("variables must be a list")
    for spec in specs:
        _check_spec(spec)
    _check_names([spec["name"] for spec in specs])


def _check_spec(spec: object) -> None:
    if not isinstance(spec, dict):
        raise ConfigError("every variable must be a JSON object")
    check_fields(spec, SPEC_FIELDS, f"variable {spec.get('name')!r}")
    name, default = spec["name"], spec["default"]
    if spec["choices"] is not None:
        if _matching_choice(spec["choices"], default) is None:
            raise ConfigError(f"{name}: default {default!r} is not one of the choices")
        return
    if isinstance(default, bool):
        return
    if not all(is_number(spec[field]) for field in ("default", "min", "max")):
        raise ConfigError(f"{name}: default, min and max must be numbers")
    if not spec["min"] <= default <= spec["max"]:
        raise ConfigError(f"{name}: default {default!r} is outside min..max")


def _check_names(names: list[str]) -> None:
    """The file must define exactly the variable names of shared/interfaces/variables.json."""
    if len(names) != len(set(names)):
        raise ConfigError("a variable is defined twice")
    expected = set(T.VARIABLES[CONFIG_KEY])
    missing = expected - set(names)
    if missing:
        raise ConfigError(f"variables missing from the file: {sorted(missing)}")
    unknown = set(names) - expected
    if unknown:
        raise ConfigError(f"variables not in shared/interfaces/variables.json: {sorted(unknown)}")
