"""Tests of E · Control Station (design document E.9).

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


@suite.test("E-T1", "Plot rate", requirement="E-R1")
def e_t1(t):
    t.not_implemented()


@suite.test("E-T2", "Button states", requirement="E-R2")
def e_t2(t):
    t.not_implemented()


@suite.test("E-T3", "Commands", requirement="E-R2")
def e_t3(t):
    t.not_implemented()


@suite.test("E-T4", "E-stop not confirmed", requirement="E-R2")
def e_t4(t):
    t.not_implemented()


@suite.test("E-T5", "Variables", requirement="E-R3")
def e_t5(t):
    t.not_implemented()


@suite.test("E-T6", "Missing data", requirement="E-R4")
def e_t6(t):
    t.not_implemented()


@suite.test("E-T7", "Recording", requirement="E-R5")
def e_t7(t):
    t.not_implemented()


@suite.test("E-T8", "No replay in the recording", requirement="E-R5")
def e_t8(t):
    t.not_implemented()


@suite.test("E-T9", "Camera and 3D", requirement="E-R6")
def e_t9(t):
    t.not_implemented()


@suite.test("E-T10", "Game states", requirement="E-R7")
def e_t10(t):
    t.not_implemented()


@suite.test("E-T11", "Finish", requirement="E-R8")
def e_t11(t):
    t.not_implemented()


@suite.test("E-T12", "Heartbeat", requirement="E-R9")
def e_t12(t):
    t.not_implemented()


@suite.test("E-T13", "Warnings", requirement="E-R10")
def e_t13(t):
    t.not_implemented()


@suite.test("E-T14", "3D Twin", requirement="E-R6")
def e_t14(t):
    t.not_implemented()


@suite.test("E-T15", "Safe replay", requirement="E-R11")
def e_t15(t):
    t.not_implemented()


@suite.test("E-T16", "Windows and Linux", requirement="E-R12")
def e_t16(t):
    t.not_implemented()


if __name__ == "__main__":
    suite.main()
