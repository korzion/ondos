# shared/tools/replay

Playback tool (IF-09). Shared infrastructure, not a module: any module can call it.

## Fixture mode – feed a module under test (section 3)

```
python -m shared.tools.replay fixture <module>/fixtures/<TEST-ID>/input.jsonl
```

A fixture file has one JSON object per line: `{"t_s": 0.5, "topic": "vision/ball", "msg": {...}}`.

- `msg` holds the topic's own fields; `timestamp_s`, `seq` and `version` are filled in.
- `writer` is the program the fixture stands in for (e.g. `vision`), so the module under test treats the data as live. Put `"writer": "replay"` in `msg` to test that a module ignores replay.
- Each stand-in program gets its own connection, so `sys/online/<program>` is true while the fixture plays. Add a line with topic `sys/online/vision` and `msg: false` to make Vision go offline.
- To make data stale, leave a gap in `t_s`.

In a `run_test.py`, use `t.play_fixture("input.jsonl")` and `t.observe([...], seconds)`.

## Replay mode – show a recorded game

```
python -m shared.tools.replay replay recordings/20261204-140500.jsonl --speed 1
python -m shared.tools.replay listen --recordings recordings     # waits for cs/command replay from the app
```

- Plays every line on its topic with the original gaps divided by the speed (0.5, 1, 2); `timestamp_s` moves to the replay clock, `seq` and the other fields stay.
- `writer = replay`, `retain = false`; the bridge, GameManager, the controllers and the Recorder ignore these messages.
- Never publishes `game/state`, `cs/command`, `cs/variables/*`, `sys/online/*` or `vision/image`.
- Skips a topic while its real writer is online.
- `replay_pause`, `replay_resume`, `replay_stop` on `cs/command` (from the app).
