# Fixture publisher (E, issue #87)

Plays the other modules for the Dec 4 demo (design document E.9): the platform bridge (A), Vision (C) and the Auto Controller (D). It plays **ready data files** and answers the commands the app sends, so the Control Station runs with no other module. It has no maze, route or controller logic and never writes `game/state` or `game/warning` (GameManager's, IF-05).

Two separate tools:

| Tool | Job | Used by |
| --- | --- | --- |
| `fixture_publisher.py` | Plays `data/` on the bus, answers `e_stop`, `clear_e_stop`, `read_maze`, `cs/variables/<key>` | the demo |
| `make_fixture.py` | Turns the simple files in `inputs/` into the ready files in `data/` (distance map, routes, ball and platform samples) | only you, before the demo |

The publisher and the tests never import `make_fixture.py`. The ready files in `data/` are committed, so the demo works without running it.

## Run

```
mosquitto -c shared/bus/mosquitto.conf                                     # broker (TCP 1883, WebSocket 9001)
python control-station/fixtures/fixture_publisher/fixture_publisher.py     # from the repository root, venv active
python control-station/fixtures/fixture_publisher/fixture_publisher.py --no-respond    # play only, answer nothing (E-T4)
```

Options: `--host`, `--port`, `--data DIR`. Stop with `q` + Enter or Ctrl+C. Each program it stands in for has its own connection, so `sys/online/<program>` is true while it runs. The data plays in a loop of 18 s.

## What is in `data/`

Every line of a `.jsonl` file is `{"t_s", "topic", "msg"}`, the same format as `python -m shared.tools.replay fixture`. `msg` holds the topic's own fields; the envelope is added on publish.

| File | Plays |
| --- | --- |
| `samples.jsonl` | `vision/ball` (30 Hz), `platform/state`, `glove/state` (50 Hz) |
| `route_start.jsonl`, `route_changed.jsonl` | `plan/route` (30 Hz) of the first and the second maze |
| `controller_*.jsonl` | `control/target_tilt` (30 Hz), `ai/status` (10 Hz), `vision/status` (1 Hz) |
| `edit_*.jsonl` | `vision/edit_state` at 1 Hz: clear (per maze), hand_present, rescanning |
| `start.jsonl`, `maze_changed.jsonl`, `hand.jsonl`, `read_maze.jsonl` | played once: `vision/maze`, `plan/distance_map`, and the edit_state change |
| `behaviour.json` | which files play after which command or key (see below) |
| `variables_spec.json` | The variables of each module. **Edited by hand**, `make_fixture.py` leaves it alone |
| `events.json` (optional) | Keys pressed at a time: `[{"t_s": 20, "key": "h"}, {"t_s": 25, "key": "c"}]` |

`behaviour.json` has `loop_s`, a `start` list and the actions of each command (`commands`) and key (`triggers`). An action is one of: `{"play": file}` (once), `{"streams": [files]}` (the files now playing in a loop), `{"override": {topic: {field: value}}}` and `{"clear_override": [topic]}` (fields set on every later message of the topic), `{"after_s": n, "do": [actions]}`.

A variable the app sets is clamped to its `min`/`max` (or checked against `choices`) from `variables_spec.json`, and the owner publishes its spec again with the value in use.

## Edit the demo

**Simple way: edit `inputs/`, then regenerate**

```
python control-station/fixtures/fixture_publisher/make_fixture.py
```

| File | What you can change |
| --- | --- |
| `inputs/maze.txt`, `maze_after_change.txt` | The two mazes as a text grid. `#` wall, `.` open, `S` start, `E` exit. Lines `2 x rows + 1` long, border and corners `#`, the top line is north. Both mazes need the same size and exit |
| `inputs/ball_path.json` | `cells` `[row, col]` the ball walks through (the same cell twice = it waits there), `seconds_per_cell`, `end_hold_s` (how long it stands on the last cell: the `not_moving` warning) |
| `inputs/platform.json` | `cell_size_mm`, `tilt_limit_deg`, `tilt_gain_deg_per_mm`, `rescan_s`, `battery_pct` |

The generator checks its output before it writes: every cell of a distance map is 1 + its smallest open neighbour, every route stays on open cells and gets one step closer each point, and every line is a valid message of its topic. A wrong input stops it with the file and line.

**Direct way:** edit a ready file in `data/` (a value in `samples.jsonl`, an action in `behaviour.json`) and start the publisher again. Running `make_fixture.py` later overwrites everything in `data/` except `variables_spec.json` and `events.json`.

## Manual triggers (letter + Enter)

| Key | Action |
| --- | --- |
| `h` | A hand enters: `edit_state = hand_present`, the route stops |
| `c` | The hand leaves: the second maze, its distance map and routes, `edit_state = clear` |
| `n` / `y` | Stop / start answering commands |
| `b`, `v`, `a` | bridge, vision, auto_controller go offline (capital letter: back online) |
| `q` | Quit |

`h`, `c` and the commands are defined in `behaviour.json`; `n`, `y` and the program keys are built in. Notes: `c` always plays the second maze (pressing it twice repeats it). `read_maze` reads the first maze again. `ball_seq` in `plan/route` is the sample number inside the loop.

## Tests

```
python -m pytest control-station/fixtures/fixture_publisher -q
```

`test_fixture_data.py` checks the ready files by rules (maze, distance map, routes, ball, rates, behaviour) and imports neither the publisher nor the generator. `test_fixture_publisher.py` checks that the publisher plays the files and obeys `behaviour.json`. Both need no broker. The test plan is at the top of each file.
