# E-T6 Missing data

Requirement: E-R4

**Method:** Stop each topic in turn.

**Pass if:** Warning appears within 1 s after that topic's max delay.

## Inputs

`params.json` is the only input file. The test builds the run from it: every topic below is published at its
rate (playback tool, fixture mode), and after a warm-up each topic is stopped in turn while the others keep
coming. A stopped topic stays silent for its max delay + `warning_window_s` + `silence_margin_s`, then comes back.

| Key | Meaning |
| --- | --- |
| `topics` | Each topic with a Control Station max delay (interface appendix, "Control Station" reader rows): its publish rate `rate_hz` and `max_delay_ms`. The app's own values are in `src/renderer/topicHealthMonitor.ts`. |
| `health_log_path` | Health log file, relative to `control-station/`. |
| `warm_up_s` | Time with every topic coming before the first one is stopped. |
| `recovery_s` | Time between a topic coming back and the next one stopping. |
| `warning_window_s` | E-R4: the warning must show at most this long after the max delay, and clear at most this long after data returns. |
| `silence_margin_s` | Extra silence after the window, so a late warning is still seen. |
| `early_tolerance_ms` | A warning earlier than the max delay minus this is a failure (timer jitter only). |

The test measures each topic's last message before its pause with its own subscriber, on the same wall clock as
the app's log. For every topic it checks that the warning comes not before the max delay, at most 1 s after it, and
clears when data returns. It also checks that no topic is warned about while it keeps coming. At the end it clears
the retained `game/state` and `vision/status` it left on the broker.

The design document gives no timing tolerances; `early_tolerance_ms` and the margins are our choice.

## How to run

1. Start a local broker: `mosquitto -c shared/bus/mosquitto.conf`.
   On Windows, if `mosquitto` is not on the PATH:
   `& "C:\Program Files\mosquitto\mosquitto.exe" -c shared/bus/mosquitto.conf -v`
2. Start the app with the health log on (PowerShell, in `control-station/`):
   `$env:ONDOS_HEALTH_LOG = "out/e-t6-health-log.jsonl"; npm run dev`
   Without the variable the app writes no log. Keep the window visible: a minimized or covered window slows its
   timers down and the warnings come late.
   Run only the broker and the app: no GameManager, no fixture publishers and no real modules. Anything else
   that publishes these topics keeps them coming during their pause (for example `game/state` from GameManager),
   and the test fails.
3. In another terminal (venv active): `python run_test.py E-T6` and answer `y` to the one manual check.
   The run takes about 25 s and prints PASS or FAIL for each topic.

Each line of the health log is one change of a warning: `t_s` (wall clock), `topic` and `is_missing`.

## Broken version (end of the demo)

In `src/renderer/topicHealthMonitor.ts`, change the `platform/state` max delay from `200` to `2000`, restart the
app as in step 2 and run the test again. `platform/state` misses its window and the test prints FAIL; its
"warning shown" check fails too, because the 1.7 s pause is shorter than the new delay. Set it back to `200` afterwards.
