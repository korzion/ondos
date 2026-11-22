"""Bus helper and playback tool against a real Mosquitto (skipped when mosquitto is not installed)."""
import json
import shutil
import socket
import subprocess
import time

import pytest

from shared import topics as T
from shared.bus import Bus
from shared.tools.replay import Replayer, play_fixture

pytestmark = pytest.mark.skipif(shutil.which("mosquitto") is None, reason="needs mosquitto")


@pytest.fixture()
def broker():
    # No config file: Ubuntu's AppArmor profile lets mosquitto read configs only from /etc/mosquitto.
    # Without one, mosquitto 2 runs in local-only mode (127.0.0.1, anonymous), which is what the tests need.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(["mosquitto", "-p", str(port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            if p.poll() is not None:
                pytest.fail("mosquitto did not start:\n" + p.stdout.read().decode(errors="replace"))
            time.sleep(0.05)
    else:
        p.kill()
        pytest.fail("mosquitto did not open its port in 5 s")
    yield port
    p.terminate()
    p.wait()


def collect(port, patterns):
    got = []
    b = Bus("cs_app", port=port)
    for p in patterns:
        b.subscribe(p, lambda t, m, r: got.append((t, m)), accept_replay=True)
    b.connect()
    return b, got


BALL = {"x_mm": 1.0, "y_mm": 2.0, "vx_mm_s": 0.0, "vy_mm_s": 0.0, "is_visible": True, "is_predicted": False,
        "is_on_exit": False, "frame_age_ms": 20.0, "meas_x_mm": 1.0, "meas_y_mm": 2.0}


def test_publish_adds_envelope_and_online(broker):
    obs, got = collect(broker, ["vision/ball", "sys/online/+"])
    with Bus("vision", port=broker) as vision:
        vision.publish(T.VISION_BALL, BALL)
        vision.publish(T.VISION_BALL, BALL)
        time.sleep(0.3)
    time.sleep(0.3)
    obs.close()
    balls = [m for t, m in got if t == "vision/ball"]
    assert [m["seq"] for m in balls] == [0, 1]
    assert balls[0]["writer"] == "vision" and balls[0]["version"] == 1
    online = [m for t, m in got if t == "sys/online/vision"]
    assert online[0] is True and online[-1] is False


def test_bad_messages_and_replay_are_dropped(broker):
    obs, got = collect(broker, ["vision/ball"])
    plain = []
    obs.subscribe("vision/ball", lambda t, m, r: plain.append(m))  # does not accept replay
    with Bus("vision", port=broker, validate_messages=False) as raw:
        raw.publish(T.VISION_BALL, {**BALL, "x_mm": "oops"})           # bad type: dropped by receiver
        raw.publish_raw(T.VISION_BALL, {**raw.envelope(T.VISION_BALL), **BALL, "writer": "replay"})
        time.sleep(0.3)
    obs.close()
    assert obs.rejected == 1
    assert len(got) == 1 and got[0][1]["writer"] == "replay"
    assert plain == []


def test_publish_rejects_invalid_payload(broker):
    with Bus("vision", port=broker) as vision:
        with pytest.raises(Exception):
            vision.publish(T.VISION_BALL, {"x_mm": 1.0})


def test_fixture_mode_fills_envelope(broker, tmp_path):
    f = tmp_path / "in.jsonl"
    lines = [{"t_s": 0.0, "topic": "vision/ball", "msg": BALL},
             {"t_s": 0.05, "topic": "game/state", "msg": {"state": "playing", "mode": "ai", "game_id": "20261204-140500",
              "maze_id": "demo", "elapsed_s": 1.0, "cell": None, "distance_to_exit_cells": None,
              "progress_pct": 0.0, "result": "none"}},
             {"t_s": 0.1, "topic": "vision/ball", "msg": {**BALL, "writer": "replay"}}]
    f.write_text("\n".join(json.dumps(l) for l in lines))
    obs, got = collect(broker, ["vision/ball", "game/state", "sys/online/+"])
    assert play_fixture(f, port=broker) == 3
    time.sleep(0.3)
    obs.close()
    ball = [m for t, m in got if t == "vision/ball"]
    assert [m["writer"] for m in ball] == ["vision", "replay"]
    assert [m for t, m in got if t == "game/state"][0]["writer"] == "game_manager"
    assert {t for t, m in got if t.startswith("sys/online/") and m is True} >= {"sys/online/vision", "sys/online/game_manager"}


def test_replay_mode(broker, tmp_path):
    rec = tmp_path / "20261204-140500.jsonl"
    t0 = 1764849600.0
    env = lambda w, s, ts: {"timestamp_s": ts, "seq": s, "version": 1, "writer": w}
    rows = [{"type": "header", "format_version": 1, "game_id": "20261204-140500", "maze_id": "demo", "mode": "ai",
             "start_time_s": t0, "git_commit": None}]
    rows += [{"t_recv_s": t0 + i * 0.05, "topic": "vision/ball", "msg": {**env("vision", i, t0 + i * 0.05), **BALL}} for i in range(4)]
    rows += [{"t_recv_s": t0 + 0.06, "topic": "game/state", "msg": {"state": "playing"}},       # never replayed
             {"t_recv_s": t0 + 0.07, "topic": "cs/command", "msg": {"cmd": "pause"}},          # never replayed
             {"t_recv_s": t0 + 0.08, "topic": "sys/online/vision", "msg": True}]               # never replayed
    rec.write_text("\n".join(json.dumps(r) for r in rows))
    obs, got = collect(broker, ["#"])
    r = Replayer(rec, speed=2, port=broker)
    r.run()
    time.sleep(0.3)
    obs.close()
    balls = [m for t, m in got if t == "vision/ball"]
    assert r.sent == 4 and len(balls) == 4
    assert all(m["writer"] == "replay" for m in balls)
    assert [m["seq"] for m in balls] == [0, 1, 2, 3]
    gaps = [b["timestamp_s"] - a["timestamp_s"] for a, b in zip(balls, balls[1:])]
    assert all(abs(g - 0.025) < 1e-6 for g in gaps)   # speed 2 halves the gaps
    assert not any(t in ("game/state", "cs/command") for t, m in got)
    assert ("sys/online/replay", True) in got


def test_replay_skips_topic_whose_writer_is_online(broker, tmp_path):
    rec = tmp_path / "g.jsonl"
    t0 = 1764849600.0
    rows = [{"type": "header", "format_version": 1, "game_id": "20261204-140500", "maze_id": "demo", "mode": "ai",
             "start_time_s": t0, "git_commit": None},
            {"t_recv_s": t0, "topic": "vision/ball",
             "msg": {"timestamp_s": t0, "seq": 0, "version": 1, "writer": "vision", **BALL}}]
    rec.write_text("\n".join(json.dumps(r) for r in rows))
    with Bus("vision", port=broker):
        r = Replayer(rec, port=broker)
        r.run()
    assert r.sent == 0 and r.skipped == 1


def test_unsubscribe_counts_and_stops_delivery(broker):
    got_a, got_b = [], []
    on_a = lambda t, m, r: got_a.append(m)
    on_b = lambda t, m, r: got_b.append(m)
    obs = Bus("cs_app", port=broker)
    obs.subscribe("vision/ball", on_a)
    obs.subscribe("vision/ball", on_b)
    obs.connect()
    with Bus("vision", port=broker) as vision:
        vision.publish(T.VISION_BALL, BALL)
        time.sleep(0.3)
        assert obs.unsubscribe("vision/ball", on_a) == 1   # only this callback
        vision.publish(T.VISION_BALL, BALL)
        time.sleep(0.3)
        assert obs.unsubscribe("vision/ball") == 1         # the rest of the pattern
        assert obs.unsubscribe("vision/ball") == 0         # nothing left
        vision.publish(T.VISION_BALL, BALL)
        time.sleep(0.3)
    obs.close()
    assert len(got_a) == 1 and len(got_b) == 2
