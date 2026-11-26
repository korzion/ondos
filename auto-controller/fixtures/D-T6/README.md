# D-T6 Training rows

Requirement: D-R6

**Method:** Recording with a maze change.

**Pass if:** Rows as expected; none mixes the two mazes.

## Inputs

- `recording_maze_change.jsonl`: IF-09 JSONL game recording containing an in-game maze change (`maze-a` → `paused` → `maze-b`).
  - Header (`mode: "ai"`) intentionally differs from the active playing mode after a mode change in `ready` (`mode: "glove"`), verifying that rows follow `game/state.mode` (IF-09).
  - On playing frames, `plan/route` arrives 2–3 ms after `vision/ball` (as on the live bus) and is matched by `route.ball_seq == ball.seq`, so cell transitions (e.g. `seq` 14 entering `{1, 0}`) receive their own route rather than the previous sample's route.
  - Includes `ready`, `paused`, and `finished` ball samples (`seq` 1, 20, 40) that must be excluded.
  - Includes a `writer: "replay"` ball sample (`seq` 12), a non-visible ball sample (`seq` 13), and an unmatched ball sample without a route (`seq` 16, `route_mismatch`) that must be excluded.
  - Includes a `platform/state` gap > 100 ms (`seq` 15 at 140 ms) that must be marked `is_platform_stale = true` / `is_usable_for_imitation = false` and excluded from default training rows.
  - Includes a `glove/state` message whose `hand_tilt_*` differs from `platform/state.applied_tilt_*`, verifying that imitation labels use `applied_tilt_*` from `platform/state` (IF-09).
  - Includes a ball sample after switching to `maze-b` before any `maze-b` route arrives (`seq` 30, `maze_mismatch`) and a `no_path` route (`seq` 31, `invalid_route`), both excluded without mixing `maze-a` and `maze-b`.
- `expected.json`: Hand-checked expected `maze_ids`, `kept_rows`, `stale_platform_ball_seqs`, and `excluded` counts for `recording_maze_change.jsonl`.

### What can be edited

You may edit values in `recording_maze_change.jsonl` and `expected.json`, or pass a custom folder with `--input DIR`. If an `--input DIR` folder has no `expected.json`, `run_test.py D-T6` still runs all universal rule checks (causality, `route.ball_seq == ball.seq`, no cross-maze mixing, freshness, label provenance, and contiguous maze transitions).

## Running

```bash
python auto-controller/run_test.py D-T6
python auto-controller/run_test.py D-T6 --input /path/to/custom/dir
```
