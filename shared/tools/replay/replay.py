"""Playback tool (IF-09): replay mode and fixture mode.

Replay mode – show a recorded game on the live broker:
    python -m shared.tools.replay replay recordings/20261204-140500.jsonl --speed 1
    python -m shared.tools.replay listen --recordings recordings   # waits for cs/command replay
  - publishes every line on its original topic with the original gaps / speed
  - writer = replay, retain = false, timestamp_s moved to the replay clock
  - never publishes game/state, cs/command, cs/variables/*, sys/online/* or vision/image
  - skips a topic while its real writer is online (sys/online/<program> = true)
  - replay_pause / replay_resume / replay_stop from cs/command (writer cs_app)

Fixture mode – feed a module under test on a local test broker (section 3):
    python -m shared.tools.replay fixture tilting-platform/fixtures/A-T3/input.jsonl
  - lines {"t_s": …, "topic": …, "msg": {…}}
  - envelope fields left out are filled in; writer = the program the fixture stands in for
  - each stand-in program gets its own connection, so sys/online/<program> = true while it plays
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

from shared import topics as T
from shared.bus import Bus, now_s
from shared.interfaces import validate_file

NEVER_REPLAYED_PREFIXES = ("cs/variables/", "sys/online/")
NEVER_REPLAYED = {T.GAME_STATE, T.CS_COMMAND, T.VISION_IMAGE}


def read_jsonl(path: Path) -> list[dict]:
    lines = []
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            raw = raw.strip()
            if raw:
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n}: not JSON: {e}") from None
    return lines


# --------------------------------------------------------------------- fixture
def load_fixture(path: Path) -> list[dict]:
    lines = read_jsonl(path)
    for n, line in enumerate(lines, 1):
        try:
            validate_file("fixture_line", line)
            T.topic_info(line["topic"])
        except Exception as e:
            raise ValueError(f"{path}:{n}: {e}") from None
    return sorted(lines, key=lambda l: l["t_s"])


def play_fixture(path: Path | str, host: str = T.BROKER_HOST, port: int = T.BROKER_TCP_PORT,
                 stop: threading.Event | None = None, validate_messages: bool = True) -> int:
    """Publish a fixture file at its times. Returns the number of messages sent."""
    lines = load_fixture(Path(path))
    buses: dict[str, Bus] = {}
    stop = stop or threading.Event()
    sent = 0
    try:
        t0 = time.perf_counter()
        for line in lines:
            delay = line["t_s"] - (time.perf_counter() - t0)
            if delay > 0 and stop.wait(delay):
                break
            topic, msg = line["topic"], line["msg"]
            info = T.topic_info(topic)
            writer = info["writer"]
            if isinstance(msg, dict) and msg.get("writer"):
                writer = msg["writer"]
            bus = buses.get(writer)
            if bus is None:
                bus = buses[writer] = Bus(writer, host, port, validate_messages=validate_messages)
                bus.connect()
            if info["payload"] == "json":
                full = {**bus.envelope(topic), **msg}
            elif info["payload"] == "jpeg":
                full = Path(path).parent.joinpath(msg).read_bytes()  # msg = JPEG file name
            else:
                full = msg
            bus.publish_raw(topic, full)
            sent += 1
        time.sleep(0.2)  # let QoS 1 messages leave before disconnecting
    finally:
        for bus in buses.values():
            bus.close()
    return sent


# --------------------------------------------------------------------- replay
class Replayer:
    def __init__(self, path: Path | str, speed: float = 1.0, host: str = T.BROKER_HOST,
                 port: int = T.BROKER_TCP_PORT) -> None:
        if speed not in (0.5, 1, 2):
            raise ValueError("speed must be 0.5, 1 or 2 (IF-07)")
        self.path = Path(path)
        self.speed = speed
        self.bus = Bus("replay", host, port)
        self.online: dict[str, bool] = {}
        self._paused = threading.Event()
        self._stop = threading.Event()
        self._finished = threading.Event()
        self.sent = 0
        self.skipped = 0

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        self._stop.set()

    def _on_online(self, topic: str, msg, t_recv_s: float) -> None:
        self.online[topic.rsplit("/", 1)[1]] = bool(msg)

    def _on_command(self, topic: str, msg, t_recv_s: float) -> None:
        if msg.get("writer") != "cs_app":
            return
        {"replay_pause": self.pause, "replay_resume": self.resume, "replay_stop": self.stop}.get(msg["cmd"], lambda: None)()

    @staticmethod
    def is_replayable(topic: str) -> bool:
        return topic not in NEVER_REPLAYED and not topic.startswith(NEVER_REPLAYED_PREFIXES)

    def is_finished(self) -> bool:
        """True once run() has returned: the file ended, stop() was called or the file was unreadable."""
        return self._finished.is_set()

    def run(self) -> None:
        try:
            self._play()
        finally:
            self._finished.set()

    def _play(self) -> None:
        lines = read_jsonl(self.path)
        if not lines or lines[0].get("type") != "header":
            raise ValueError(f"{self.path}: first line is not a recording header")
        validate_file("recording_header", lines[0])
        body = [l for l in lines[1:] if self.is_replayable(l["topic"]) and isinstance(l["msg"], dict)]
        if not body:
            return
        self.bus.subscribe("sys/online/+", self._on_online, accept_replay=True)
        self.bus.subscribe(T.CS_COMMAND, self._on_command)
        self.bus.connect()  # sys/online/replay = true before the first replayed message
        time.sleep(0.3)  # receive the retained sys/online states
        try:
            first_recv = body[0]["t_recv_s"]
            first_ts = body[0]["msg"]["timestamp_s"]
            start_perf = time.perf_counter()
            start_s = now_s()
            paused_total = 0.0
            for line in body:
                due = (line["t_recv_s"] - first_recv) / self.speed
                while True:
                    if self._stop.is_set():
                        return
                    if self._paused.is_set():
                        p0 = time.perf_counter()
                        while self._paused.is_set() and not self._stop.is_set():
                            time.sleep(0.05)
                        paused_total += time.perf_counter() - p0
                        continue
                    left = due - (time.perf_counter() - start_perf - paused_total)
                    if left <= 0:
                        break
                    time.sleep(min(left, 0.05))
                topic, msg = line["topic"], dict(line["msg"])
                if self.online.get(T.topic_info(topic)["writer"], False):
                    self.skipped += 1  # the real writer is running
                    continue
                msg["writer"] = "replay"
                msg["timestamp_s"] = start_s + (msg["timestamp_s"] - first_ts) / self.speed + paused_total
                self.bus.publish_raw(topic, msg, retain=False)
                self.sent += 1
        finally:
            self.bus.close()


def listen(recordings: Path, host: str, port: int) -> None:
    """Wait for cs/command replay from the Control Station and play the file."""
    import paho.mqtt.client as mqtt

    state: dict = {"replayer": None}

    def on_message(client, userdata, m):
        try:
            msg = json.loads(m.payload)
        except ValueError:
            return
        if msg.get("writer") != "cs_app" or msg.get("cmd") != "replay":
            return
        current = state["replayer"]
        if current is not None and not current.is_finished():
            return  # one replay at a time
        r = Replayer(recordings / msg["file"], msg["speed"], host, port)
        state["replayer"] = r
        threading.Thread(target=r.run, daemon=True).start()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ondos-replay-listener")
    client.on_message = on_message
    client.on_connect = lambda c, *a: c.subscribe(T.CS_COMMAND, qos=1)
    client.connect(host, port)
    print(f"waiting for cs/command replay (recordings: {recordings})")
    client.loop_forever()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m shared.tools.replay", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=T.BROKER_HOST)
    ap.add_argument("--port", type=int, default=T.BROKER_TCP_PORT)
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("replay", help="play a recording (IF-09 replay mode)")
    r.add_argument("file", type=Path)
    r.add_argument("--speed", type=float, default=1.0, choices=[0.5, 1.0, 2.0])
    f = sub.add_parser("fixture", help="play a fixture file on a local test broker")
    f.add_argument("file", type=Path)
    l = sub.add_parser("listen", help="wait for cs/command replay")
    l.add_argument("--recordings", type=Path, default=Path("recordings"))
    a = ap.parse_args(argv)
    if a.mode == "replay":
        rep = Replayer(a.file, a.speed, a.host, a.port)
        rep.run()
        print(f"replayed {rep.sent} messages, skipped {rep.skipped} (real writer online)")
    elif a.mode == "fixture":
        print(f"sent {play_fixture(a.file, a.host, a.port)} messages")
    else:
        listen(a.recordings, a.host, a.port)
    return 0
