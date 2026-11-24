"""VisionNode (C.5): the main program of Vision.

Runs the frame loop, applies the game-state rules for Vision commands and publishes the
vision/* topics. The parts of the other Vision issues plug in at _process_frame (per-frame
parts) and at the command handlers (read_maze, calibrate_camera).
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path

import numpy as np

from shared import topics as T
from shared.bus import Bus, now_s
from vision.board_calibrator import BoardCalibrator, NotCalibratedError
from vision.command_rules import is_command_allowed, is_vision_command
from vision.cpu_meter import CpuMeter
from vision.frame_grabber import FrameGrabber
from vision.frame_stats import FrameStats
from vision.vision_variables import CONFIG_KEY, VisionVariables

log = logging.getLogger(__name__)

STATUS_PERIOD_S = 1.0        # vision/status is published at 1 Hz (IF-04)
CAMERA_LOST_TIMEOUT_S = 1.0  # no frame for 1 s: the camera is lost (C.8)
CAMERA_RETRY_PERIOD_S = 1.0  # a lost camera is opened again every 1 s (C.8)
NO_FRAME_WAIT_S = 0.01       # short pause when no frame came, so a missing camera does not use a full CPU core
ENVELOPE_FIELDS = frozenset({"timestamp_s", "seq", "version", "writer"})
NO_MAZE_MATCH = "none"       # vision/status maze_match while no maze file matches
CAMERA_SELECT_VARIABLES = frozenset({"camera_index"})
EXPOSURE_VARIABLES = frozenset({"exposure", "gain"})


class VisionNode:
    """Main program of Vision: runs the frame loop, applies the game-state rules and publishes vision/*."""

    def __init__(self, variables: VisionVariables, grabber: FrameGrabber, bus: Bus, calibrator: BoardCalibrator,
                 clip_dir: Path | None = None) -> None:
        self._variables = variables
        self._grabber = grabber
        self._bus = bus
        self._clip_dir = clip_dir  # None = USB camera
        self._frame_stats = FrameStats()
        self._cpu_meter = CpuMeter()
        self._calibrator = calibrator
        self._last_frame: np.ndarray | None = None
        self._game_state_lock = threading.Lock()
        self._game_state: dict | None = None
        # Bus callbacks run on the MQTT thread; camera and command work is handed to the frame loop
        # through these, so OpenCV is used from one thread only.
        self._pending_commands: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._camera_reopen_request = threading.Event()
        self._exposure_update_request = threading.Event()
        self._stop_request = threading.Event()
        self._command_handlers = {
            "read_maze": self._handle_read_maze,
            "calibrate_camera": self._handle_calibrate_camera,
        }
        self._last_frame_s: float | None = None
        self._last_open_attempt_s = 0.0
        self._next_status_s = 0.0

    # ------------------------------------------------------------ public (C.5)
    def run(self) -> None:
        """Connect to the bus, open the frame source and run the frame loop until stop() or the end of a clip."""
        self._subscribe()
        self._bus.connect()
        try:
            self._open_source()
            self._publish_variables_spec()
            while not self._is_done():
                self._run_one_iteration()
        except KeyboardInterrupt:
            log.info("stopped by the user")
        finally:
            self._grabber.close()
            self._bus.close()

    def stop(self) -> None:
        """Ask the frame loop to end after the current iteration (safe from any thread)."""
        self._stop_request.set()

    def on_command(self, msg: dict) -> None:
        """cs/command: queue read_maze or calibrate_camera when the game state allows it; refuse it otherwise."""
        cmd = msg["cmd"]
        if not is_vision_command(cmd):
            return
        game_state = self._latest_game_state()
        if not is_command_allowed(cmd, game_state, now_s()):
            log.warning("%s refused in game state %s", cmd, game_state["state"])
            return
        self._pending_commands.put(cmd)

    def on_variables(self, msg: dict) -> None:
        """cs/variables/vision: check and apply the values, then republish the spec with the values in use."""
        requested = {name: value for name, value in msg.items() if name not in ENVELOPE_FIELDS}
        changed = set(self._variables.apply(requested))
        if changed & CAMERA_SELECT_VARIABLES:
            self._camera_reopen_request.set()
        if changed & EXPOSURE_VARIABLES:
            self._exposure_update_request.set()
        self._publish_variables_spec()

    # ------------------------------------------------------------ bus
    def _subscribe(self) -> None:
        self._bus.subscribe(T.CS_COMMAND, lambda topic, msg, t_recv_s: self.on_command(msg))
        self._bus.subscribe(T.cs_variables(CONFIG_KEY), lambda topic, msg, t_recv_s: self.on_variables(msg))
        self._bus.subscribe(T.GAME_STATE, lambda topic, msg, t_recv_s: self._store_game_state(msg))

    def _store_game_state(self, msg: dict) -> None:
        with self._game_state_lock:
            self._game_state = msg

    def _latest_game_state(self) -> dict | None:
        with self._game_state_lock:
            return self._game_state

    def _publish_variables_spec(self) -> None:
        self._bus.publish(T.variables_spec(CONFIG_KEY), self._variables.to_spec())

    def _publish_status_if_due(self, now: float) -> None:
        if now < self._next_status_s:
            return
        self._next_status_s = now + STATUS_PERIOD_S
        self._bus.publish(T.VISION_STATUS, self._build_status(now))

    def _build_status(self, now: float) -> dict:
        # maze_match comes from MazeReader (#48); until it is integrated nothing is matched.
        return {
            "fps_hz": self._frame_stats.fps_hz(now),
            "frame_age_ms": self._frame_stats.mean_frame_age_ms(now),
            "is_camera_ok": self._is_camera_ok(now),
            "is_calibrated": self._calibrator.is_calibrated,
            "markers_found": self._calibrator.markers_found,
            "reprojection_error_mm": self._calibrator.reprojection_error_mm,
            "maze_match": NO_MAZE_MATCH,
            "cpu_pct": self._cpu_meter.sample_pct(),
        }

    # ------------------------------------------------------------ frame source
    def _open_source(self) -> None:
        if self._clip_dir is None:
            self._open_camera()
            return
        if not self._grabber.open_clip(self._clip_dir):
            raise FileNotFoundError(f"cannot open the clip in {self._clip_dir}")

    def _open_camera(self) -> None:
        self._last_open_attempt_s = now_s()
        camera_index = self._variables.get("camera_index")
        if not self._grabber.open(camera_index):
            log.warning("camera %s cannot be opened; retrying every %.0f s", camera_index, CAMERA_RETRY_PERIOD_S)
            return
        log.info("camera %s opened", camera_index)
        self._apply_exposure()

    def _apply_exposure(self) -> None:
        self._grabber.set_exposure(self._variables.get("exposure"), self._variables.get("gain"))

    def _is_camera_ok(self, now: float) -> bool:
        return self._last_frame_s is not None and now - self._last_frame_s < CAMERA_LOST_TIMEOUT_S

    def _is_done(self) -> bool:
        if self._stop_request.is_set():
            return True
        return self._clip_dir is not None and self._grabber.is_clip_finished()

    # ------------------------------------------------------------ frame loop
    def _run_one_iteration(self) -> None:
        self._apply_requested_settings()
        self._run_pending_commands()
        sample = self._grabber.read()
        if sample is None:
            self._handle_missing_frame()
        else:
            self._process_frame(*sample)
        self._publish_status_if_due(now_s())

    def _apply_requested_settings(self) -> None:
        if _take_request(self._camera_reopen_request) and self._clip_dir is None:
            self._open_camera()
        if _take_request(self._exposure_update_request):
            self._apply_exposure()

    def _run_pending_commands(self) -> None:
        while not self._pending_commands.empty():
            self._command_handlers[self._pending_commands.get()]()

    def _process_frame(self, frame: np.ndarray, t_arrival_s: float) -> None:
        self._last_frame_s = t_arrival_s
        self._last_frame = frame
        self._calibrator.update(frame)
        # The per-frame parts plug in here, in the order of C.5: calibration, ball state, events,
        # edit state, then the route for this ball sample.
        self._frame_stats.record_frame(t_arrival_s, now_s())

    def _handle_missing_frame(self) -> None:
        now = now_s()
        is_retry_due = now - self._last_open_attempt_s >= CAMERA_RETRY_PERIOD_S
        if self._clip_dir is None and not self._is_camera_ok(now) and is_retry_due:
            self._open_camera()
        time.sleep(NO_FRAME_WAIT_S)

    # ------------------------------------------------------------ commands
    def _handle_read_maze(self) -> None:
        log.warning("read_maze accepted, but MazeReader (#48) is not integrated yet")

    def _handle_calibrate_camera(self) -> None:
        if self._last_frame is None:
            log.warning("calibrate_camera accepted, but there is no frame yet")
            return
        try:
            error_mm, camera_height_mm = self._calibrator.calibrate(self._last_frame)
        except NotCalibratedError as error:
            log.warning("calibrate_camera failed: %s", error)
            return
        log.info("calibrate_camera done: reprojection_error_mm=%.2f camera_height_mm=%.0f",
                 error_mm, camera_height_mm)


def _take_request(request: threading.Event) -> bool:
    """True once for each time the request was set."""
    if not request.is_set():
        return False
    request.clear()
    return True
