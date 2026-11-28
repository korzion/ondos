# E-T1 Plot rate

Requirement: E-R1

**Method:** Replay a sample game and log draw times.

**Pass if:** Plots update at 20 Hz, with the last 30 s visible.

## Inputs

`params.json` is the only input file. The test builds the sample game from it (35 s of `vision/ball`, `platform/state`,
`glove/state` and `control/target_tilt`, each moving on a slow circle) and plays it with the playback tool in fixture mode.

| Key | Meaning |
| --- | --- |
| `play_duration_s`, `publish_rates_hz` | Length of the sample game and the publish rate of each plotted topic. |
| `draw_log_path` | Draw log file, relative to `control-station/`. |
| `expected_plot_rate_hz`, `plot_rate_tolerance_hz` | Wanted draw rate and how far the mean may be from it. The app's own rate is `plot_rate_hz` in `plotsTab.ts`. |
| `max_draw_gap_ms` | Longest allowed pause between two draws of one plot. One draw every 50 ms is normal; 120 ms lets one tick come a little late (timer jitter) but not two missed ticks. |
| `plot_window_s`, `plot_window_tolerance_s` | Wanted width of the time axis, after the first `plot_window_s` of the game. |
| `min_data_span_s` | The stored data must cover at least this much of the window. |

The design document gives no tolerances; the values above are our choice.

## How to run

1. Start a local broker: `mosquitto -c shared/bus/mosquitto.conf`.
   On Windows, if `mosquitto` is not on the PATH:
   `& "C:\Program Files\mosquitto\mosquitto.exe" -c shared/bus/mosquitto.conf -v`
2. Start the app with the draw log on (PowerShell, in `control-station/`):
   `$env:ONDOS_DRAW_LOG = "out/e-t1-draw-log.jsonl"; npm run dev`
   Without the variable the app writes no log. Open the **Plots** tab and keep the window visible: a minimized
   window, or one covered by other windows, counts as hidden. Its timers slow down and the test then correctly fails.
   If the test shows about 1 Hz, the window was hidden. Do not switch to another tab while the test runs: the
   plots are not drawn while another tab is open, so the test shows a long gap and a lower draw rate.
3. In another terminal (venv active): `python run_test.py E-T1` and answer `y` to the one manual check.
   The test plays the game for about 35 s, reads the draw log and prints PASS or FAIL for each plot.

Each line of the draw log is one real uPlot redraw: `t_s` (wall clock), `plot` (topic), `x_min_s`, `x_max_s`,
`oldest_s` and `points`. A topic's first chart is named after the topic; a second chart of the same topic with
another unit adds the unit (`vision/ball mm/s`, ball speed) and is not checked by this test.

## Broken version (end of the demo)

Set `plot_rate_hz` in `src/renderer/plotsTab.ts` to `5`, restart the app as in step 2 and run the test again.
The mean draw rate and the longest gap fail, so the test prints FAIL. Set it back to `20` afterwards.
