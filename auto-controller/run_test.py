"""Tests of D · Auto Controller (design document D.9).

    python run_test.py --list
    python run_test.py <TEST-ID> [--input DIR]

Inputs are in fixtures/<TEST-ID>/. Each test prints PASS or FAIL for every check;
see shared/testing/runner.py for the helpers (check, load_json, play_fixture, observe, checklist).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for `import shared`
sys.path.insert(0, str(Path(__file__).resolve().parent))  # this folder, also when Python runs in safe-path mode

from pid_controller import PIDController  # noqa: E402
from shared import topics as T  # noqa: E402
from shared.interfaces import ValidationError, validate, validate_file  # noqa: E402
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


_D_T4_OBSERVE_TAIL_S = 0.6
_MODE_TO_TARGET_TOPIC = {
    "ai": T.AI_TARGET_TILT,
    "simple": T.CONTROL_TARGET_TILT,
}


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _load_d_t4_expected(t) -> tuple[dict[int, tuple[str, str, float]], set[int]]:
    data = t.load_json("expected.json")
    max_tilt_deg = float(data["max_tilt_deg"])
    expected = {
        int(item["ball_seq"]): (_MODE_TO_TARGET_TOPIC[item["mode"]], item["maze_id"], max_tilt_deg)
        for item in data["expected_commands"]
    }
    blocked = {int(seq) for seq in data["blocked_ball_seqs"]}
    return expected, blocked


def _validate_d_t4_fixture(lines: list[dict]) -> tuple[bool, str]:
    seq_counters: dict[str, int] = {}
    for line_no, entry in enumerate(lines, start=1):
        try:
            validate_file("fixture_line", entry)
            info = T.topic_info(entry["topic"])
            msg = entry["msg"]
            if info["payload"] == "json":
                if not isinstance(msg, dict):
                    return False, f"line {line_no}: JSON topic msg must be an object"
                writer = msg.get("writer") or info["writer"]
                seq_counters[entry["topic"]] = seq_counters.get(entry["topic"], 0) + 1
                full = {
                    "timestamp_s": float(entry["t_s"]),
                    "seq": seq_counters[entry["topic"]],
                    "version": info["version"],
                    "writer": writer,
                    **msg,
                }
                validate(entry["topic"], full)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            return False, f"line {line_no}: {exc}"
    return True, f"{len(lines)} fixture lines valid"


def _inspect_d_t4_commands(
    cmd_msgs: list[tuple[str, dict]],
    expected: dict[int, tuple[str, str, float]],
) -> tuple[list[str], list[str], list[tuple[str, int]], list[tuple[int, str, str]], dict[int, tuple[str, str]]]:
    schema_errors: list[str] = []
    bound_errors: list[str] = []
    forbidden_hits: list[tuple[str, int]] = []
    wrong_topic_hits: list[tuple[int, str, str]] = []
    answered: dict[int, tuple[str, str]] = {}

    for topic, msg in cmd_msgs:
        try:
            validate(topic, msg)
        except ValidationError as exc:
            schema_errors.append(f"{topic}: {exc}")
            continue
        seq = int(msg["ball_seq"])
        if seq not in expected:
            forbidden_hits.append((topic, seq))
            continue
        exp_topic, exp_maze_id, max_tilt_deg = expected[seq]
        x_deg, y_deg = msg["target_tilt_x_deg"], msg["target_tilt_y_deg"]
        if not _is_finite_number(x_deg) or not _is_finite_number(y_deg) or abs(x_deg) > max_tilt_deg or abs(y_deg) > max_tilt_deg:
            bound_errors.append(f"seq {seq}: ({x_deg}, {y_deg}) exceeds +/-{max_tilt_deg}")
        if topic != exp_topic or msg["maze_id"] != exp_maze_id:
            wrong_topic_hits.append((seq, topic, exp_topic))
        answered[seq] = (topic, msg["maze_id"])

    return schema_errors, bound_errors, forbidden_hits, wrong_topic_hits, answered


def _has_loaded_ai_model(observed: list[tuple[str, object, float]]) -> bool:
    spec_topic = T.variables_spec("ai")
    for topic, msg, _ in observed:
        if topic != spec_topic or not isinstance(msg, dict):
            continue
        for var in msg.get("variables", []):
            if var.get("name") == "model_version":
                val = var.get("value")
                return isinstance(val, str) and bool(val) and val != "none"
    return False


def _find_d_t4_fixture_path(t) -> Path:
    fixture_path = t.fixture_dir / "input.jsonl"
    if fixture_path.exists():
        return fixture_path
    candidates = sorted(t.fixture_dir.glob("*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"{t.test_id}: no *.jsonl fixture found in {t.fixture_dir}")
    return candidates[0]


@suite.test("D-T4", "Only valid commands", requirement="D-R4")
def d_t4(t):
    fixture_path = _find_d_t4_fixture_path(t)
    lines = t.load_jsonl(fixture_path.name)
    schema_ok, schema_detail = _validate_d_t4_fixture(lines)
    t.check("fixture lines pass IF-09 and topic schemas", bool(lines) and schema_ok, schema_detail)
    if not lines or not schema_ok:
        return

    expected, blocked = _load_d_t4_expected(t)
    t.check("fixture covers valid and blocked cases", bool(expected) and bool(blocked),
            f"{len(expected)} expected, {len(blocked)} blocked")

    t.require_broker()
    duration_s = max(float(entry["t_s"]) for entry in lines) + _D_T4_OBSERVE_TAIL_S
    observed = t.observe(
        [T.AI_TARGET_TILT, T.CONTROL_TARGET_TILT, T.AI_STATUS, T.variables_spec("ai")],
        duration_s,
        start=lambda: t.play_fixture(fixture_path.name),
    )

    status_msgs = [msg for topic, msg, _ in observed if topic == T.AI_STATUS and isinstance(msg, dict)]
    t.check("auto_controller runtime published ai/status", len(status_msgs) > 0, f"{len(status_msgs)} status msgs")

    has_model = _has_loaded_ai_model(observed)
    active_expected = expected if has_model else {seq: val for seq, val in expected.items() if val[0] != T.AI_TARGET_TILT}
    cmd_msgs = [(topic, msg) for topic, msg, _ in observed if topic in (T.AI_TARGET_TILT, T.CONTROL_TARGET_TILT)]
    schema_errors, bound_errors, forbidden_hits, wrong_topic_hits, answered = _inspect_d_t4_commands(cmd_msgs, active_expected)

    t.check("published commands pass IF-06 schemas", not schema_errors, str(schema_errors[:3]))
    t.check("published tilts finite and within +/-max_tilt_deg", not bound_errors, str(bound_errors[:3]))
    t.check("zero commands on blocked/stale/invalid/wrong-mode cases", not forbidden_hits and not wrong_topic_hits,
            f"forbidden={forbidden_hits[:3]}, wrong_topic={wrong_topic_hits[:3]}")
    missing = sorted(set(active_expected) - set(answered))
    t.check("all valid samples answered on the selected mode topic", not missing, f"missing={missing}, model_loaded={has_model}")
    if not has_model:
        no_model_seen = any(m.get("status") == "no_model" for m in status_msgs)
        t.check("ai mode reports no_model when no model is loaded", no_model_seen,
                f"statuses={sorted({m.get('status') for m in status_msgs})}")


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
