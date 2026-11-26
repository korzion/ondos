"""What the fixture publisher plays and when. No maze, route or controller logic: only ready data files.

Everything it plays is in data/ (written by make_fixture.py, or edited by hand). behaviour.json says which file
plays after which command or key; events.json (optional) presses keys at given times. The engine has no broker:
tick() returns what to publish, publisher.py puts it on the bus.
"""
import json
from pathlib import Path

from player import Player
from shared import topics as T
from shared.tools.replay import load_fixture
from topic_table import STAND_IN_PROGRAMS, Publication, writer_of
from variables import VariableSpecs

COMMAND_SENDER = writer_of(T.CS_COMMAND)  # the Control Station app, from topics.json
ACTION_KEYS = ("play", "streams", "override", "clear_override", "after_s")
KEY_RESPOND_OFF, KEY_RESPOND_ON = "n", "y"


class DataError(Exception):
    """A data file is missing or wrong; the message starts with the file name."""


def program_keys() -> dict[str, tuple[str, str]]:
    """First letter takes a stand-in program offline, the capital letter brings it back."""
    keys = {}
    for program in sorted(STAND_IN_PROGRAMS):
        keys[program[0]] = ("offline", program)
        keys[program[0].upper()] = ("online", program)
    return keys


class Engine:
    def __init__(self, data_dir: Path, respond: bool = True) -> None:
        self.respond = respond
        self._behaviour = _read_json(data_dir / "behaviour.json")
        self._events = sorted(_read_json(data_dir / "events.json") if (data_dir / "events.json").exists() else [],
                              key=lambda event: event["t_s"])
        try:
            self._variables = VariableSpecs(_read_json(data_dir / "variables_spec.json"))
        except ValueError as error:
            raise DataError(f"variables_spec.json: {error}") from None
        self._files = {name: _load_lines(data_dir, name) for name in _referenced_files(self._behaviour)}
        self._check_behaviour()
        self._streams: dict[str, Player] = {}
        self._shots: list[Player] = []
        self._overrides: dict[str, dict] = {}
        self._scheduled: list[tuple[float, list[dict]]] = []
        self._offline: frozenset[str] = frozenset()
        self._start_s: float | None = None

    @property
    def offline_programs(self) -> frozenset[str]:
        return self._offline

    def help_text(self) -> str:
        rows = [f"  {key}  {trigger['description']}" for key, trigger in self._behaviour["triggers"].items()]
        rows += [f"  {KEY_RESPOND_OFF}  stop answering commands (E-T4)", f"  {KEY_RESPOND_ON}  answer commands again"]
        rows += [f"  {key}  {action} {program}" for key, (action, program) in program_keys().items()]
        return "Keys (letter + Enter):\n" + "\n".join(rows) + "\n  q  quit"

    # ------------------------------------------------------------------ time
    def tick(self, now_s: float) -> list[Publication]:
        out: list[Publication] = []
        if self._start_s is None:
            self._start_s = now_s
            self._run(self._behaviour["start"], now_s)
            out += self._variables.start_publications()
        self._fire_events(now_s)
        self._run_scheduled(now_s)
        for player in [*self._streams.values(), *self._shots]:
            out += [self._publication(line) for line in player.due(now_s)]
        self._shots = [shot for shot in self._shots if not shot.is_finished]
        return [publication for publication in out if publication.program not in self._offline]

    def _publication(self, line: dict) -> Publication:
        topic = line["topic"]
        return Publication(writer_of(topic), topic, {**line["msg"], **self._overrides.get(topic, {})})

    def _fire_events(self, now_s: float) -> None:
        while self._events and self._events[0]["t_s"] <= now_s - self._start_s:
            self.press(self._events.pop(0)["key"], now_s)

    def _run_scheduled(self, now_s: float) -> None:
        due = [item for item in self._scheduled if item[0] <= now_s]
        self._scheduled = [item for item in self._scheduled if item[0] > now_s]
        for _, actions in due:
            self._run(actions, now_s)

    # ------------------------------------------------------------------ commands, variables and keys
    def _should_answer(self, msg: dict) -> bool:
        return self.respond and msg.get("writer") == COMMAND_SENDER

    def on_command(self, msg: dict, now_s: float) -> None:
        """Run the actions of behaviour.json for this cs/command; GameManager's commands are not in the file."""
        if self._should_answer(msg):
            self._run(self._behaviour["commands"].get(msg.get("cmd"), []), now_s)

    def on_variables(self, key: str, msg: dict) -> list[Publication]:
        if not self._should_answer(msg) or self._variables.owner_of(key) in self._offline:
            return []
        return self._variables.answer(key, msg)

    def press(self, key: str, now_s: float) -> bool:
        """A manual key; False when the key is not known."""
        if key in self._behaviour["triggers"]:
            self._run(self._behaviour["triggers"][key]["do"], now_s)
        elif key in (KEY_RESPOND_OFF, KEY_RESPOND_ON):
            self.respond = key == KEY_RESPOND_ON
        elif key in program_keys():
            action, program = program_keys()[key]
            self._offline = self._offline | {program} if action == "offline" else self._offline - {program}
        else:
            return False
        return True

    # ------------------------------------------------------------------ actions of behaviour.json
    def _run(self, actions: list[dict], now_s: float) -> None:
        for action in actions:
            if "play" in action:
                self._shots.append(Player(self._files[action["play"]], None, now_s, now_s))
            elif "streams" in action:
                self._set_streams(action["streams"], now_s)
            elif "override" in action:
                self._overrides = {**self._overrides, **{topic: {**self._overrides.get(topic, {}), **fields}
                                                         for topic, fields in action["override"].items()}}
            elif "clear_override" in action:
                self._overrides = {topic: fields for topic, fields in self._overrides.items() if topic not in action["clear_override"]}
            else:
                self._scheduled.append((now_s + action["after_s"], action["do"]))

    def _set_streams(self, names: list[str], now_s: float) -> None:
        loop_s = self._behaviour["loop_s"]
        self._streams = {name: self._streams.get(name) or Player(self._files[name], loop_s, self._start_s, now_s) for name in names}

    # ------------------------------------------------------------------ checks at start
    def _check_behaviour(self) -> None:
        known_keys = {*self._behaviour["triggers"], KEY_RESPOND_OFF, KEY_RESPOND_ON, *program_keys()}
        if len(known_keys) != len(self._behaviour["triggers"]) + 2 + len(program_keys()):
            raise DataError("behaviour.json: a trigger key is also a built-in key")
        for event in self._events:
            if event.get("key") not in known_keys or "t_s" not in event:
                raise DataError(f"events.json: each event needs t_s and a known key ({sorted(known_keys)})")
        for actions in _all_action_lists(self._behaviour):
            for action in actions:
                if not any(name in action for name in ACTION_KEYS):
                    raise DataError(f"behaviour.json: unknown action {action}; allowed: {ACTION_KEYS}")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise DataError(f"{path.name}: not found in {path.parent} (run make_fixture.py)") from None
    except ValueError as error:
        raise DataError(f"{path.name}: not valid JSON ({error})") from None


def _load_lines(data_dir: Path, name: str) -> list[dict]:
    path = data_dir / name
    if not path.exists():
        raise DataError(f"{name}: not found in {data_dir} (run make_fixture.py)")
    try:
        lines = load_fixture(path)
    except ValueError as error:
        raise DataError(str(error)) from None
    for line in lines:
        program = writer_of(line["topic"])
        if program not in STAND_IN_PROGRAMS:
            raise DataError(f"{name}: {line['topic']} is written by {program}, which this publisher does not stand in for")
    return lines


def _all_action_lists(behaviour: dict) -> list[list[dict]]:
    """Every list of actions, including the ones inside after_s."""
    found = [behaviour["start"], *behaviour["commands"].values(), *(t["do"] for t in behaviour["triggers"].values())]
    for actions in list(found):
        found += [action["do"] for action in actions if "after_s" in action]
    return found


def _referenced_files(behaviour: dict) -> list[str]:
    names = []
    for actions in _all_action_lists(behaviour):
        for action in actions:
            names += [action["play"]] if "play" in action else action.get("streams", [])
    return sorted(set(names))
