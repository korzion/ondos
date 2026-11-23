"""Reading and checking Vision's JSON configuration files (config/*.json)."""
from __future__ import annotations

import json
from pathlib import Path

COMMENT_KEY = "$comment"  # a JSON file has no comments; this key holds the explanation and is skipped


class ConfigError(ValueError):
    """A configuration file is missing, unreadable, or has a missing or wrong field."""


def read_json_object(path: Path) -> dict:
    """Read a JSON file whose top level is an object."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path}: file not found") from None
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path}: not valid JSON ({error})") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level must be a JSON object")
    return data


def check_fields(data: dict, expected_fields: frozenset[str], where: str) -> None:
    """Raise ConfigError when a field is missing or unknown (a typo must not be ignored silently)."""
    present = set(data) - {COMMENT_KEY}
    missing = expected_fields - present
    if missing:
        raise ConfigError(f"{where}: missing field(s) {sorted(missing)}")
    unknown = present - expected_fields
    if unknown:
        raise ConfigError(f"{where}: unknown field(s) {sorted(unknown)}")


def is_number(value: object) -> bool:
    """True for int and float, but not for bool (in Python, True is also an int)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)
