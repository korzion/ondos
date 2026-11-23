"""Tests of E · Control Station (design document E.9).

    python run_test.py --list
    python run_test.py <TEST-ID> [--input DIR]

Inputs are in fixtures/<TEST-ID>/. Each test prints PASS or FAIL for every check;
see shared/testing/runner.py for the helpers (check, load_json, play_fixture, observe, checklist).
"""
import json
import math
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for `import shared`

from shared import topics as T  # noqa: E402
from shared.testing import TestSuite  # noqa: E402

suite = TestSuite(__file__)

MODULE_DIR = Path(__file__).resolve().parent
EXAMPLE_MESSAGES = MODULE_DIR.parent / "shared" / "interfaces" / "examples" / "messages.json"
ENVELOPE_FIELDS = ("timestamp_s", "seq", "version", "writer")  # filled in by the playback tool
S_PER_MS = 0.001

# E-T1: the two fields of each plotted topic that the fixture moves (the ones PlotsTab draws).
MOVING_FIELDS = {
    T.VISION_BALL: ("x_mm", "y_mm"),
    T.PLATFORM_STATE: ("tilt_x_deg", "tilt_y_deg"),
    T.GLOVE_STATE: ("hand_tilt_x_deg", "hand_tilt_y_deg"),
    T.CONTROL_TARGET_TILT: ("target_tilt_x_deg", "target_tilt_y_deg"),
}
FIXTURE_AMPLITUDE = 20.0
FIXTURE_PERIOD_S = 8.0


def example_payload(topic: str) -> dict:
    """The valid example message of a topic, without the envelope the playback tool adds."""
    examples = json.loads(EXAMPLE_MESSAGES.read_text(encoding="utf-8"))["examples"]
    msg = next(e["msg"] for e in examples if e["topic"] == topic)
    return {k: v for k, v in msg.items() if k not in ENVELOPE_FIELDS}


def e_t1_fixture_lines(params: dict) -> list[dict]:
    """Fixture lines for the playback tool: every plotted topic moves on a slow circle."""
    lines = []
    for topic, rate_hz in params["publish_rates_hz"].items():
        x_field, y_field = MOVING_FIELDS[topic]
        payload = example_payload(topic)
        for i in range(int(params["play_duration_s"] * rate_hz)):
            t_s = i / rate_hz
            phase = 2 * math.pi * t_s / FIXTURE_PERIOD_S
            msg = {**payload, x_field: FIXTURE_AMPLITUDE * math.sin(phase), y_field: FIXTURE_AMPLITUDE * math.cos(phase)}
            lines.append({"t_s": t_s, "topic": topic, "msg": msg})
    return lines


def play_e_t1_fixture(t, params: dict) -> tuple[float, float]:
    """Play the generated game on the broker. Returns the wall-clock start and end (epoch s)."""
    from shared.tools.replay import play_fixture  # needs paho, so not imported for `--list`

    t.require_broker()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "input.jsonl"
        path.write_text("\n".join(json.dumps(line) for line in e_t1_fixture_lines(params)), encoding="utf-8")
        start_s = time.time()
        play_fixture(path, t.host, t.port)
    return start_s, time.time()


def read_draw_log(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"draw log {path} not found: was the app started with ONDOS_DRAW_LOG?")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_plot_draws(t, topic: str, draws: list[dict], start_s: float, params: dict) -> None:
    """The E-R1 checks of one plot: draw rate, longest gap, axis width and data span."""
    if not t.check(f"{topic}: plot was redrawn", len(draws) >= 2, f"{len(draws)} draws"):
        return
    times_s = [d["t_s"] for d in draws]
    rate_hz = (len(draws) - 1) / (times_s[-1] - times_s[0])
    gap_ms = max(b - a for a, b in zip(times_s, times_s[1:])) / S_PER_MS
    t.check(f"{topic}: mean draw rate", abs(rate_hz - params["plot_rate_hz"]) <= params["plot_rate_tolerance_hz"],
            f"{rate_hz:.1f} Hz, wanted {params['plot_rate_hz']} ± {params['plot_rate_tolerance_hz']}")
    t.check(f"{topic}: longest gap between draws", gap_ms <= params["max_draw_gap_ms"],
            f"{gap_ms:.0f} ms, at most {params['max_draw_gap_ms']}")

    settled = [d for d in draws if d["t_s"] >= start_s + params["plot_window_s"]]
    if not t.check(f"{topic}: plot still drawn after the first {params['plot_window_s']} s", bool(settled)):
        return
    width_error_s = max(abs(d["x_max_s"] - d["x_min_s"] - params["plot_window_s"]) for d in settled)
    span_s = min(d["x_max_s"] - d["oldest_s"] for d in settled)
    t.check(f"{topic}: time axis width", width_error_s <= params["plot_window_tolerance_s"],
            f"off by {width_error_s:.3f} s, allowed {params['plot_window_tolerance_s']}")
    t.check(f"{topic}: data covers the window", span_s >= params["min_data_span_s"],
            f"{span_s:.1f} s of data, at least {params['min_data_span_s']}")


@suite.test("E-T1", "Plot rate", requirement="E-R1")
def e_t1(t):
    params = t.load_json("params.json")
    log_path = MODULE_DIR / params["draw_log_path"]
    t.checklist([f"App started with ONDOS_DRAW_LOG={log_path} and the Plots tab is open, window visible"])
    if not all(c.ok for c in t.checks):
        return
    start_s, end_s = play_e_t1_fixture(t, params)
    log = read_draw_log(log_path)
    for topic in params["publish_rates_hz"]:
        # Draws with no samples (the empty chart built when the tab opens) are not updates.
        draws = [d for d in log if d["plot"] == topic and d["points"] > 0 and start_s <= d["t_s"] <= end_s]
        check_plot_draws(t, topic, draws, start_s, params)


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
