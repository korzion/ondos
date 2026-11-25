# D-T6 Training rows

Requirement: D-R6

**Method:** Recording with a maze change.

**Pass if:** Rows as expected; none mixes the two mazes.

## Inputs

- `recording_maze_change.jsonl`: IF-09 JSONL game recording containing an in-game maze change (`maze-a` → `paused` → `maze-b`).
  - Header (`mode: "ai"`) intentionally differs from the active playing mode after a mode change in `ready` (`mode: "glove"`), verifying that rows follow `game/state.mode` (IF-09).
  - Includes `ready`, `paused`, and `finished` ball samples (`seq` 1, 20, 40) that must be excluded.
  - Includes a `writer: "replay"` ball sample (`seq` 12) and a non-visible ball sample (`seq` 13) that must be excluded.
  - Includes a `platform/state` gap > 100 ms (`seq` 15 at 140 ms) that must be marked `is_platform_stale = true` / `is_usable_for_imitation = false` and excluded from default training rows.
  - Includes a `glove/state` message whose `hand_tilt_*` differs from `platform/state.applied_tilt_*`, verifying that imitation labels use `applied_tilt_*` from `platform/state` (IF-09).
  - Includes a ball sample after switching to `maze-b` before `plan/route` updates (`seq` 30, mismatched `maze_id`) and a `no_path` route (`seq` 31), both excluded without mixing `maze-a` and `maze-b`.

### What can be edited

You may edit values in `recording_maze_change.jsonl` or pass another `*.jsonl` recording via `--input DIR`:

- Edit `t_recv_s`, ball positions/velocities, `platform/state.applied_tilt_*`, `game/state.state`/`mode`, or `maze_id` values (keeping messages valid per `shared/interfaces/schemas/`).
- `run_test.py D-T6 [--input DIR]` computes expected rows independently from the JSONL file and checks causality (`t_* <= t_recv_s`), no cross-maze joins, stale-platform marking, and reference output equality.

## Running

```bash
python auto-controller/run_test.py D-T6
python auto-controller/run_test.py D-T6 --input /path/to/custom/dir
```
