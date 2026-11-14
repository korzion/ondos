"""Schema validation for bus messages and files (IF-03 … IF-09).

    from shared.interfaces import validate, validate_file, ValidationError
    validate("vision/ball", msg)           # full message, envelope included
    validate_file("maze_file", maze_dict)  # maze_file, recording_header, recording_line, fixture_line
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from shared.topics import VARIABLES, topic_info

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

__all__ = ["validate", "validate_file", "ValidationError", "SCHEMA_DIR"]


@lru_cache(maxsize=None)
def _registry() -> Registry:
    resources = []
    for p in SCHEMA_DIR.glob("*.schema.json"):
        s = json.loads(p.read_text(encoding="utf-8"))
        resources.append((s["$id"], Resource.from_contents(s)))
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def _validator(schema_file: str) -> Draft202012Validator:
    s = json.loads((SCHEMA_DIR / schema_file).read_text(encoding="utf-8"))
    return Draft202012Validator(s, registry=_registry())


def _raise_first(validator: Draft202012Validator, obj, where: str) -> None:
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        path = "/".join(str(x) for x in e.path) or "(root)"
        raise ValidationError(f"{where}: {path}: {e.message}")


def validate(topic: str, msg) -> None:
    """Raise ValidationError if `msg` is not a valid message for `topic`."""
    info = topic_info(topic)
    if info["payload"] == "jpeg":
        if not isinstance(msg, (bytes, bytearray)):
            raise ValidationError(f"{topic}: payload must be JPEG bytes")
        return
    if info["payload"] == "bool":
        if not isinstance(msg, bool):
            raise ValidationError(f"{topic}: payload must be a bool")
        return
    _raise_first(_validator(info["schema"]), msg, topic)
    key = info["params"].get("key")
    if key is not None:
        allowed = set(VARIABLES[key])
        if topic.startswith("cs/variables/"):
            names = [k for k in msg if k not in ("timestamp_s", "seq", "version", "writer")]
        else:
            names = [v["name"] for v in msg["variables"]]
        unknown = sorted(set(names) - allowed)
        if unknown:
            raise ValidationError(f"{topic}: unknown variable(s) {unknown} for key {key!r}")


def validate_file(kind: str, obj) -> None:
    """kind: maze_file, recording_header, recording_line or fixture_line."""
    _raise_first(_validator(f"{kind}.schema.json"), obj, kind)
