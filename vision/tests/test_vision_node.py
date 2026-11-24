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
from vision.board_calibrator import BoardCalibrator
from vision.tests.message_helpers import with_envelope
from vision.vision_config import load_vision_config
from vision.vision_node import CAMERA_RETRY_PERIOD_S, VisionNode
from vision.vision_variables import CONFIG_KEY, VisionVariables

SPEC_TOPIC = T.variables_spec(CONFIG_KEY)
VARIABLES_TOPIC = T.cs_variables(CONFIG_KEY)
FRAME_PERIOD_S = 1.0 / 30.0
STARTUP_WAIT_S = 0.3


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

    def __init__(self, can_open: bool = True, clip_frame_count: int | None = None) -> None:
        self.can_open = can_open
        self.opened_indexes: list[int] = []
        self.exposures: list[tuple[float, float]] = []
        self.is_closed = False
        self._clip_frames_left = clip_frame_count
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
        return np.zeros((48, 64, 3), dtype=np.uint8), now_s()

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
