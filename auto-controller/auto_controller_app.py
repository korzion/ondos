"""Runtime coordinator of D · Auto Controller (design document D.5, D.7, D.8, IF-06)."""
from __future__ import annotations

import argparse
import logging
import math
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from output_shaper import OutputShaper  # noqa: E402
from pid_controller import PIDController  # noqa: E402
from shared import topics as T  # noqa: E402

log = logging.getLogger("ondos.auto_controller")

STATUS_RATE_HZ = 10.0
STATUS_PERIOD_S = 1.0 / STATUS_RATE_HZ
MS_PER_S = 1000.0
PERCENT_SCALE = 100.0
MAX_CACHED_SAMPLES = 64

MAX_TILT_VAR_NAME = "max_tilt_deg"
INITIAL_MAX_TILT_FALLBACK_DEG = 10.0
NO_MODEL_CHOICE = "none"

DEFAULT_AI_SETTINGS: dict[str, Any] = {
    "model_version": NO_MODEL_CHOICE,
    "action_smoothing_pct": 0.0,
    "tilt_scale_pct": 100.0,
}
DEFAULT_PID_SETTINGS: dict[str, float] = {
    "pid_kp_deg_per_mm": 0.05,
    "pid_ki_deg_per_mm_per_s": 0.05,
    "pid_kd_deg_per_mm_s": 0.02,
    "pid_integral_limit_deg": 2.0,
}

AI_NUMERIC_BOUNDS: dict[str, tuple[float, float, float, str]] = {
    "action_smoothing_pct": (0.0, 100.0, 5.0, "AI output smoothing percentage."),
    "tilt_scale_pct": (10.0, 100.0, 5.0, "AI output scale percentage."),
}
PID_NUMERIC_BOUNDS: dict[str, tuple[float, float, float, str]] = {
    "pid_kp_deg_per_mm": (0.0, 2.0, 0.01, "Proportional gain (deg/mm)."),
    "pid_ki_deg_per_mm_per_s": (0.0, 2.0, 0.01, "Integral gain (deg/(mm*s))."),
    "pid_kd_deg_per_mm_s": (0.0, 1.0, 0.01, "Velocity damping gain (deg per mm/s)."),
    "pid_integral_limit_deg": (0.0, 15.0, 0.5, "Maximum integral tilt contribution (deg)."),
}


def _default_clock_s() -> float:
    try:
        from shared.bus import now_s
        return now_s()
    except ImportError:
        return time.time()


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _scale_action(
    action: Sequence[float], max_tilt_deg: float, tilt_scale_pct: float
) -> tuple[float, float]:
    try:
        from ai.common.action_scaling import to_target_tilt_deg
        return to_target_tilt_deg(action, max_tilt_deg, tilt_scale_pct)
    except ImportError:
        scale_deg = max_tilt_deg * tilt_scale_pct / PERCENT_SCALE
        return float(action[0]) * scale_deg, float(action[1]) * scale_deg


def _available_model_versions(models_dir: Path | None) -> list[str]:
    try:
        from ai.model_versions import DEFAULT_MODELS_DIR, list_model_versions
        target_dir = DEFAULT_MODELS_DIR if models_dir is None else models_dir
        return list_model_versions(target_dir)
    except ImportError:
        return []


def _extract_max_tilt_deg(spec_msg: Mapping[str, Any]) -> float | None:
    for item in spec_msg.get("variables", []):
        if item.get("name") == MAX_TILT_VAR_NAME:
            value = item.get("value")
            if _is_finite_number(value) and float(value) >= 0.0:
                return float(value)
    return None


class AutoControllerApp:
    """Validates bus inputs, selects AI or PID mode, and publishes target tilts and status."""

    def __init__(
        self,
        bus: Any = None,
        ai_controller: Any = None,
        models_dir: Path | None = None,
        clock: Callable[[], float] | None = None,
        load_default_model: bool = True,
    ) -> None:
        self._bus = bus
        self._models_dir = models_dir
        self._clock = clock or _default_clock_s
        self._lock = threading.RLock()

        self._ai_settings: dict[str, Any] = dict(DEFAULT_AI_SETTINGS)
        self._pid_settings: dict[str, float] = dict(DEFAULT_PID_SETTINGS)
        self._pid = PIDController(self._pid_settings, INITIAL_MAX_TILT_FALLBACK_DEG)
        self._ai_shaper = OutputShaper()
        self._pid_shaper = OutputShaper()

        self._ai_controller = ai_controller
        self._pending_model_version: str | None = None
        if self._ai_controller is None and load_default_model:
            self._load_ai_model(None)
        elif self._ai_controller is not None and getattr(self._ai_controller, "model_version", None):
            self._ai_settings["model_version"] = self._ai_controller.model_version

        self._init_state_caches()

    def _init_state_caches(self) -> None:
        self._game_state: dict[str, Any] | None = None
        self._platform_state: dict[str, Any] | None = None
        self._maze: dict[str, Any] | None = None
        self._distance_map: dict[str, Any] | None = None
        self._vision_online: bool | None = None
        self._max_tilt_deg: float | None = None

        self._balls_by_seq: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._routes_by_ball_seq: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._latest_ball: dict[str, Any] | None = None
        self._latest_route: dict[str, Any] | None = None
        self._last_matched_ball: dict[str, Any] | None = None
        self._last_matched_route: dict[str, Any] | None = None

        self._previous_action: tuple[float, float] = (0.0, 0.0)
        self._previous_ball_ts: float | None = None
        self._last_answered_ball_seq: int | None = None
        self._controller_fault = False
        self._last_published_status: str | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Subscribe to required topics and publish initial AI/PID variables specs."""
        if self._bus is None:
            raise RuntimeError("Bus is not set; pass bus=... or call run()")
        subscriptions = (
            (T.VISION_BALL, self.on_ball),
            (T.VISION_MAZE, self.on_maze),
            (T.PLAN_DISTANCE_MAP, self.on_distance_map),
            (T.PLAN_ROUTE, self.on_route),
            (T.PLATFORM_STATE, self.on_platform_state),
            (T.GAME_STATE, self.on_game_state),
            (T.variables_spec("platform"), self.on_platform_variables_spec),
            (T.cs_variables("ai"), self.on_ai_variables),
            (T.cs_variables("pid"), self.on_pid_variables),
            (T.sys_online("vision"), self.on_vision_online),
        )
        for topic, callback in subscriptions:
            self._bus.subscribe(topic, callback)
        self._publish_ai_variables_spec()
        self._publish_pid_variables_spec()

    def stop(self) -> None:
        """Signal the run() loop to stop."""
        self._stop_event.set()

    def run(self, host: str = T.BROKER_HOST, port: int = T.BROKER_TCP_PORT) -> None:
        """Connect to the broker and run the 10 Hz status loop until stopped."""
        created_bus = False
        if self._bus is None:
            from shared.bus import Bus
            self._bus = Bus("auto_controller", host, port)
            self._bus.connect()
            created_bus = True
        self._stop_event.clear()
        try:
            self.start()
            while not self._stop_event.is_set():
                self.tick()
                self._stop_event.wait(STATUS_PERIOD_S)
        except KeyboardInterrupt:
            pass
        finally:
            if created_bus and self._bus is not None:
                self._bus.close()

    # ------------------------------------------------------------------ handlers
    def on_game_state(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            prev = self._game_state
            self._game_state = msg
            changed_game = prev is not None and (
                prev.get("game_id") != msg.get("game_id")
                or prev.get("mode") != msg.get("mode")
                or prev.get("maze_id") != msg.get("maze_id")
            )
            if msg.get("state") != "playing" or changed_game:
                self._reset_controllers()
                self._controller_fault = False
                if changed_game:
                    self._last_matched_ball = None
                    self._last_matched_route = None
            if self._pending_model_version is not None and msg.get("state") in ("setup", "ready"):
                version = self._pending_model_version
                self._pending_model_version = None
                self._apply_model_version(version)

    def on_maze(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            prev_id = self._maze.get("maze_id") if self._maze else None
            self._maze = msg
            if prev_id != msg.get("maze_id"):
                self._routes_by_ball_seq.clear()
                self._latest_route = None
                self._last_matched_ball = None
                self._last_matched_route = None
                self._controller_fault = False
                self._reset_controllers()

    def on_distance_map(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            self._distance_map = msg

    def on_platform_state(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            self._platform_state = msg
            if msg.get("is_e_stop") or msg.get("fault") != "none":
                self._reset_controllers()

    def on_platform_variables_spec(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        max_tilt = _extract_max_tilt_deg(msg)
        if max_tilt is not None:
            with self._lock:
                self._max_tilt_deg = max_tilt

    def on_vision_online(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, bool):
            return
        with self._lock:
            self._vision_online = msg
            if not msg:
                self._reset_controllers()

    def on_ball(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            seq = int(msg["seq"])
            self._latest_ball = msg
            self._cache_sample(self._balls_by_seq, seq, msg)
            if not msg.get("is_visible"):
                self._reset_controllers()
                return
            self._try_publish_for_seq(seq, self._clock())

    def on_route(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            ball_seq = int(msg["ball_seq"])
            self._latest_route = msg
            self._cache_sample(self._routes_by_ball_seq, ball_seq, msg)
            self._try_publish_for_seq(ball_seq, self._clock())

    def on_ai_variables(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            changed = False
            for name, bounds in AI_NUMERIC_BOUNDS.items():
                if name in msg and _is_finite_number(msg[name]):
                    low, high, _, _ = bounds
                    self._ai_settings[name] = min(max(float(msg[name]), low), high)
                    changed = True
            if "model_version" in msg and isinstance(msg["model_version"], str):
                requested = msg["model_version"]
                if self._is_between_games():
                    self._pending_model_version = None
                    self._apply_model_version(requested)
                else:
                    self._pending_model_version = requested
                changed = True
            if changed:
                self._publish_ai_variables_spec()

    def on_pid_variables(self, topic: str, msg: Any, t_recv_s: float) -> None:
        if not isinstance(msg, dict) or self._is_replay(msg):
            return
        with self._lock:
            changed = False
            for name, bounds in PID_NUMERIC_BOUNDS.items():
                if name in msg and _is_finite_number(msg[name]):
                    low, high, _, _ = bounds
                    self._pid_settings[name] = min(max(float(msg[name]), low), high)
                    changed = True
            if changed:
                self._pid.settings = self._pid_settings
                self._publish_pid_variables_spec()

    def tick(self, now_s: float | None = None) -> dict[str, Any]:
        """Evaluate current controller health/status and publish ai/status."""
        with self._lock:
            t_now = self._clock() if now_s is None else float(now_s)
            status, active_controller, route_points = self._evaluate_status(t_now)
            if status != "active":
                self._reset_controllers()
            return self._publish_status(status, active_controller, route_points)

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _is_replay(msg: Mapping[str, Any]) -> bool:
        return msg.get("writer") == "replay"

    @staticmethod
    def _cache_sample(cache: OrderedDict[int, dict[str, Any]], key: int, msg: dict[str, Any]) -> None:
        if key in cache:
            cache.move_to_end(key)
        cache[key] = msg
        while len(cache) > MAX_CACHED_SAMPLES:
            cache.popitem(last=False)

    def _is_between_games(self) -> bool:
        return self._game_state is None or self._game_state.get("state") in ("setup", "ready")

    def _reset_controllers(self) -> None:
        self._pid.reset()
        self._ai_shaper.reset()
        self._pid_shaper.reset()
        self._previous_action = (0.0, 0.0)
        self._previous_ball_ts = None

    def _load_ai_model(self, model_version: str | None) -> bool:
        load_errors: tuple[type[BaseException], ...] = (OSError, RuntimeError, ValueError)
        try:
            from ai.model_metadata import ModelLoadError
            load_errors = (ModelLoadError, OSError, RuntimeError, ValueError)
        except ImportError:
            pass

        candidate = self._ai_controller
        if candidate is None:
            try:
                from ai.ai_controller import AIController
                from ai.model_versions import DEFAULT_MODELS_DIR
            except ImportError:
                return False
            target_dir = DEFAULT_MODELS_DIR if self._models_dir is None else self._models_dir
            candidate = AIController(target_dir)

        try:
            candidate.load(model_version)
        except load_errors:
            return False
        self._ai_controller = candidate
        if getattr(candidate, "model_version", None):
            self._ai_settings["model_version"] = candidate.model_version
        return True

    def _apply_model_version(self, model_version: str) -> None:
        if model_version == NO_MODEL_CHOICE:
            return
        if self._load_ai_model(model_version):
            self._controller_fault = False
            self._publish_ai_variables_spec()

    def _is_fresh(self, msg: Mapping[str, Any] | None, now_s: float, max_age_ms: float) -> bool:
        if msg is None:
            return False
        ts = msg.get("timestamp_s")
        if not _is_finite_number(ts):
            return False
        return (now_s - float(ts)) * MS_PER_S <= max_age_ms

    def _active_controller_for_mode(self, mode: str | None) -> str:
        if mode == "ai":
            return "ai"
        if mode == "simple":
            return "pid"
        return "none"

    def _check_game_and_platform(self, now_s: float) -> tuple[str | None, str]:
        game = self._game_state
        if not self._is_fresh(game, now_s, T.GAME_STATE_MAX_AGE_MS):
            return "stale_game", "none"
        assert game is not None
        if game["state"] == "e_stop":
            return "e_stop", "none"
        active_ctrl = self._active_controller_for_mode(game["mode"])
        if game["state"] != "playing" or active_ctrl == "none":
            return "idle", "none"
        plat = self._platform_state
        if not self._is_fresh(plat, now_s, T.CONTROLLER_INPUT_MAX_AGE_MS) or self._max_tilt_deg is None:
            return "stale_platform", active_ctrl
        assert plat is not None
        if plat["is_e_stop"]:
            return "e_stop", active_ctrl
        if plat["fault"] != "none":
            return "fault", active_ctrl
        return None, active_ctrl

    def _check_vision_and_maps(self, now_s: float, ball_msg: dict[str, Any] | None) -> str | None:
        if (
            self._vision_online is False
            or not self._is_fresh(ball_msg, now_s, T.CONTROLLER_INPUT_MAX_AGE_MS)
            or not ball_msg["is_visible"]
        ):
            return "ball_lost"
        active_maze_id = self._game_state.get("maze_id") if self._game_state else None
        if (
            active_maze_id is None
            or self._maze is None
            or self._distance_map is None
            or self._maze.get("maze_id") != active_maze_id
            or self._distance_map.get("maze_id") != active_maze_id
        ):
            return "no_maze"
        return None

    def _check_route_and_model(
        self,
        now_s: float,
        active_ctrl: str,
        ball_msg: dict[str, Any],
        route_msg: dict[str, Any] | None,
    ) -> str | None:
        active_maze_id = self._game_state.get("maze_id") if self._game_state else None
        if (
            not self._is_fresh(route_msg, now_s, T.CONTROLLER_INPUT_MAX_AGE_MS)
            or route_msg.get("maze_id") != active_maze_id
            or route_msg.get("ball_seq") != ball_msg["seq"]
            or route_msg.get("status") != "valid"
            or not route_msg.get("target_points_mm")
        ):
            return "no_path"
        if active_ctrl == "ai" and (
            self._ai_controller is None
            or getattr(self._ai_controller, "model_version", None) is None
        ):
            return "no_model"
        return None

    def _resolve_tick_route_pair(
        self, ball_msg: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        seq = int(ball_msg["seq"])
        matched = self._routes_by_ball_seq.get(seq)
        if matched is not None:
            return ball_msg, matched
        # Between vision/ball and its plan/route (e.g. 3 ms transit), keep the last matched pair
        # so tick() does not misreport no_path and reset the PID integral mid-run.
        if self._last_matched_ball is not None and self._last_matched_route is not None:
            return self._last_matched_ball, self._last_matched_route
        return ball_msg, self._latest_route

    def _evaluate_status(
        self,
        now_s: float,
        ball: dict[str, Any] | None = None,
        route: dict[str, Any] | None = None,
        ignore_controller_fault: bool = False,
    ) -> tuple[str, str, list[list[float]]]:
        err, active_ctrl = self._check_game_and_platform(now_s)
        if err is not None:
            return err, active_ctrl, []
        ball_msg = self._latest_ball if ball is None else ball
        err = self._check_vision_and_maps(now_s, ball_msg)
        if err is not None:
            return err, active_ctrl, []
        assert ball_msg is not None
        pair_ball, pair_route = (
            self._resolve_tick_route_pair(ball_msg) if (ball is None and route is None) else (ball_msg, route)
        )
        err = self._check_route_and_model(now_s, active_ctrl, pair_ball, pair_route)
        if err is not None:
            return err, active_ctrl, []
        if not ignore_controller_fault and self._controller_fault:
            return "fault", active_ctrl, []
        assert pair_route is not None
        return "active", active_ctrl, pair_route["target_points_mm"]

    def _publish_status(
        self, status: str, active_controller: str, route_points: list[list[float]]
    ) -> dict[str, Any]:
        payload = self._build_status_payload(status, active_controller, route_points)
        self._last_published_status = status
        if self._bus is not None:
            self._bus.publish(T.AI_STATUS, payload)
        return payload

    def _publish_status_if_changed(
        self, status: str, active_controller: str, route_points: list[list[float]]
    ) -> None:
        if status != self._last_published_status:
            self._publish_status(status, active_controller, route_points)

    def _build_status_payload(
        self, status: str, active_controller: str, route_points: list[list[float]]
    ) -> dict[str, Any]:
        policy = None
        model_version = None
        if active_controller == "ai" and self._ai_controller is not None:
            policy = getattr(self._ai_controller, "policy", None)
            model_version = getattr(self._ai_controller, "model_version", None)
        return {
            "active_controller": active_controller,
            "status": status,
            "policy": policy,
            "model_version": model_version,
            "target_points_mm": [list(pt) for pt in route_points] if status == "active" else [],
        }

    def _try_publish_for_seq(self, ball_seq: int, now_s: float) -> None:
        if ball_seq == self._last_answered_ball_seq:
            return
        ball = self._balls_by_seq.get(ball_seq)
        route = self._routes_by_ball_seq.get(ball_seq)
        if ball is None or route is None:
            return
        self._last_matched_ball = ball
        self._last_matched_route = route
        status, active_controller, route_points = self._evaluate_status(
            now_s, ball=ball, route=route, ignore_controller_fault=True
        )
        if status != "active":
            self._reset_controllers()
            self._publish_status_if_changed(status, active_controller, [])
            return
        self._run_and_publish_cycle(ball_seq, ball, route, active_controller, route_points)

    def _run_and_publish_cycle(
        self,
        ball_seq: int,
        ball: Mapping[str, Any],
        route: Mapping[str, Any],
        active_controller: str,
        route_points: list[list[float]],
    ) -> None:
        assert self._game_state is not None and self._platform_state is not None and self._max_tilt_deg is not None
        maze_id = self._game_state["maze_id"]
        try:
            if active_controller == "ai":
                self._publish_ai_command(ball, route, self._platform_state, maze_id, self._max_tilt_deg)
            elif active_controller == "pid":
                self._publish_pid_command(ball, route, maze_id, self._max_tilt_deg)
            self._controller_fault = False
            self._last_answered_ball_seq = ball_seq
            self._publish_status_if_changed("active", active_controller, route_points)
        except (ValueError, RuntimeError) as exc:
            log.warning("dropping invalid controller cycle for seq %s: %s", ball_seq, exc)
            self._controller_fault = True
            self._reset_controllers()
            self._publish_status("fault", active_controller, [])

    def _publish_ai_command(
        self,
        ball: Mapping[str, Any],
        route: Mapping[str, Any],
        plat: Mapping[str, Any],
        maze_id: str,
        max_tilt_deg: float,
    ) -> None:
        obs = self._ai_controller.observation_builder.build(
            ball, plat, self._previous_action, route["target_points_mm"]
        )
        raw_action = self._ai_controller.act(obs)
        scaled = _scale_action(raw_action, max_tilt_deg, self._ai_settings["tilt_scale_pct"])
        tilt_x_deg, tilt_y_deg = self._ai_shaper.shape(
            scaled,
            {
                "max_tilt_deg": max_tilt_deg,
                "action_smoothing_pct": self._ai_settings["action_smoothing_pct"],
            },
        )
        if not (_is_finite_number(tilt_x_deg) and _is_finite_number(tilt_y_deg)):
            raise ValueError("non-finite shaped AI tilt")
        self._previous_action = (tilt_x_deg, tilt_y_deg)
        if self._bus is not None:
            self._bus.publish(
                T.AI_TARGET_TILT,
                {
                    "target_tilt_x_deg": float(tilt_x_deg),
                    "target_tilt_y_deg": float(tilt_y_deg),
                    "model_version": self._ai_controller.model_version,
                    "ball_seq": int(ball["seq"]),
                    "maze_id": maze_id,
                },
            )

    def _publish_pid_command(
        self,
        ball: Mapping[str, Any],
        route: Mapping[str, Any],
        maze_id: str,
        max_tilt_deg: float,
    ) -> None:
        ball_ts = float(ball["timestamp_s"])
        dt_s = None if self._previous_ball_ts is None else ball_ts - self._previous_ball_ts
        self._pid.max_tilt_deg = max_tilt_deg
        raw_tilt = self._pid.compute(ball, route["target_points_mm"][0], dt_s)
        tilt_x_deg, tilt_y_deg = self._pid_shaper.shape(
            raw_tilt, {"max_tilt_deg": max_tilt_deg}
        )
        if not (_is_finite_number(tilt_x_deg) and _is_finite_number(tilt_y_deg)):
            raise ValueError("non-finite shaped PID tilt")
        self._previous_ball_ts = ball_ts
        if self._bus is not None:
            self._bus.publish(
                T.CONTROL_TARGET_TILT,
                {
                    "target_tilt_x_deg": float(tilt_x_deg),
                    "target_tilt_y_deg": float(tilt_y_deg),
                    "ball_seq": int(ball["seq"]),
                    "maze_id": maze_id,
                },
            )

    def _publish_ai_variables_spec(self) -> None:
        if self._bus is None:
            return
        versions = _available_model_versions(self._models_dir)
        current = str(self._ai_settings["model_version"])
        if current not in versions and current != NO_MODEL_CHOICE:
            versions.append(current)
        choices = versions or [NO_MODEL_CHOICE]
        variables: list[dict[str, Any]] = [
            {
                "name": "model_version",
                "value": current,
                "default": choices[-1],
                "min": None,
                "max": None,
                "choices": choices,
                "is_live": False,
                "description": "Trained AI model version (takes effect next game).",
            }
        ]
        for name, (low, high, step, desc) in AI_NUMERIC_BOUNDS.items():
            variables.append(
                {
                    "name": name,
                    "value": self._ai_settings[name],
                    "default": DEFAULT_AI_SETTINGS[name],
                    "min": low,
                    "max": high,
                    "step": step,
                    "choices": None,
                    "is_live": True,
                    "description": desc,
                }
            )
        self._bus.publish(T.variables_spec("ai"), {"variables": variables})

    def _publish_pid_variables_spec(self) -> None:
        if self._bus is None:
            return
        variables = [
            {
                "name": name,
                "value": self._pid_settings[name],
                "default": DEFAULT_PID_SETTINGS[name],
                "min": low,
                "max": high,
                "step": step,
                "choices": None,
                "is_live": True,
                "description": desc,
            }
            for name, (low, high, step, desc) in PID_NUMERIC_BOUNDS.items()
        ]
        self._bus.publish(T.variables_spec("pid"), {"variables": variables})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Ondos Auto Controller runtime.")
    parser.add_argument("--host", default=T.BROKER_HOST)
    parser.add_argument("--port", type=int, default=T.BROKER_TCP_PORT)
    parser.add_argument("--models-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    app = AutoControllerApp(models_dir=args.models_dir)
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
