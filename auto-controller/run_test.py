"""Tests of D · Auto Controller (design document D.9).

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


@suite.test("D-T1", "AI in training environment", requirement="D-R1")
def d_t1(t):
    t.not_implemented()


@suite.test("D-T2", "AI vs PID", requirement="D-R2")
def d_t2(t):
    t.not_implemented()


@suite.test("D-T3", "Decision time", requirement="D-R3")
def d_t3(t):
    t.not_implemented()


@suite.test("D-T4", "Only valid commands", requirement="D-R4")
def d_t4(t):
    t.not_implemented()


@suite.test("D-T5", "PID output", requirement="D-R5")
def d_t5(t):
    t.not_implemented()


@suite.test("D-T6", "Training rows", requirement="D-R6")
def d_t6(t):
    t.not_implemented()


@suite.test("D-T7", "Signs", requirement="D-R7")
def d_t7(t):
    t.not_implemented()


if __name__ == "__main__":
    suite.main()
