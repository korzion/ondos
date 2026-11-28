# D-T6 Training rows

Requirement: D-R6

**Method:** Recording with a maze change.

**Pass if:** Rows as expected; none mixes the two mazes.

## Inputs

- `recording_maze_change.jsonl`: IF-09 JSONL game recording containing an in-game maze change (`maze-a` → `paused` → `maze-b`) and a same-maze pause.
  - Header (`mode: "ai"`) intentionally differs from the active playing modes (`"glove"` in `maze-a`, `"simple"` in `maze-b`), verifying that rows follow `game/state.mode` (IF-09).
  - On playing frames, `plan/route` arrives 2–3 ms after `vision/ball` (as on the live bus) and is matched by `route.ball_seq == ball.seq`, so cell transitions (e.g. `seq` 14 entering `{1, 0}`) receive their own route rather than the previous sample's route.
  - Covers all `_check_planning` stale/cross-maze exclusions:
    - `seq` 9: `vision/maze` still `maze-old` while `game/state`, `plan/distance_map`, and `plan/route` are `maze-a` (`maze_mismatch`).
    - `seq` 27: `plan/distance_map` still `maze-a` after `vision/maze` switched to `maze-b` (`maze_mismatch`).
    - `seq` 28: `plan/route` matches `ball_seq=28` but still has `maze_id="maze-a"` (`maze_mismatch`).
    - `seq` 29: valid `plan/route` arrives 150 ms after `vision/ball` (`stale_route`).
    - `seq` 30: unmatched ball after switching to `maze-b` with `maze-a` in latest route (`maze_mismatch`), and `seq` 31: `status="no_path"` (`invalid_route`).
  - Covers `ready`, `paused`, and `finished` exclusions (`seq` 1, 20, 40), `writer: "replay"` (`seq` 12), `is_visible=false` (`seq` 13), unmatched `route_mismatch` (`seq` 16), and stale `platform/state` (`seq` 15 at 140 ms).
  - Includes `glove/state` whose `hand_tilt_*` differs from `platform/state.applied_tilt_*` (IF-09).
  - Tracks `prev_command_x_deg` / `prev_command_y_deg` from `control/target_tilt` (`seq` 32→33→34) and resets `is_episode_start=true`, `prev_command=null` after the maze change (`seq` 32) and after a same-maze pause (`seq` 35).
- `expected.json`: Hand-checked expected `maze_ids`, `kept_rows` (including `is_episode_start` and `prev_command_*`), `stale_platform_ball_seqs`, and `excluded` counts.

### What can be edited

You may edit values in `recording_maze_change.jsonl` and `expected.json`, or pass a custom folder with `--input DIR`. If an `--input DIR` folder has no `expected.json`, `run_test.py D-T6` still runs all universal rule checks (causality, `route.ball_seq == ball.seq`, no cross-maze mixing, freshness, label provenance, and contiguous maze transitions).

## Running

```bash
python auto-controller/run_test.py D-T6
python auto-controller/run_test.py D-T6 --input /path/to/custom/dir
```
