"""Tests of D · Auto Controller (design document D.9).

    python run_test.py --list
    python run_test.py <TEST-ID> [--input DIR]

Inputs are in fixtures/<TEST-ID>/. Each test prints PASS or FAIL for every check;
see shared/testing/runner.py for the helpers (check, load_json, play_fixture, observe, checklist).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for `import shared`

from pid_controller import PIDController  # noqa: E402
from shared import topics as T  # noqa: E402
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


# ---------------------------------------------------------------- D-T5
MAX_TILT_NAME = "max_tilt_deg"
REFERENCE_MAX_STEP_S = T.CONTROLLER_INPUT_MAX_AGE_MS / 1000.0
AXES = (("x_mm", "vx_mm_s"), ("y_mm", "vy_mm_s"))


def reference_pid_outputs(steps: list[dict], settings: dict) -> list[tuple[float, float] | None]:
    """D.5 formula written out step by step, independent of PIDController.

    Returns one (tilt_x_deg, tilt_y_deg) per ball step and None for a reset step.
    """
    kp = settings["pid_kp_deg_per_mm"]
    ki = settings["pid_ki_deg_per_mm_per_s"]
    kd = settings["pid_kd_deg_per_mm_s"]
    integral_limit = settings["pid_integral_limit_deg"]
    max_tilt = settings[MAX_TILT_NAME]
    integral = [0.0, 0.0]
    previous_time_s = None
    outputs: list[tuple[float, float] | None] = []
    for step in steps:
        if step.get("reset"):
            integral = [0.0, 0.0]
            previous_time_s = None
            outputs.append(None)
            continue
        ball, target = step["ball"], step["target_points_mm"][0]
        dt = 0.0
        if previous_time_s is not None and ball["timestamp_s"] > previous_time_s:
            dt = min(ball["timestamp_s"] - previous_time_s, REFERENCE_MAX_STEP_S)
        previous_time_s = ball["timestamp_s"]
        tilt = []
        for axis, (position_field, velocity_field) in enumerate(AXES):
            error = target[axis] - ball[position_field]
            p_term = kp * error
            d_term = -kd * ball[velocity_field]
            new_integral = max(-integral_limit, min(integral_limit, integral[axis] + ki * error * dt))
            unclamped = p_term + new_integral + d_term
            saturated = unclamped > max_tilt or unclamped < -max_tilt
            pushes_further = (new_integral - integral[axis]) * unclamped > 0
            if not (saturated and pushes_further):
                integral[axis] = new_integral
            tilt.append(max(-max_tilt, min(max_tilt, p_term + integral[axis] + d_term)))
        outputs.append((tilt[0], tilt[1]))
    return outputs


def run_pid_controller(steps: list[dict], settings: dict) -> list[tuple[float, float] | None]:
    """Feed the steps to PIDController as AutoControllerApp would: dt from consecutive timestamp_s."""
    controller = PIDController(settings, settings[MAX_TILT_NAME])
    previous_time_s = None
    outputs: list[tuple[float, float] | None] = []
    for step in steps:
        if step.get("reset"):
            controller.reset()
            previous_time_s = None
            outputs.append(None)
            continue
        ball = step["ball"]
        dt_s = None if previous_time_s is None else ball["timestamp_s"] - previous_time_s
        previous_time_s = ball["timestamp_s"]
        outputs.append(controller.compute(ball, step["target_points_mm"][0], dt_s))
    return outputs


def is_close(got: tuple[float, float], expected: list[float], tolerance: float) -> bool:
    return all(abs(g - e) <= tolerance for g, e in zip(got, expected))


@suite.test("D-T5", "PID output", requirement="D-R5")
def d_t5(t):
    fixture = t.load_json("sequences.json")
    tolerance = fixture["tolerance_deg"]
    for sequence in fixture["sequences"]:
        name = sequence["name"]
        settings = {**fixture["settings"], **sequence.get("settings", {})}
        steps = sequence["steps"]
        got = run_pid_controller(steps, settings)
        reference = reference_pid_outputs(steps, settings)

        ball_steps = [i for i, out in enumerate(got) if out is not None]
        mismatches = [i for i in ball_steps if not is_close(got[i], reference[i], tolerance)]
        t.check(f"{name}: outputs match the D.5 formula", not mismatches,
                f"step {mismatches[0] + 1}: got {got[mismatches[0]]}, reference {reference[mismatches[0]]}"
                if mismatches else f"{len(ball_steps)} steps")

        max_tilt = settings[MAX_TILT_NAME]
        out_of_bounds = [i for i in ball_steps if any(abs(v) > max_tilt for v in got[i])]
        t.check(f"{name}: outputs within +/-{max_tilt} deg", not out_of_bounds,
                f"step {out_of_bounds[0] + 1}: {got[out_of_bounds[0]]}" if out_of_bounds else "")

        for i, step in enumerate(steps):
            if "expected_tilt_deg" not in step:
                continue
            expected = step["expected_tilt_deg"]
            label = step.get("note", "fixed value")
            t.check(f"{name} step {i + 1}: {label}", is_close(got[i], expected, tolerance),
                    f"got ({got[i][0]:.6f}, {got[i][1]:.6f}), expected {expected}")


@suite.test("D-T6", "Training rows", requirement="D-R6")
def d_t6(t):
    t.not_implemented()


@suite.test("D-T7", "Signs", requirement="D-R7")
def d_t7(t):
    t.not_implemented()


if __name__ == "__main__":
    suite.main()
