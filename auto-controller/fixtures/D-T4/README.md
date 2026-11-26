# D-T4 Only valid commands

Requirement: D-R4

**Method:** Fixture sequences for every state, both modes, stale and missing inputs, wrong `maze_id`, `no_path`, fault.

**Pass if:** Commands only when all conditions hold; otherwise none.

## Inputs

- `input.jsonl`: IF-09 fixture-mode timeline (`{"t_s", "topic", "msg"}`) played through `shared.tools.replay` covering 19 gating cases:
  1. `ball_seq=99` (`t=0.07s`): `playing` + `ai`, missing `platform/variables_spec` -> **blocked**
  2. `ball_seq=100` (`t=0.32s`): `setup` + `ai` -> **blocked**
  3. `ball_seq=1001` (`t=0.52s`): `ready` + `ai` -> **blocked**
  4. `ball_seq=1002` (`t=0.72s`): `playing` + `glove` -> **blocked**
  5. `ball_seq=101` (`t=0.92s`): `playing` + `ai`, all inputs fresh & valid -> **allowed (`ai/target_tilt`)**
  6. `ball_seq=102` (`t=1.17s`): `playing` + `simple`, all inputs fresh & valid -> **allowed (`control/target_tilt`)**
  7. `ball_seq=103` (`t=1.42s`): `paused` + `ai` -> **blocked**
  8. `ball_seq=104` (`t=1.67s`): `finished` + `simple` -> **blocked**
  9. `ball_seq=105` (`t=1.92s`): `e_stop` + `ai` -> **blocked**
  10. `ball_seq=106` (`t=2.17s`): `playing` + `ai`, `is_visible=false` -> **blocked**
  11. `ball_seq=107` (`t=2.42s`): `playing` + `ai`, route `maze_id="other-maze"` mismatch -> **blocked**
  12. `ball_seq=108` (`t=2.67s`): `playing` + `simple`, route `status="no_path"` -> **blocked**
  13. `ball_seq=109` (`t=2.92s`): `playing` + `ai`, `platform/state.fault="motor"` -> **blocked**
  14. `ball_seq=110` (`t=3.17s`): `playing` + `simple`, `platform/state.is_e_stop=true` -> **blocked**
  15. `ball_seq=111` (`t=3.57s`): `playing` + `ai`, `platform/state` stale (`180 ms > 100 ms`) -> **blocked**
  16. `ball_seq=112` (`t=3.95s`): `game/state` stale (`410 ms > 300 ms`) -> **blocked**
  17. `ball_seq=113` (`t=4.22s`): `writer="replay"` ball & route -> **blocked**
  18. `ball_seq=114` (`t=4.52s`): recovery `playing` + `ai` -> **allowed (`ai/target_tilt`)**
  19. `ball_seq=115` (`t=4.77s`): recovery `playing` + `simple` -> **allowed (`control/target_tilt`)**
- `expected.json`: hand-checkable reference listing `max_tilt_deg`, `expected_commands` (`ball_seq`, `mode`, `maze_id`), and `blocked_ball_seqs`.

### What can be edited

You may edit any `t_s`, `state`, `mode`, `maze_id`, `status`, `fault`, `is_e_stop`, `is_visible`, or `writer` field in `input.jsonl` (and update `expected.json` to match), or pass another folder with `--input DIR` containing both `input.jsonl` and `expected.json`.

## Running

Start a local MQTT broker and `auto_controller_app.py`, then run:

```bash
mosquitto -c shared/bus/mosquitto.conf
python auto-controller/auto_controller_app.py
python auto-controller/run_test.py D-T4
python auto-controller/run_test.py D-T4 --input /path/to/custom/dir
```
