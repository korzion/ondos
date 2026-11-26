"""Which program writes which topic, read from shared/interfaces/topics.json (IF-03).

The fixture publisher stands in for the writers of the IF-02, IF-04 and IF-06 topics (bridge, vision,
auto_controller). Everything else, above all game/state and game/warning, is never published here.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from shared import topics as T

TOPICS_JSON = Path(__file__).resolve().parents[3] / "shared" / "interfaces" / "topics.json"
STAND_IN_INTERFACES = ("IF-02", "IF-04", "IF-06")
VARIABLES_SPEC_SUFFIX = "/variables_spec"


class ForbiddenTopic(Exception):
    """The topic belongs to a program the fixture publisher does not stand in for."""


class Publication(NamedTuple):
    program: str
    topic: str
    fields: dict
    ball_index: int | None = None  # vision/ball only: the sample number that ball_seq in the data files points to


@lru_cache(maxsize=1)
def _topic_entries() -> tuple[dict, ...]:
    return tuple(json.loads(TOPICS_JSON.read_text(encoding="utf-8"))["topics"])


def writer_by_topic() -> dict[str, str]:
    """Topic name (templates like cs/variables/{key} included) to its writer."""
    return {entry["name"]: entry["writer"] for entry in _topic_entries()}


def _stand_in_programs() -> frozenset[str]:
    return frozenset(entry["writer"] for entry in _topic_entries() if entry["interface"] in STAND_IN_INTERFACES)


STAND_IN_PROGRAMS = _stand_in_programs()


def writer_of(topic: str) -> str:
    if topic.endswith(VARIABLES_SPEC_SUFFIX):
        return T.KEY_OWNER[topic.removesuffix(VARIABLES_SPEC_SUFFIX)]  # the owner of each key, shared/interfaces/variables.json
    return writer_by_topic()[topic]


def publication(topic: str, fields: dict) -> Publication:
    """A message of a stand-in program; refuses every topic written by another program."""
    program = writer_of(topic)
    if program not in STAND_IN_PROGRAMS:
        raise ForbiddenTopic(f"{topic} is written by {program}, not by a program this publisher stands in for")
    return Publication(program, topic, fields)
