"""Shared bus helper for every Python program (IF-03).

    from shared.bus import Bus
    from shared import topics as T

    bus = Bus("vision")                     # program id = envelope writer
    bus.connect()                           # LWT + sys/online/vision = true
    bus.subscribe(T.GAME_STATE, on_state)   # on_state(topic, msg, t_recv_s)
    bus.publish(T.VISION_BALL, {...})       # envelope, QoS, retain and checks are added here

What it does for you:
- envelope: timestamp_s (wall clock at start + perf_counter), seq per topic, version, writer
- QoS and retained flag from shared/interfaces/topics.json
- schema check on publish (your bug) and on receive (rejects unknown versions / bad payloads)
- drops repeated QoS 1 deliveries (same writer, seq and timestamp_s)
- drops writer = replay unless subscribe(..., accept_replay=True)
- sys/online/<program>: true on connect, false via MQTT Last Will
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Callable

import paho.mqtt.client as mqtt

from shared import topics as T
from shared.interfaces import ValidationError, validate

log = logging.getLogger("ondos.bus")

Callback = Callable[[str, object, float], None]


class Clock:
    """Laptop clock (IF-03): wall clock taken once, then perf_counter differences."""

    def __init__(self) -> None:
        self._t0_wall = time.time()
        self._t0_perf = time.perf_counter()

    def now_s(self) -> float:
        return self._t0_wall + (time.perf_counter() - self._t0_perf)


CLOCK = Clock()


def now_s() -> float:
    return CLOCK.now_s()


def age_s(msg: dict, now: float | None = None) -> float:
    """Age of a message from its envelope timestamp_s (IF-03)."""
    return (now_s() if now is None else now) - msg["timestamp_s"]


class Bus:
    def __init__(self, program: str, host: str = T.BROKER_HOST, port: int = T.BROKER_TCP_PORT,
                 validate_messages: bool = True) -> None:
        if program not in T.WRITER_VALUES:
            raise ValueError(f"unknown program {program!r}; allowed: {T.WRITER_VALUES}")
        self.program = program
        self.host, self.port = host, port
        self.validate_messages = validate_messages
        self._seq: dict[str, int] = {}
        self._subs: list[tuple[str, Callback, bool]] = []
        self._seen: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self.rejected = 0  # messages dropped by the receive checks
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ondos-{program}-{id(self):x}")
        self._client.will_set(T.sys_online(program), json.dumps(False), qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ------------------------------------------------------------ connection
    def connect(self, timeout_s: float = 5.0) -> None:
        self._client.connect(self.host, self.port, keepalive=10)
        self._client.loop_start()
        if not self._connected.wait(timeout_s):
            raise ConnectionError(f"no broker at {self.host}:{self.port}")

    def is_connected(self) -> bool:
        """True while the broker connection is up. Becomes False as soon as the connection drops and True again after the automatic reconnect."""
        return self._connected.is_set()

    def close(self) -> None:
        """Clean shutdown: sys/online/<program> = false, then disconnect."""
        if self._connected.is_set():
            self._client.publish(T.sys_online(self.program), json.dumps(False), qos=1, retain=True).wait_for_publish(2)
        self._client.disconnect()
        self._client.loop_stop()
        self._connected.clear()

    def __enter__(self) -> "Bus":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._connected.clear()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        client.publish(T.sys_online(self.program), json.dumps(True), qos=1, retain=True)
        with self._lock:
            subs = list(self._subs)
        for pattern, _, _ in subs:
            client.subscribe(pattern, qos=1)
        self._connected.set()

    # ------------------------------------------------------------ publish
    def envelope(self, topic: str) -> dict:
        info = T.topic_info(topic)
        with self._lock:
            seq = self._seq.get(topic, 0)
            self._seq[topic] = seq + 1
        return {"timestamp_s": now_s(), "seq": seq, "version": info["version"], "writer": self.program}

    def publish(self, topic: str, fields: dict | bytes | bool) -> dict | bytes | bool:
        """Publish the topic's own fields; the envelope is added here. Returns what was sent."""
        info = T.topic_info(topic)
        if info["payload"] == "json":
            overlap = {"timestamp_s", "seq", "version", "writer"} & set(fields)
            if overlap:
                raise ValueError(f"{topic}: envelope fields {sorted(overlap)} are filled in by the bus helper")
            msg = {**self.envelope(topic), **fields}
        else:
            msg = fields
        self.publish_raw(topic, msg)
        return msg

    def publish_raw(self, topic: str, msg, retain: bool | None = None) -> None:
        """Publish a complete message as is (used by the playback tool)."""
        info = T.topic_info(topic)
        if self.validate_messages:
            validate(topic, msg)
        if info["payload"] == "jpeg":
            data = bytes(msg)
        else:
            data = json.dumps(msg, separators=(",", ":"), allow_nan=False)
        self._client.publish(topic, data, qos=info["qos"], retain=info["retained"] if retain is None else retain)

    def clear_retained(self, topic: str) -> None:
        """Remove the retained message of a topic (test brokers between tests)."""
        self._client.publish(topic, b"", qos=1, retain=True).wait_for_publish(2)

    def resubscribe(self) -> None:
        """Subscribe again to every pattern, so retained messages are delivered again (Recorder, IF-09)."""
        with self._lock:
            patterns = [p for p, _, _ in self._subs]
        for p in patterns:
            self._client.unsubscribe(p)
            self._client.subscribe(p, qos=1)

    # ------------------------------------------------------------ subscribe
    def subscribe(self, pattern: str, callback: Callback, accept_replay: bool = False) -> None:
        """callback(topic, msg, t_recv_s). pattern may use MQTT wildcards (+, #)."""
        with self._lock:
            self._subs.append((pattern, callback, accept_replay))
        if self._connected.is_set():
            self._client.subscribe(pattern, qos=1)

    def unsubscribe(self, pattern: str, callback: Callback | None = None) -> int:
        """Stop receiving a pattern. With callback, only that callback is removed; without it, every callback
        of the pattern. The broker subscription ends when no callback is left for the pattern.
        Returns how many callbacks were removed."""
        with self._lock:
            kept = [s for s in self._subs if not (s[0] == pattern and (callback is None or s[1] == callback))]
            removed = len(self._subs) - len(kept)
            self._subs = kept
            pattern_unused = all(s[0] != pattern for s in kept)
        if removed and pattern_unused and self._connected.is_set():
            self._client.unsubscribe(pattern)
        return removed

    def _on_message(self, client, userdata, m: mqtt.MQTTMessage) -> None:
        t_recv = now_s()
        topic = m.topic
        if not m.payload:  # a cleared retained topic
            return
        try:
            info = T.topic_info(topic)
        except KeyError:
            log.warning("message on unknown topic %s dropped", topic)
            self.rejected += 1
            return
        try:
            msg = bytes(m.payload) if info["payload"] == "jpeg" else json.loads(m.payload)
            if self.validate_messages:
                validate(topic, msg)
        except (ValueError, ValidationError) as e:
            log.warning("bad message on %s dropped: %s", topic, e)
            self.rejected += 1
            return
        is_replay = isinstance(msg, dict) and msg.get("writer") == "replay"
        # Repeated QoS 1 deliveries are dropped; retained deliveries (new subscription) are always passed on.
        if isinstance(msg, dict) and not m.retain and self._is_repeat(topic, msg):
            return
        with self._lock:
            subs = list(self._subs)
        for pattern, cb, accept_replay in subs:
            if is_replay and not accept_replay:
                continue
            if mqtt.topic_matches_sub(pattern, topic):
                try:
                    cb(topic, msg, t_recv)
                except Exception:  # a bad callback must not stop the bus thread
                    log.exception("callback for %s failed", topic)

    def _is_repeat(self, topic: str, msg: dict) -> bool:
        key = (msg["writer"], msg["seq"], msg["timestamp_s"])
        with self._lock:
            seen = self._seen.setdefault(topic, deque(maxlen=32))
            if key in seen:
                return True
            seen.append(key)
        return False
