"""Tests of B · Glove Controller (design document B.9).

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


@suite.test("B-T1", "Rate and delay", requirement="B-R1")
def b_t1(t):
    t.not_implemented()


@suite.test("B-T2", "Vibration patterns", requirement="B-R2")
def b_t2(t):
    t.not_implemented()


@suite.test("B-T3", "Disconnect", requirement="B-R4")
def b_t3(t):
    t.not_implemented()


@suite.test("B-T4", "Calibration and signs", requirement="B-R3")
def b_t4(t):
    t.not_implemented()


if __name__ == "__main__":
    suite.main()
