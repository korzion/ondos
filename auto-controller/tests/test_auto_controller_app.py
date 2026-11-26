"""Unit tests for AutoControllerApp (D-R4, IF-06, IF-07) using an in-memory validating bus."""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from auto_controller_app import AutoControllerApp  # noqa: E402
from shared import topics as T  # noqa: E402
from shared.interfaces import validate  # noqa: E402


class FakeBus:
    """In-memory MQTT bus double that enforces shared.interfaces schemas on every publish."""

    def __init__(self, clock_fn) -> None:
        self._clock = clock_fn
        self._seq: dict[str, int] = defaultdict(int)
        self.subs: dict[str, list] = defaultdict(list)
        self.published: list[tuple[str, dict]] = []

    def subscribe(self, pattern: str, callback, accept_replay: bool = False) -> None:
        self.subs[pattern].append((callback, accept_replay))

    def publish(self, topic: str, fields: dict) -> dict:
        info = T.topic_info(topic)
        seq = self._seq[topic]
        self._seq[topic] += 1
        msg = {
            "timestamp_s": self._clock(),
            "seq": seq,
            "version": info["version"],
            "writer": "auto_controller",
            **fields,
        }
        validate(topic, msg)
        self.published.append((topic, msg))
        return msg

    def inject(self, topic: str, fields: dict, t_s: float) -> None:
        info = T.topic_info(topic)
        if info["payload"] == "bool":
            payload = fields
        else:
            seq = fields.get("seq", self._seq[topic])
            self._seq[topic] = max(self._seq[topic], int(seq) + 1)
            payload = {
                "timestamp_s": t_s,
                "seq": seq,
                "version": info["version"],
                "writer": fields.get("writer") or info["writer"],
                **fields,
            }
        validate(topic, payload)
        is_replay = isinstance(payload, dict) and payload.get("writer") == "replay"
        for cb, accept_replay in list(self.subs.get(topic, [])):
            if is_replay and not accept_replay:
                continue
            cb(topic, payload, t_s)

    def clear_published(self) -> None:
        self.published.clear()


class FakeObservationBuilder:
    def build(self, ball, tilt, previous_action, targets):
        return {
            "vx_mm_s": ball["vx_mm_s"],
            "vy_mm_s": ball["vy_mm_s"],
            "tilt_x_deg": tilt["tilt_x_deg"],
            "tilt_y_deg": tilt["tilt_y_deg"],
            "previous_action": tuple(previous_action),
            "targets": list(targets),
        }


class FakeAIController:
    def __init__(self, version: str = "ppo-20261201-1", policy: str = "rl", action=(0.2, -0.3)):
        self.model_version = version
        self.policy = policy
        self.observation_builder = FakeObservationBuilder()
        self.action = action
        self.calls: list[dict] = []

    def load(self, model_version: str | None = None) -> None:
        self.model_version = model_version or "ppo-20261201-2"

    def act(self, observation: dict) -> tuple[float, float]:
        self.calls.append(observation)
        return self.action


def _base_maze() -> dict:
    return {
        "maze_id": "demo",
        "source": "file_checked",
        "cell_size_mm": 40.0,
        "rows": 2,
        "cols": 2,
        "origin_x_mm": -40.0,
        "origin_y_mm": -40.0,
        "walls": [[14, 14], [9, 3]],
        "wall_thickness_mm": 4.0,
        "wall_height_mm": 10.0,
        "start_cell": {"row": 0, "col": 0},
        "exit_cell": {"row": 0, "col": 1},
        "exit_x_mm": 20.0,
        "exit_y_mm": -20.0,
        "exit_radius_mm": 8.0,
        "ball_diameter_mm": 12.0,
    }


def _base_dmap() -> dict:
    return {"maze_id": "demo", "rows": 2, "cols": 2, "steps": [[3, 0], [2, 1]]}


def _base_platform(fault: str = "none", is_e_stop: bool = False) -> dict:
    return {
        "tilt_x_deg": 0.0,
        "tilt_y_deg": 0.0,
        "applied_tilt_x_deg": 0.0,
        "applied_tilt_y_deg": 0.0,
        "source": "ai",
        "mode": "ai",
        "mode_button_presses": 0,
        "is_e_stop": is_e_stop,
        "is_laptop_connected": True,
        "is_glove_connected": False,
        "fault": fault,
    }


def _base_game(state: str = "playing", mode: str = "ai", maze_id: str | None = "demo") -> dict:
    return {
        "state": state,
        "mode": mode,
        "game_id": "20261204-140500",
        "maze_id": maze_id,
        "elapsed_s": 1.0,
        "cell": {"row": 0, "col": 0},
        "distance_to_exit_cells": 3,
        "progress_pct": 0.0,
        "result": "none",
    }


def _base_ball(seq: int = 1, x_mm: float = -20.0, y_mm: float = -20.0, is_visible: bool = True) -> dict:
    return {
        "seq": seq,
        "x_mm": x_mm,
        "y_mm": y_mm,
        "vx_mm_s": 0.0,
        "vy_mm_s": 0.0,
        "is_visible": is_visible,
        "is_predicted": False,
        "is_on_exit": False,
        "frame_age_ms": 15.0,
        "meas_x_mm": x_mm if is_visible else None,
        "meas_y_mm": y_mm if is_visible else None,
    }


def _base_route(ball_seq: int = 1, maze_id: str = "demo", status: str = "valid") -> dict:
    return {
        "maze_id": maze_id,
        "ball_seq": ball_seq,
        "status": status,
        "ball_cell": {"row": 0, "col": 0},
        "target_points_mm": [[-20.0, 20.0], [20.0, 20.0]] if status == "valid" else [],
        "distance_to_exit_cells": 3 if status == "valid" else None,
    }


def _setup_app(ai_ctrl=None):
    now = [1000.0]
    bus = FakeBus(lambda: now[0])
    app = AutoControllerApp(
        bus=bus,
        ai_controller=ai_ctrl,
        clock=lambda: now[0],
        load_default_model=False,
    )
    app.start()
    return now, bus, app


def test_d_t4_fixture_gating_end_to_end() -> None:
    now, bus, _ = _setup_app(FakeAIController())
    bus.clear_published()

    d_t4_dir = MODULE_DIR / "fixtures/D-T4"
    fixture_lines = [
        json.loads(line)
        for line in (d_t4_dir / "input.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_data = json.loads((d_t4_dir / "expected.json").read_text(encoding="utf-8"))
    base_t = 1000.0
    for entry in fixture_lines:
        now[0] = base_t + float(entry["t_s"])
        bus.inject(entry["topic"], entry["msg"], now[0])

    mode_to_topic = {"ai": T.AI_TARGET_TILT, "simple": T.CONTROL_TARGET_TILT}
    expected = [
        (mode_to_topic[item["mode"]], item["ball_seq"], item["maze_id"])
        for item in expected_data["expected_commands"]
    ]
    max_tilt_deg = float(expected_data["max_tilt_deg"])
    cmds = [(topic, msg) for topic, msg in bus.published if topic in (T.AI_TARGET_TILT, T.CONTROL_TARGET_TILT)]
    got = [(topic, msg["ball_seq"], msg["maze_id"]) for topic, msg in cmds]
    assert got == expected, f"unexpected commands: {got}"
    for _, msg in cmds:
        assert abs(msg["target_tilt_x_deg"]) <= max_tilt_deg and abs(msg["target_tilt_y_deg"]) <= max_tilt_deg


def test_variables_spec_clamping_and_deferred_model_version() -> None:
    ai = FakeAIController("ppo-20261201-1")
    now, bus, app = _setup_app(ai)

    specs = {topic: msg for topic, msg in bus.published}
    assert T.variables_spec("ai") in specs and T.variables_spec("pid") in specs

    bus.inject(T.GAME_STATE, _base_game(state="playing", mode="ai"), now[0])
    bus.inject(T.cs_variables("ai"), {"action_smoothing_pct": 999.0, "tilt_scale_pct": -5.0, "model_version": "ppo-20261201-2"}, now[0])
    assert app._ai_settings["action_smoothing_pct"] == 100.0
    assert app._ai_settings["tilt_scale_pct"] == 10.0
    assert ai.model_version == "ppo-20261201-1"  # deferred while playing

    bus.inject(T.GAME_STATE, _base_game(state="ready", mode="ai"), now[0])
    assert ai.model_version == "ppo-20261201-2"  # applied between games

    bus.inject(T.cs_variables("pid"), {"pid_kp_deg_per_mm": 50.0, "pid_integral_limit_deg": -2.0}, now[0])
    assert app._pid.settings["pid_kp_deg_per_mm"] == 2.0
    assert app._pid.settings["pid_integral_limit_deg"] == 0.0


def test_status_transitions_and_vision_offline() -> None:
    now, bus, app = _setup_app(None)  # no AI model loaded

    assert app.tick()["status"] == "stale_game"

    bus.inject(T.GAME_STATE, _base_game(state="ready", mode="ai"), now[0])
    assert app.tick()["status"] == "idle"

    bus.inject(T.GAME_STATE, _base_game(state="playing", mode="ai"), now[0])
    assert app.tick()["status"] == "stale_platform"

    bus.inject(T.variables_spec("platform"), {"variables": [{"name": "max_tilt_deg", "value": 8.0, "default": 8.0, "min": 0.0, "max": 15.0, "choices": None, "is_live": True, "description": "limit"}]}, now[0])
    bus.inject(T.PLATFORM_STATE, _base_platform(is_e_stop=True), now[0])
    assert app.tick()["status"] == "e_stop"

    bus.inject(T.PLATFORM_STATE, _base_platform(fault="imu"), now[0])
    assert app.tick()["status"] == "fault"

    bus.inject(T.PLATFORM_STATE, _base_platform(), now[0])
    assert app.tick()["status"] == "ball_lost"

    bus.inject(T.VISION_BALL, _base_ball(seq=1), now[0])
    assert app.tick()["status"] == "no_maze"

    bus.inject(T.VISION_MAZE, _base_maze(), now[0])
    bus.inject(T.PLAN_DISTANCE_MAP, _base_dmap(), now[0])
    assert app.tick()["status"] == "no_path"

    bus.inject(T.PLAN_ROUTE, _base_route(ball_seq=1), now[0])
    status = app.tick()
    assert status["status"] == "no_model" and status["active_controller"] == "ai"

    bus.inject(T.sys_online("vision"), False, now[0])
    assert app.tick()["status"] == "ball_lost"


def test_pid_resets_on_pause_and_previous_action_resets_in_ai() -> None:
    ai = FakeAIController(action=(0.5, -0.5))
    now, bus, app = _setup_app(ai)
    bus.inject(T.variables_spec("platform"), {"variables": [{"name": "max_tilt_deg", "value": 10.0, "default": 10.0, "min": 0.0, "max": 15.0, "choices": None, "is_live": True, "description": "limit"}]}, now[0])
    bus.inject(T.VISION_MAZE, _base_maze(), now[0])
    bus.inject(T.PLAN_DISTANCE_MAP, _base_dmap(), now[0])

    # PID builds integral over two samples, then pauses -> integral resets
    bus.inject(T.GAME_STATE, _base_game(state="playing", mode="simple"), now[0])
    bus.inject(T.PLATFORM_STATE, _base_platform(), now[0])
    bus.inject(T.VISION_BALL, _base_ball(seq=1), now[0])
    bus.inject(T.PLAN_ROUTE, _base_route(ball_seq=1), now[0])

    now[0] += 0.05
    bus.inject(T.GAME_STATE, _base_game(state="playing", mode="simple"), now[0])
    bus.inject(T.PLATFORM_STATE, _base_platform(), now[0])
    bus.inject(T.VISION_BALL, _base_ball(seq=2), now[0])
    bus.inject(T.PLAN_ROUTE, _base_route(ball_seq=2), now[0])
    assert app._pid._integral_term_deg != [0.0, 0.0]

    now[0] += 0.02
    bus.inject(T.GAME_STATE, _base_game(state="paused", mode="simple"), now[0])
    assert app._pid._integral_term_deg == [0.0, 0.0]
    assert app._previous_ball_ts is None

    # AI stores previous published tilt and resets it to (0, 0) on mode/state reset
    bus.inject(T.GAME_STATE, _base_game(state="playing", mode="ai"), now[0])
    bus.inject(T.PLATFORM_STATE, _base_platform(), now[0])
    bus.inject(T.VISION_BALL, _base_ball(seq=3), now[0])
    bus.inject(T.PLAN_ROUTE, _base_route(ball_seq=3), now[0])
    assert app._previous_action == (5.0, -5.0)
    bus.inject(T.GAME_STATE, _base_game(state="paused", mode="ai"), now[0])
    assert app._previous_action == (0.0, 0.0)


def test_non_finite_ball_or_ai_action_never_crashes_or_publishes() -> None:
    ai = FakeAIController(action=(math.nan, 0.0))
    now, bus, app = _setup_app(ai)
    bus.inject(T.variables_spec("platform"), {"variables": [{"name": "max_tilt_deg", "value": 10.0, "default": 10.0, "min": 0.0, "max": 15.0, "choices": None, "is_live": True, "description": "limit"}]}, now[0])
    bus.inject(T.VISION_MAZE, _base_maze(), now[0])
    bus.inject(T.PLAN_DISTANCE_MAP, _base_dmap(), now[0])
    bus.inject(T.GAME_STATE, _base_game(state="playing", mode="ai"), now[0])
    bus.inject(T.PLATFORM_STATE, _base_platform(), now[0])
    bus.clear_published()

    # Non-finite AI action is caught cleanly
    bus.inject(T.VISION_BALL, _base_ball(seq=1), now[0])
    bus.inject(T.PLAN_ROUTE, _base_route(ball_seq=1), now[0])
    assert not bus.published

    # Non-finite ball velocity in PID mode is caught cleanly
    bus.inject(T.GAME_STATE, _base_game(state="playing", mode="simple"), now[0])
    bad_ball = _base_ball(seq=2)
    bad_ball["vx_mm_s"] = math.nan
    bus.subs[T.VISION_BALL][0][0](T.VISION_BALL, {**bad_ball, "timestamp_s": now[0], "version": 1, "writer": "vision"}, now[0])
    bus.inject(T.PLAN_ROUTE, _base_route(ball_seq=2), now[0])
    assert not bus.published


if __name__ == "__main__":
    tests = [
        test_d_t4_fixture_gating_end_to_end,
        test_variables_spec_clamping_and_deferred_model_version,
        test_status_transitions_and_vision_offline,
        test_pid_resets_on_pause_and_previous_action_resets_in_ai,
        test_non_finite_ball_or_ai_action_never_crashes_or_publishes,
    ]
    for fn in tests:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"AutoControllerApp unit tests: PASS ({len(tests)}/{len(tests)})")
