# D-T5 PID output

Requirement: D-R5

**Method:** Reference sequences with saturation, stop and restart.

**Pass if:** Matches the expected outputs; no windup.

```
python run_test.py D-T5
python run_test.py D-T5 --input <folder with your own sequences.json>
```

## Inputs

`sequences.json`

| Field | Meaning |
| --- | --- |
| `settings` | PID gains and limits (D.7 names) and `max_tilt_deg`; used by every sequence |
| `tolerance_deg` | Largest allowed difference between an output and its expected value |
| `sequences[].settings` | Optional: overrides some settings for this sequence only |
| `sequences[].steps[]` | One ball sample each, in order, or `{"reset": true}` |
| `steps[].ball` | The vision/ball fields the PID uses: `timestamp_s`, `x_mm`, `y_mm`, `vx_mm_s`, `vy_mm_s` |
| `steps[].target_points_mm` | As in plan/route; the PID uses the first point |
| `steps[].expected_tilt_deg` | Optional hand-calculated `[target_tilt_x_deg, target_tilt_y_deg]` |
| `steps[].note` | Optional label printed with that check |

The test feeds every sequence to a fresh PIDController as AutoControllerApp does:
`dt_s` is the difference of consecutive `timestamp_s`, and the first sample and the first sample after a reset have no `dt_s`.

| Sequence | What it shows |
| --- | --- |
| tracking | P, I and velocity damping on a small error |
| saturation | A far target saturates the output at `max_tilt_deg`; afterwards the output shows that the integral did not grow (no windup) |
| integral_limit | With a large Ki the integral stops at `pid_integral_limit_deg`, unwinds when the error changes sign, and is held while the output is saturated |
| stop_restart | Reset (pause, mode change, new maze_id, fault, invalid input) clears the integral; the restart gives the first-sample output again |
| long_gap | 2 s between samples: the integral step is capped at `CONTROLLER_INPUT_MAX_AGE_MS` (0.1 s) |
| clock_step_back | A sample older than the previous one (dt < 0): the integral does not move |

## Checks

For every sequence:

1. Every output matches the D.5 formula, computed step by step by the test itself (not by PIDController).
2. Every output is within ±`max_tilt_deg`.
3. Every step with `expected_tilt_deg` matches that hand-calculated value.

## What the instructor can change

- Any `settings` value, any ball position, velocity or timestamp, any target point; add or remove steps, resets or whole sequences. Checks 1 and 2 recompute the expected outputs, so the test still passes for a correct controller.
- A changed step keeps its old `expected_tilt_deg`. Delete it or write the new hand-calculated value; otherwise that check gives FAIL.
- For a deliberate FAIL: change one `expected_tilt_deg` (e.g. the saturation step 5 value `1.025` to `1.775`, which is what a controller with windup would give).
