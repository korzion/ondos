"""VisionNode with a fake bus and a fake frame source (no broker, no camera)."""
from __future__ import annotations

import logging
import threading
import time

import numpy as np
import pytest

from shared import topics as T
from shared.bus import now_s
from shared.interfaces import validate
from vision.board_calibrator import LAST_HOMOGRAPHY_HOLD_FRAMES, BoardCalibrator
from vision.path_planner import PathPlanner
from vision.tests.message_helpers import with_envelope
from vision.tests.test_ball_tracker import (
    BALL_DIAMETER_MM,
    POSITION_TOLERANCE_MM,
    ROLLING_SPEED_MM_S,
    ball_variables,
    rolling_ball,
    scene,
)
from vision.tests.test_path_planner import planner_with_example_maze
from vision.vision_config import load_vision_config
from vision.vision_node import CAMERA_RETRY_PERIOD_S, VisionNode
from vision.vision_variables import CONFIG_KEY, VisionVariables

SPEC_TOPIC = T.variables_spec(CONFIG_KEY)
VARIABLES_TOPIC = T.cs_variables(CONFIG_KEY)
FRAME_PERIOD_S = 1.0 / 30.0
STARTUP_WAIT_S = 0.3
MAX_FRAME_AGE_MS = 100.0  # the range of frame_age_ms in vision/ball (IF-04)
ARRIVAL_DELAY_S = 0.02  # the frames of play_clip() are this old when Vision gets them
GREY = 128
NORTH_OF_START_MM = (-20.0, 20.0)  # centre of cell {row 1, col 0} of the example maze, 2 steps from the exit


class FakeBus:
    """Records what VisionNode publishes and checks every message against its schema, like the shared Bus."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []
        self.callbacks: dict[str, list] = {}
        self.is_closed = False
        self._seq: dict[str, int] = {}
        self._lock = threading.Lock()

    def subscribe(self, pattern: str, callback) -> None:
        self.callbacks.setdefault(pattern, []).append(callback)

    def connect(self) -> None:
        pass

    def close(self) -> None:
        self.is_closed = True

    def publish(self, topic: str, fields: dict) -> dict:
        with self._lock:
            seq = self._seq.get(topic, 0)
            self._seq[topic] = seq + 1
        msg = with_envelope(topic, fields, writer="vision", seq=seq)
        validate(topic, msg)
        with self._lock:
            self.published.append((topic, msg))
        return msg

    def deliver(self, topic: str, fields: dict, writer: str, timestamp_s: float | None = None) -> None:
        msg = with_envelope(topic, fields, writer=writer, timestamp_s=timestamp_s)
        for callback in self.callbacks[topic]:
            callback(topic, msg, now_s())

    def messages(self, topic: str) -> list[dict]:
        with self._lock:
            return [msg for published_topic, msg in self.published if published_topic == topic]


class FakeGrabber:
    """A camera that gives frames at 30 Hz, or one that cannot be opened."""

    def __init__(self, can_open: bool = True, clip_frame_count: int | None = None,
                 clip_frames: list[np.ndarray] | None = None, arrival_delay_s: float = 0.0) -> None:
        self.can_open = can_open
        self.opened_indexes: list[int] = []
        self.exposures: list[tuple[float, float]] = []
        self.is_closed = False
        self._clip_frames = list(clip_frames or [])  # the frames of a clip; black frames when not given
        self._clip_frames_left = clip_frame_count if clip_frames is None else len(clip_frames)
        self._arrival_delay_s = arrival_delay_s  # how long a frame has been on the laptop when read() gives it
        self._is_open = False

    def open(self, camera_index: int) -> bool:
        self.opened_indexes.append(camera_index)
        self._is_open = self.can_open
        return self.can_open

    def open_clip(self, clip_dir) -> bool:
        self._is_open = True
        return True

    def read(self):
        if not self._is_open or self.is_clip_finished():
            return None
        time.sleep(FRAME_PERIOD_S)
        if self._clip_frames_left is not None:
            self._clip_frames_left -= 1
        frame = self._clip_frames.pop(0) if self._clip_frames else np.zeros((48, 64, 3), dtype=np.uint8)
        return frame, now_s() - self._arrival_delay_s

    def set_exposure(self, exposure: float, gain: float) -> None:
        self.exposures.append((exposure, gain))

    def is_clip_finished(self) -> bool:
        return self._clip_frames_left is not None and self._clip_frames_left <= 0

    def close(self) -> None:
        self.is_closed = True


def make_calibrator() -> BoardCalibrator:
    return BoardCalibrator(load_vision_config())


def game_state_fields(state: str) -> dict:
    return {"state": state, "mode": "glove", "game_id": None, "maze_id": None, "elapsed_s": 0.0, "cell": None,
            "distance_to_exit_cells": None, "progress_pct": 0.0, "result": "none"}


@pytest.fixture
def running_node():
    """Start a VisionNode in a thread; the test gets (node, bus, grabber) and the node is stopped afterwards."""
    started = []

    def start(grabber: FakeGrabber):
        bus = FakeBus()
        node = VisionNode(VisionVariables.load(), grabber, bus, make_calibrator())
        thread = threading.Thread(target=node.run, daemon=True)
        thread.start()
        started.append((node, thread))
        time.sleep(STARTUP_WAIT_S)
        return node, bus

    yield start
    for node, thread in started:
        node.stop()
        thread.join(timeout=2)


def test_spec_and_status_are_published_at_start(running_node):
    grabber = FakeGrabber()
    _, bus = running_node(grabber)
    assert bus.messages(SPEC_TOPIC)
    status = bus.messages(T.VISION_STATUS)
    assert status and status[0]["is_calibrated"] is False and status[0]["maze_match"] == "none"
    assert grabber.opened_indexes == [0] and grabber.exposures


def test_status_shows_a_working_camera(running_node):
    _, bus = running_node(FakeGrabber())
    time.sleep(1.0)
    latest = bus.messages(T.VISION_STATUS)[-1]
    assert latest["is_camera_ok"] is True and latest["fps_hz"] > 0


def test_variables_change_republishes_the_clamped_spec_and_reopens_the_camera(running_node):
    grabber = FakeGrabber()
    _, bus = running_node(grabber)
    bus.deliver(VARIABLES_TOPIC, {"camera_index": 1, "lost_timeout_ms": 999_999}, writer="cs_app")
    time.sleep(0.2)
    entries = {entry["name"]: entry for entry in bus.messages(SPEC_TOPIC)[-1]["variables"]}
    assert entries["lost_timeout_ms"]["value"] == entries["lost_timeout_ms"]["max"]
    assert entries["camera_index"]["value"] == 1
    assert grabber.opened_indexes[-1] == 1


def test_lost_camera_is_reported_and_retried(running_node):
    grabber = FakeGrabber(can_open=False)
    _, bus = running_node(grabber)
    time.sleep(CAMERA_RETRY_PERIOD_S + 0.2)
    assert all(msg["is_camera_ok"] is False for msg in bus.messages(T.VISION_STATUS))
    assert len(grabber.opened_indexes) >= 2


def test_read_maze_is_refused_while_playing(running_node, caplog):
    _, bus = running_node(FakeGrabber())
    with caplog.at_level(logging.WARNING):
        bus.deliver(T.GAME_STATE, game_state_fields("playing"), writer="game_manager")
        bus.deliver(T.CS_COMMAND, {"cmd": "read_maze", "mode": None, "file": None, "speed": None}, writer="cs_app")
        time.sleep(0.2)
    assert "read_maze refused" in caplog.text
    assert "not integrated" not in caplog.text


def test_read_maze_is_accepted_without_game_state(running_node, caplog):
    _, bus = running_node(FakeGrabber())
    with caplog.at_level(logging.WARNING):
        bus.deliver(T.CS_COMMAND, {"cmd": "read_maze", "mode": None, "file": None, "speed": None}, writer="cs_app")
        time.sleep(0.2)
    assert "read_maze accepted" in caplog.text


def test_node_stops_at_the_end_of_a_clip(tmp_path):
    bus, grabber = FakeBus(), FakeGrabber(clip_frame_count=3)
    node = VisionNode(VisionVariables.load(), grabber, bus, make_calibrator(), clip_dir=tmp_path)
    thread = threading.Thread(target=node.run, daemon=True)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert bus.is_closed and grabber.is_closed


def test_status_shows_the_calibrator_values():
    class StubCalibrator:
        is_calibrated, markers_found, reprojection_error_mm = True, 4, 0.4

        def update(self, frame):
            return True

        def to_board_mm(self, u_px, v_px):  # BallTracker asks for it; a blob at one point is no ball
            return 0.0, 0.0

    node_bus = FakeBus()
    node = VisionNode(VisionVariables.load(), FakeGrabber(), node_bus, StubCalibrator())
    thread = threading.Thread(target=node.run, daemon=True)
    thread.start()
    time.sleep(STARTUP_WAIT_S + 0.3)
    node.stop()
    thread.join(timeout=2)
    latest = node_bus.messages(T.VISION_STATUS)[-1]
    assert latest["is_calibrated"] is True and latest["markers_found"] == 4
    assert latest["reprojection_error_mm"] == 0.4


def play_clip(frames: list[np.ndarray], clip_dir, path_planner: PathPlanner | None = None) -> FakeBus:
    """Run a VisionNode over these frames, as a clip, until the clip ends; the bus holds what it published."""
    bus = FakeBus()
    grabber = FakeGrabber(clip_frames=frames, arrival_delay_s=ARRIVAL_DELAY_S)
    node = VisionNode(ball_variables(), grabber, bus, make_calibrator(), clip_dir=clip_dir, path_planner=path_planner)
    node.run()
    return bus


def test_ball_is_published_for_every_frame(tmp_path):
    config = load_vision_config()
    bus = play_clip([scene(config, (30.0, -20.0, BALL_DIAMETER_MM))] * 3, tmp_path)
    balls = bus.messages(T.VISION_BALL)
    assert [ball["seq"] for ball in balls] == [0, 1, 2]
    for ball in balls:  # also the first one: the markers and the ball are found in the same frame
        assert (ball["x_mm"], ball["y_mm"]) == pytest.approx((30.0, -20.0), abs=POSITION_TOLERANCE_MM)
        assert (ball["meas_x_mm"], ball["meas_y_mm"]) == pytest.approx((30.0, -20.0), abs=POSITION_TOLERANCE_MM)
        assert (ball["is_visible"], ball["is_predicted"], ball["is_on_exit"]) == (True, False, False)
        assert ARRIVAL_DELAY_S * 1000 <= ball["frame_age_ms"] < MAX_FRAME_AGE_MS


def test_ball_speed_comes_from_the_arrival_times_of_the_frames(tmp_path):
    """The fake camera gives a frame every 33 ms plus the time Vision needs, so the speed is a little under 90."""
    bus = play_clip(rolling_ball(load_vision_config()), tmp_path)
    latest = bus.messages(T.VISION_BALL)[-1]
    assert latest["vx_mm_s"] == pytest.approx(ROLLING_SPEED_MM_S, rel=0.5)
    assert latest["vy_mm_s"] == pytest.approx(0.0, abs=ROLLING_SPEED_MM_S / 10)


def test_ball_is_not_published_until_the_markers_have_been_seen_once(tmp_path):
    """IF-04. After that it is published for every frame, also when the markers are hidden for a long time."""
    with_markers = scene(load_vision_config())
    without_markers = np.full_like(with_markers, GREY)
    hidden_for_long = [without_markers] * (LAST_HOMOGRAPHY_HOLD_FRAMES + 2)
    bus = play_clip([without_markers, without_markers, with_markers] + hidden_for_long, tmp_path)
    assert len(bus.messages(T.VISION_BALL)) == 1 + len(hidden_for_long)


def test_route_answers_every_ball_message_while_a_maze_exists(tmp_path):
    """The example maze: from the cell north of the start the route goes east and then south to the exit."""
    frames = [scene(load_vision_config(), (*NORTH_OF_START_MM, BALL_DIAMETER_MM))] * 3
    bus = play_clip(frames, tmp_path, planner_with_example_maze())
    routes = bus.messages(T.PLAN_ROUTE)
    assert [route["ball_seq"] for route in routes] == [ball["seq"] for ball in bus.messages(T.VISION_BALL)] == [0, 1, 2]
    for route in routes:
        assert (route["maze_id"], route["status"]) == ("example-2x2", "valid")
        assert route["ball_cell"] == {"row": 1, "col": 0}
        assert route["target_points_mm"] == [[20.0, 20.0], [20.0, -20.0]]
        assert route["distance_to_exit_cells"] == 2


def test_route_is_invalid_while_the_ball_is_not_visible(tmp_path):
    bus = play_clip([scene(load_vision_config())] * 2, tmp_path, planner_with_example_maze())
    routes = bus.messages(T.PLAN_ROUTE)
    assert [route["ball_seq"] for route in routes] == [0, 1]
    for route in routes:
        assert (route["maze_id"], route["status"], route["ball_cell"]) == ("example-2x2", "invalid", None)
        assert (route["target_points_mm"], route["distance_to_exit_cells"]) == ([], None)


def test_no_route_is_published_without_a_maze(tmp_path):
    bus = play_clip([scene(load_vision_config(), (*NORTH_OF_START_MM, BALL_DIAMETER_MM))] * 2, tmp_path)
    assert len(bus.messages(T.VISION_BALL)) == 2
    assert bus.messages(T.PLAN_ROUTE) == []
