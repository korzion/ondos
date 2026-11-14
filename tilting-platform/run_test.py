"""Tests of A · Tilting Platform (design document A.9).

    python run_test.py --list
    python run_test.py <TEST-ID> [--input DIR]

Inputs are in fixtures/<TEST-ID>/. Each test prints PASS or FAIL for every check;
see shared/testing/runner.py for the helpers (check, load_json, play_fixture, observe, checklist).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for `import shared`

from shared.testing import TestSuite  # noqa: E402

suite = TestSuite(__file__)


@suite.test("A-T1", "Two-axis tilt", requirement="A-R1")
def a_t1(t):
    t.not_implemented()


@suite.test("A-T2", "Glove control", requirement="A-R2")
def a_t2(t):
    t.not_implemented()


@suite.test("A-T3", "Laptop commands", requirement="A-R3")
def a_t3(t):
    t.not_implemented()


@suite.test("A-T4", "State publishing", requirement="A-R4")
def a_t4(t):
    t.not_implemented()


@suite.test("A-T5", "Safe state", requirement="A-R5")
def a_t5(t):
    t.not_implemented()


if __name__ == "__main__":
    suite.main()
