"""Tests of D · Auto Controller (design document D.9).

    python run_test.py --list
    python run_test.py <TEST-ID> [--input DIR]

Inputs are in fixtures/<TEST-ID>/. Each test prints PASS or FAIL for every check;
see shared/testing/runner.py for the helpers (check, load_json, play_fixture, observe, checklist).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR.parent))         # repo root, for `import shared`
sys.path.insert(0, str(MODULE_DIR))                # this folder, also when Python runs in safe-path mode

from ai.recording_reader import RecordingReader    # noqa: E402
from pid_controller import PIDController           # noqa: E402
from shared import topics as T                     # noqa: E402
from shared.interfaces import ValidationError, validate, validate_file  # noqa: E402
from shared.testing import TestSuite               # noqa: E402

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


def _latest_raw_at_or_before(sorted_entries, topic, t_limit):
    found = None
    for t_recv, _, entry_topic, msg in sorted_entries:
        if t_recv > t_limit:
            break
        if entry_topic == topic and not (isinstance(msg, dict) and msg.get("writer") == "replay"):
            found = (t_recv, msg)
    return found


def _raw_route_for_ball_seq(sorted_entries, ball_seq, t_ball):
    candidates = [
        (t_recv, msg)
        for t_recv, _, entry_topic, msg in sorted_entries
        if entry_topic == T.PLAN_ROUTE
        and not (isinstance(msg, dict) and msg.get("writer") == "replay")
        and msg.get("ball_seq") == ball_seq
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(item[0] - t_ball))


def _maze_transitions_are_contiguous(rows):
    """Return (is_contiguous, ordered_maze_ids) ensuring no row reverts to an earlier maze."""
    seen = []
    for row in rows:
        if not seen or seen[-1] != row.maze_id:
            if row.maze_id in seen:
                return False, seen + [row.maze_id]
            seen.append(row.maze_id)
    return True, seen


@suite.test("D-T6", "Training rows", requirement="D-R6")
def d_t6(t):
    rec_path = t.fixture_dir / "recording_maze_change.jsonl"
    if not rec_path.exists():
        candidates = sorted(t.fixture_dir.glob("*.jsonl"))
        if not candidates:
            raise FileNotFoundError(f"{t.test_id}: no *.jsonl recording found in {t.fixture_dir}")
        rec_path = candidates[0]

    raw_lines = [line for line in rec_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    t.check("recording file has header and data lines", len(raw_lines) >= 2, f"{len(raw_lines)} lines")
    if len(raw_lines) < 2:
        return

    schema_ok = True
    schema_err = ""
    raw_entries = []
    try:
        header = json.loads(raw_lines[0])
        validate_file("recording_header", header)
        for line_no, raw in enumerate(raw_lines[1:], start=2):
            entry = json.loads(raw)
            validate_file("recording_line", entry)
            validate(entry["topic"], entry["msg"])
            raw_entries.append((float(entry["t_recv_s"]), line_no, entry["topic"], entry["msg"]))
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        schema_ok = False
        schema_err = str(exc)
    t.check("recording header and lines match IF-09 schemas", schema_ok, schema_err)
    if not schema_ok:
        return

    reader = RecordingReader()
    loaded = reader.load(rec_path)
    rows = reader.training_rows()
    all_rows = reader.training_rows(include_stale_platform=True)
    imit_rows = reader.imitation_rows()

    t.check("produced clean training rows", len(rows) > 0, f"{len(rows)} kept rows")

    # 1. Context causality: joined state/maze/platform messages come from t_recv_s <= ball t_recv_s.
    causal_violations = [
        r.ball_seq
        for r in all_rows
        if (
            r.t_game_state_s > r.t_recv_s
            or r.t_platform_state_s > r.t_recv_s
            or r.t_maze_s > r.t_recv_s
            or r.t_distance_map_s > r.t_recv_s
        )
    ]
    t.check("causal context timestamps (t_ctx <= t_recv_s)", not causal_violations, f"violations={causal_violations}")

    # 2. Route parity + 3. No maze mixing + 4. Freshness and IF-09 label provenance verified against raw file.
    sorted_entries = sorted(raw_entries, key=lambda item: (item[0], item[1]))
    maze_mix_errors = []
    label_or_fresh_errors = []
    for r in rows:
        g_snap = _latest_raw_at_or_before(sorted_entries, T.GAME_STATE, r.t_recv_s)
        m_snap = _latest_raw_at_or_before(sorted_entries, T.VISION_MAZE, r.t_recv_s)
        dm_snap = _latest_raw_at_or_before(sorted_entries, T.PLAN_DISTANCE_MAP, r.t_recv_s)
        rt_snap = _raw_route_for_ball_seq(sorted_entries, r.ball_seq, r.t_recv_s)
        p_snap = _latest_raw_at_or_before(sorted_entries, T.PLATFORM_STATE, r.t_recv_s)

        if not (g_snap and m_snap and dm_snap and rt_snap and p_snap):
            maze_mix_errors.append(f"seq {r.ball_seq}: missing raw snapshot")
            continue

        tg, g = g_snap
        tm, m = m_snap
        tdm, dm = dm_snap
        trt, rt = rt_snap
        tp, p = p_snap

        if (
            tg != r.t_game_state_s
            or tm != r.t_maze_s
            or tdm != r.t_distance_map_s
            or trt != r.t_route_s
            or tp != r.t_platform_state_s
        ):
            maze_mix_errors.append(f"seq {r.ball_seq}: joined timestamp mismatch")

        if (
            r.route_ball_seq != r.ball_seq
            or g["state"] != "playing"
            or g["maze_id"] != r.maze_id
            or m["maze_id"] != r.maze_id
            or dm["maze_id"] != r.maze_id
            or rt["maze_id"] != r.maze_id
            or rt["status"] != "valid"
        ):
            maze_mix_errors.append(f"seq {r.ball_seq}: maze/route/state mismatch")

        if (
            r.platform_age_ms > T.CONTROLLER_INPUT_MAX_AGE_MS
            or r.route_age_ms > T.CONTROLLER_INPUT_MAX_AGE_MS
            or abs(trt - r.t_recv_s) * 1000.0 > T.CONTROLLER_INPUT_MAX_AGE_MS
            or r.game_state_age_ms > T.GAME_STATE_MAX_AGE_MS
            or r.applied_tilt_x_deg != float(p["applied_tilt_x_deg"])
            or r.applied_tilt_y_deg != float(p["applied_tilt_y_deg"])
            or r.mode != g["mode"]
        ):
            label_or_fresh_errors.append(f"seq {r.ball_seq}: freshness/label/mode mismatch")

    t.check("no cross-maze mixing and exact route ball_seq match", not maze_mix_errors, str(maze_mix_errors[:3]))
    t.check("fresh inputs, applied_tilt label, and game/state.mode", not label_or_fresh_errors, str(label_or_fresh_errors[:3]))

    # 5. Stale platform rows are marked and excluded from default and imitation rows.
    clean_seqs = {r.ball_seq for r in rows}
    imit_seqs = {r.ball_seq for r in imit_rows}
    stale_ok = True
    stale_detail = []
    for r in all_rows:
        if r.platform_age_ms > T.CONTROLLER_INPUT_MAX_AGE_MS:
            if not r.is_platform_stale or r.is_usable_for_imitation or r.ball_seq in clean_seqs or r.ball_seq in imit_seqs:
                stale_ok = False
                stale_detail.append(r.ball_seq)
    expected_imit_seqs = {r.ball_seq for r in rows if r.source in ("glove", "ai", "simple")}
    if imit_seqs != expected_imit_seqs:
        stale_ok = False
        stale_detail.append("imitation_rows filter mismatch")
    t.check("stale platform rows marked and excluded from training/imitation", stale_ok, f"bad={stale_detail}")

    # 6. Contiguous maze transitions without reverting.
    is_contiguous, seen_mazes = _maze_transitions_are_contiguous(rows)
    t.check("maze transitions stay contiguous without reverting", is_contiguous, f"mazes={seen_mazes}")

    # 7. Hand-checked expected fixture comparison (when expected.json is provided).
    expected_path = t.fixture_dir / "expected.json"
    if expected_path.exists():
        expected = t.load_json("expected.json")
        actual_rows = [
            {
                "ball_seq": r.ball_seq,
                "maze_id": r.maze_id,
                "mode": r.mode,
                "applied_tilt_x_deg": r.applied_tilt_x_deg,
                "applied_tilt_y_deg": r.applied_tilt_y_deg,
                "target_points_mm": r.target_points_mm,
            }
            for r in rows
        ]
        actual_stale_seqs = sorted(r.ball_seq for r in all_rows if r.is_platform_stale)
        t.check("maze_ids match expected.json", seen_mazes == expected["maze_ids"], f"{seen_mazes} vs {expected['maze_ids']}")
        t.check("kept training rows match expected.json", actual_rows == expected["kept_rows"], f"{len(actual_rows)} vs {len(expected['kept_rows'])}")
        t.check("stale-marked rows match expected.json", actual_stale_seqs == expected["stale_platform_ball_seqs"], f"{actual_stale_seqs} vs {expected['stale_platform_ball_seqs']}")
        t.check("excluded counts match expected.json", loaded.stats.excluded == expected["excluded"], f"{loaded.stats.excluded}")


@suite.test("D-T7", "Signs", requirement="D-R7")
def d_t7(t):
    t.not_implemented()


if __name__ == "__main__":
    suite.main()
