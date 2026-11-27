# shared/ball_filter

The ball filter: filtered ball position and velocity and the flags is_visible and is_predicted, from the measured ball positions. Owner: C. Used by C at runtime (BallTracker) and by D in training (TrainEnv, IF-08), so both give the same numbers.

## Python

```python
from shared.ball_filter import BallFilter

ball_filter = BallFilter(filter_noise=1.0, lost_timeout_ms=200.0)  # the Vision variables of C.7
estimate = ball_filter.update(12.3, -40.1, t_s)  # a frame with a detection (x_mm, y_mm in the board frame)
estimate = ball_filter.update(None, None, t_s)   # a frame without a detection
estimate.x_mm, estimate.y_mm, estimate.vx_mm_s, estimate.vy_mm_s, estimate.is_visible, estimate.is_predicted
ball_filter.lost_timeout_ms = 300.0              # a live change of a setting
ball_filter.reset()                              # new game or new training episode
```

Call `update` once for every frame, also when the ball was not detected: the filter has no timer of its own.

Rules of the filter (vision/ball, IF-04):

- A frame without a detection is predicted at the last velocity (`is_predicted`), for at most `MAX_PREDICTION_MS` (70 ms) after the last detection.
- Then the ball is held until it is lost: the position stays, the velocity is 0 and `is_predicted` stays true.
- When the last detection is `lost_timeout_ms` old the ball is lost: `is_visible` is false, the velocity is 0 and the position is the last one with a detection.
- Only a new detection brings a held or lost ball back. It starts a new track at rest, and the velocity is found again within 3 frames (C-R5).
- A non-finite value, or a measurement with only one coordinate, raises `ValueError` and the filter does not change.

What `filter_noise` does (lower = smoother, higher = faster reaction), measured at 30 frames per second with 1 mm measurement noise:

| filter_noise | Position lag at 600 mm/s^2 | Velocity spread of a resting ball | Velocity follows a bounce after |
| --- | --- | --- | --- |
| 0.1 | 2.5 mm | 5 mm/s | 6 frames |
| 1.0 | 0.6 mm | 12 mm/s | 4 frames |
| 10.0 | 0.1 mm | 26 mm/s | 2 frames |

The bounce is a change from +200 to -100 mm/s without noise; the velocity "follows" when it is within 20 mm/s of the new one.

Starting decisions, where the design document leaves a detail open:

- The design document names the filter inside BallTracker (C.5). It lives in `shared/` because TrainEnv must use the same filter (IF-08, where "low-pass filter" means this one). Agreed in #47.
- Two independent Kalman filters, one per axis, each with the states position and velocity. Pure Python, so `shared/` needs no NumPy.
- `update` gives a `BallEstimate`, a named tuple with the six fields in the order above. BallTracker adds meas_x_mm and meas_y_mm to make a BallState.
- Before the first detection the answer is (0, 0, 0, 0, False, False).
- `MAX_PREDICTION_MS` limits the prediction, so that the estimate does not run on through the walls (C.8 only says the filter bridges the gap until `lost_timeout_ms`). It is a time, 2 frames at 30 frames per second, so it means the same for every frame period of TrainEnv; a constant and not a live setting. Agreed in #47.
- A held ball has velocity 0 and `is_predicted` true. A detection after the prediction time starts a new track, as after a loss.
- The "last known position" of a lost ball is the estimate of the last frame with a detection, not the predicted position.
- `is_visible` becomes false in the first frame that is `lost_timeout_ms` or more after the last detection, so up to one frame later than the timeout itself. The ages are compared with a tolerance of 0.01 ms, so that rounded timestamps do not move the loss by a frame.
- A lost ball comes back only with a new detection, also when `lost_timeout_ms` is raised meanwhile.
- A timestamp before the previous one (a restarted clock or recording) ends the track.
- `filter_noise` scales the process noise. `MEASUREMENT_NOISE_STD_MM`, `PROCESS_NOISE_MM2_PER_S3` and `INITIAL_VELOCITY_STD_MM_S` in `axis_kalman.py` are starting values, to be tuned with the real camera.
- A setting must be a finite number above 0 (not a bool or a string). The ranges of the settings are in `vision/config/variables.json`.
- Not done here: a detection far from the track is not refused, and a predicted position is not kept inside the plate or the walls (at 300 mm/s it moves 20 mm in the prediction time). The filter has no lock: call it from one thread.

Tests: `python -m pytest shared/tests/test_axis_kalman.py shared/tests/test_ball_filter.py`
