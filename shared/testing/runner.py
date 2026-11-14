"""Common base for every module's run_test.py (design document section 3).

A module's run_test.py:

    from shared.testing import TestSuite
    suite = TestSuite(__file__)

    @suite.test("A-T3", "Laptop commands", requirement="A-R3")
    def a_t3(t):
        cases = t.load_json("cases.json")          # from fixtures/A-T3/ (or --input DIR)
        ...
        t.check("invalid command rejected", rejected, f"got {result}")

    suite.main()

Command line:
    python run_test.py --list
    python run_test.py <TEST-ID> [--input DIR] [--host H] [--port P]

Prints PASS or FAIL for every check and a final line "<TEST-ID>: PASS|FAIL".
Exit code: 0 = PASS, 1 = FAIL, 2 = not implemented / usage error.
The test computes the expected result itself and never calls another module.
"""
from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from shared import topics as T


class NotImplementedTest(Exception):
    pass


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class TestContext:
    test_id: str
    fixture_dir: Path
    host: str = T.BROKER_HOST
    port: int = T.BROKER_TCP_PORT
    checks: list[Check] = field(default_factory=list)

    # ------------------------------------------------------------ results
    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        ok = bool(ok)
        self.checks.append(Check(name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
        return ok

    def not_implemented(self) -> None:
        raise NotImplementedTest()

    def checklist(self, items: list[str]) -> None:
        """Manual checks (e.g. pressing the E-stop): the operator answers y/n for each item."""
        for item in items:
            answer = input(f"  [manual] {item}  ok? [y/n] ").strip().lower()
            self.check(item, answer == "y", "operator")

    # ------------------------------------------------------------ inputs
    def path(self, name: str) -> Path:
        p = self.fixture_dir / name
        if not p.exists():
            raise FileNotFoundError(f"{self.test_id}: input file {p} not found")
        return p

    def load_json(self, name: str):
        return json.loads(self.path(name).read_text(encoding="utf-8"))

    def load_jsonl(self, name: str) -> list:
        return [json.loads(l) for l in self.path(name).read_text(encoding="utf-8").splitlines() if l.strip()]

    def load_csv(self, name: str) -> list[dict]:
        with open(self.path(name), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # ------------------------------------------------------------ bus
    def require_broker(self) -> None:
        try:
            socket.create_connection((self.host, self.port), timeout=1).close()
        except OSError:
            raise SystemExit(f"no MQTT broker at {self.host}:{self.port}. Start one with:\n"
                             f"  mosquitto -c shared/bus/mosquitto.conf")

    def play_fixture(self, name: str, background: bool = True) -> threading.Thread | int:
        """Play fixtures/<TEST-ID>/<name> through the playback tool in fixture mode (IF-09)."""
        from shared.tools.replay import play_fixture
        self.require_broker()
        path = self.path(name)
        if not background:
            return play_fixture(path, self.host, self.port)
        th = threading.Thread(target=play_fixture, args=(path, self.host, self.port), daemon=True)
        th.start()
        return th

    def observe(self, patterns: list[str], duration_s: float, start: Callable[[], object] | None = None) -> list[tuple[str, object, float]]:
        """Collect messages on `patterns` for duration_s; calls start() once subscribed.
        Observes with a plain client: it publishes nothing, not even sys/online."""
        import paho.mqtt.client as mqtt
        self.require_broker()
        got: list[tuple[str, object, float]] = []
        ready = threading.Event()

        def on_connect(c, *a):
            for p in patterns:
                c.subscribe(p, qos=1)
            ready.set()

        def on_message(c, u, m):
            try:
                msg = json.loads(m.payload) if m.payload else None
            except ValueError:
                msg = bytes(m.payload)
            got.append((m.topic, msg, time.time()))

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ondos-test-{self.test_id}-{id(self):x}")
        client.on_connect, client.on_message = on_connect, on_message
        client.connect(self.host, self.port)
        client.loop_start()
        try:
            ready.wait(3)
            time.sleep(0.2)
            if start:
                start()
            time.sleep(duration_s)
        finally:
            client.loop_stop()
            client.disconnect()
        return got


@dataclass
class _Test:
    test_id: str
    title: str
    requirement: str
    fn: Callable[[TestContext], None]


class TestSuite:
    def __init__(self, run_test_file: str) -> None:
        self.module_dir = Path(run_test_file).resolve().parent
        self.tests: dict[str, _Test] = {}

    def test(self, test_id: str, title: str, requirement: str = ""):
        def deco(fn):
            self.tests[test_id] = _Test(test_id, title, requirement, fn)
            return fn
        return deco

    def run(self, test_id: str, input_dir: Path | None = None, host: str = T.BROKER_HOST,
            port: int = T.BROKER_TCP_PORT) -> int:
        if test_id not in self.tests:
            print(f"unknown test {test_id}; known: {', '.join(self.tests)}")
            return 2
        t = self.tests[test_id]
        fixture_dir = (input_dir or self.module_dir / "fixtures" / test_id).resolve()
        print(f"{t.test_id} {t.title} ({t.requirement})  inputs: {fixture_dir}")
        ctx = TestContext(test_id, fixture_dir, host, port)
        try:
            t.fn(ctx)
        except NotImplementedTest:
            print(f"{test_id}: NOT IMPLEMENTED")
            return 2
        except FileNotFoundError as e:
            print(f"  FAIL  {e}")
            print(f"{test_id}: FAIL")
            return 1
        except AssertionError as e:
            ctx.check("assertion", False, str(e))
        ok = bool(ctx.checks) and all(c.ok for c in ctx.checks)
        if not ctx.checks:
            print("  FAIL  the test made no checks")
        failed = sum(not c.ok for c in ctx.checks)
        print(f"{test_id}: {'PASS' if ok else 'FAIL'}  ({len(ctx.checks) - failed}/{len(ctx.checks)} checks)")
        return 0 if ok else 1

    def main(self, argv: list[str] | None = None) -> None:
        ap = argparse.ArgumentParser(description="Run one module test and print PASS or FAIL.")
        ap.add_argument("test_id", nargs="?", help="e.g. A-T3")
        ap.add_argument("--list", action="store_true", help="list the tests of this module")
        ap.add_argument("--input", type=Path, help="use this folder instead of fixtures/<TEST-ID>/")
        ap.add_argument("--host", default=T.BROKER_HOST)
        ap.add_argument("--port", type=int, default=T.BROKER_TCP_PORT)
        a = ap.parse_args(argv)
        if a.list or not a.test_id:
            for t in self.tests.values():
                print(f"{t.test_id:6} {t.requirement:6} {t.title}")
            sys.exit(0 if a.list else 2)
        sys.exit(self.run(a.test_id, a.input, a.host, a.port))
