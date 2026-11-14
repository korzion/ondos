"""Tests of C · Vision (design document C.9).

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


@suite.test("C-T1", "Position accuracy", requirement="C-R1")
def c_t1(t):
    t.not_implemented()


@suite.test("C-T2", "Delay", requirement="C-R2")
def c_t2(t):
    t.not_implemented()


@suite.test("C-T3", "Maze scan", requirement="C-R3")
def c_t3(t):
    t.not_implemented()


@suite.test("C-T4", "Exit detection", requirement="C-R4")
def c_t4(t):
    t.not_implemented()


@suite.test("C-T5", "Lost ball", requirement="C-R5")
def c_t5(t):
    t.not_implemented()


@suite.test("C-T6", "Wall hits", requirement="C-R6")
def c_t6(t):
    t.not_implemented()


@suite.test("C-T7", "Route", requirement="C-R7")
def c_t7(t):
    t.not_implemented()


@suite.test("C-T8", "Maze change", requirement="C-R8")
def c_t8(t):
    t.not_implemented()


@suite.test("C-T9", "False pauses", requirement="C-R9")
def c_t9(t):
    t.not_implemented()


if __name__ == "__main__":
    suite.main()
