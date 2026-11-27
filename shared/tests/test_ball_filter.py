import math
import random
import statistics

import pytest

from shared.ball_filter import BallFilter

FILTER_NOISE = 1.0        # the starting value of the Vision variable filter_noise
LOST_TIMEOUT_MS = 250.0   # 8 frames of 1/32 s, so the timeout falls exactly on a frame
FRAME_S = 1 / 32          # a frame period that is exact in binary
SPEED_MM_S = 64.0         # 2 mm per frame


def new_filter():
    return BallFilter(FILTER_NOISE, LOST_TIMEOUT_MS)


def track_along_x(ball_filter, frames, y_mm=-20.0):
    # one detection per frame of a ball moving along +x at SPEED_MM_S; gives the estimate of the last frame
    for frame in range(frames):
        estimate = ball_filter.update(SPEED_MM_S * frame * FRAME_S, y_mm, frame * FRAME_S)
    return estimate


def test_before_the_first_detection_the_ball_is_not_visible():
    assert new_filter().update(None, None, 0.0) == (0.0, 0.0, 0.0, 0.0, False, False)


def test_the_first_detection_is_given_back_as_measured_and_at_rest():
    assert new_filter().update(10.0, -20.0, 0.0) == (10.0, -20.0, 0.0, 0.0, True, False)


def test_a_tracked_ball_gets_its_velocity_on_the_axis_it_moves_along():
    estimate = track_along_x(new_filter(), frames=40)
    assert estimate.vx_mm_s == pytest.approx(SPEED_MM_S, rel=0.01)
    assert estimate.x_mm == pytest.approx(78.0, abs=0.05)
    assert (estimate.y_mm, estimate.vy_mm_s) == (-20.0, 0.0)
    assert (estimate.is_visible, estimate.is_predicted) == (True, False)


def estimate_one_frame_after_a_jump(filter_noise):
    # the ball rests in the board centre and then jumps 10 mm on both axes
    ball_filter = BallFilter(filter_noise, LOST_TIMEOUT_MS)
    for frame in range(40):
        ball_filter.update(0.0, 0.0, frame * FRAME_S)
    return ball_filter.update(10.0, 10.0, 40 * FRAME_S)


def resting_velocity_spread_mm_s(filter_noise):
    noise = random.Random(1)
    ball_filter = BallFilter(filter_noise, LOST_TIMEOUT_MS)
    estimates = [ball_filter.update(noise.gauss(0.0, 1.0), 0.0, frame * FRAME_S) for frame in range(500)]
    return statistics.pstdev(estimate.vx_mm_s for estimate in estimates)


def test_a_higher_filter_noise_reacts_faster_on_both_axes():
    smooth, default, fast = (estimate_one_frame_after_a_jump(noise) for noise in (0.1, 1.0, 10.0))
    assert 0.0 < smooth.x_mm < default.x_mm < fast.x_mm < 10.0
    assert (smooth.y_mm, default.y_mm, fast.y_mm) == (smooth.x_mm, default.x_mm, fast.x_mm)


def test_a_lower_filter_noise_is_smoother():
    smooth, default, fast = (resting_velocity_spread_mm_s(noise) for noise in (0.1, 1.0, 10.0))
    assert smooth < default < fast


TRACKED_FRAMES = 40                       # the last detection is in frame 39
TIMEOUT_FRAMES = 8                        # LOST_TIMEOUT_MS / FRAME_S
LOST_FRAME = 39 + TIMEOUT_FRAMES          # the first frame LOST_TIMEOUT_MS after the last detection


def miss_frames(ball_filter, first_frame, last_frame):
    # frames without a detection; gives the estimate of the last one
    for frame in range(first_frame, last_frame + 1):
        estimate = ball_filter.update(None, None, frame * FRAME_S)
    return estimate


def test_a_frame_without_a_detection_is_predicted_at_the_same_velocity():
    ball_filter = new_filter()
    detected = track_along_x(ball_filter, TRACKED_FRAMES)
    predicted = miss_frames(ball_filter, 40, 40)
    assert predicted.x_mm == pytest.approx(detected.x_mm + detected.vx_mm_s * FRAME_S, abs=1e-9)
    assert (predicted.y_mm, predicted.vx_mm_s, predicted.vy_mm_s) == (detected.y_mm, detected.vx_mm_s, 0.0)
    assert (predicted.is_visible, predicted.is_predicted) == (True, True)


def test_several_frames_without_a_detection_are_predicted_one_after_the_other():
    ball_filter = new_filter()
    detected = track_along_x(ball_filter, TRACKED_FRAMES)
    predicted = miss_frames(ball_filter, 40, 41)
    assert predicted.x_mm == pytest.approx(detected.x_mm + detected.vx_mm_s * 2 * FRAME_S, abs=1e-9)
    assert predicted.vx_mm_s == detected.vx_mm_s


def test_after_the_prediction_time_the_ball_is_held_at_rest_until_it_is_lost():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    last_predicted = miss_frames(ball_filter, 40, 41)  # 62.5 ms after the detection, within MAX_PREDICTION_MS
    held = [miss_frames(ball_filter, frame, frame) for frame in range(42, LOST_FRAME)]
    assert held == [(last_predicted.x_mm, last_predicted.y_mm, 0.0, 0.0, True, True)] * len(held)


def test_the_prediction_time_is_a_time_and_not_a_number_of_frames():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    half_frame_s = FRAME_S / 2  # a camera twice as fast: 4 of its frames fit in the time of 2
    estimates = [ball_filter.update(None, None, 39 * FRAME_S + step * half_frame_s) for step in range(1, 7)]
    assert [estimate.vx_mm_s != 0.0 for estimate in estimates] == [True] * 4 + [False] * 2


def test_two_frames_of_a_camera_with_30_frames_per_second_are_predicted():
    frame_s = 1 / 30
    ball_filter = BallFilter(FILTER_NOISE, 200.0)
    for frame in range(TRACKED_FRAMES):
        ball_filter.update(SPEED_MM_S * frame * frame_s, -20.0, frame * frame_s)
    estimates = [ball_filter.update(None, None, (39 + step) * frame_s) for step in (1, 2, 3)]
    assert [estimate.vx_mm_s != 0.0 for estimate in estimates] == [True, True, False]


def test_a_detection_within_the_prediction_time_goes_on_with_the_track():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    miss_frames(ball_filter, 40, 40)
    found = ball_filter.update(SPEED_MM_S * 41 * FRAME_S, -20.0, 41 * FRAME_S)
    assert found.vx_mm_s == pytest.approx(SPEED_MM_S, rel=0.01)
    assert (found.is_visible, found.is_predicted) == (True, False)


def test_a_detection_after_the_prediction_time_starts_a_new_track():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    miss_frames(ball_filter, 40, 42)
    found = ball_filter.update(-50.0, 30.0, 43 * FRAME_S)
    assert found == (-50.0, 30.0, 0.0, 0.0, True, False)


@pytest.mark.parametrize("start_s", [0.0, 1.76e9], ids=["time from zero", "Unix time"])
def test_the_frame_of_the_loss_does_not_depend_on_where_the_clock_starts(start_s):
    frame_s = 1 / 30  # not exact in binary: the age of the detection in frame 6 is 200 ms only up to rounding
    ball_filter = BallFilter(FILTER_NOISE, 200.0)
    t_s = start_s
    ball_filter.update(0.0, 0.0, t_s)
    visible = []
    for _ in range(7):
        t_s += frame_s
        visible.append(ball_filter.update(None, None, t_s).is_visible)
    assert visible == [True] * 5 + [False] * 2


def test_the_ball_is_lost_when_the_last_detection_is_as_old_as_the_timeout():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    still_predicted = miss_frames(ball_filter, 40, LOST_FRAME - 1)
    lost = miss_frames(ball_filter, LOST_FRAME, LOST_FRAME)
    assert (still_predicted.is_visible, still_predicted.is_predicted) == (True, True)
    assert (lost.is_visible, lost.is_predicted) == (False, False)


def test_the_timeout_counts_from_the_last_detection_and_not_from_the_last_frame():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    half_frame_s = FRAME_S / 2
    estimates = [ball_filter.update(None, None, 39 * FRAME_S + step * half_frame_s) for step in range(1, 17)]
    assert [estimate.is_visible for estimate in estimates] == [True] * 15 + [False]


def test_a_lost_ball_rests_at_the_last_detected_position():
    ball_filter = new_filter()
    detected = track_along_x(ball_filter, TRACKED_FRAMES)
    lost = miss_frames(ball_filter, 40, LOST_FRAME)
    assert lost == (detected.x_mm, detected.y_mm, 0.0, 0.0, False, False)


def test_a_lost_ball_stays_lost_when_the_timeout_is_raised():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    miss_frames(ball_filter, 40, LOST_FRAME)
    ball_filter.lost_timeout_ms = 1000.0
    after_the_change = miss_frames(ball_filter, LOST_FRAME + 1, LOST_FRAME + 1)
    assert (after_the_change.is_visible, after_the_change.is_predicted) == (False, False)


def test_the_first_detection_after_a_loss_starts_a_new_track():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    miss_frames(ball_filter, 40, LOST_FRAME)
    found = ball_filter.update(-50.0, 30.0, (LOST_FRAME + 1) * FRAME_S)
    assert found == (-50.0, 30.0, 0.0, 0.0, True, False)


def test_a_detection_after_a_stall_longer_than_the_timeout_starts_a_new_track():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    found = ball_filter.update(-50.0, 30.0, 39 * FRAME_S + 1.0)  # no frame at all for 1 s, e.g. a camera stall
    assert found == (-50.0, 30.0, 0.0, 0.0, True, False)


def test_a_second_detection_with_the_same_timestamp_does_not_move_the_ball_ahead():
    ball_filter = new_filter()
    detected = track_along_x(ball_filter, TRACKED_FRAMES)
    again = ball_filter.update(detected.x_mm, detected.y_mm, 39 * FRAME_S)
    assert again.x_mm == pytest.approx(detected.x_mm, abs=1e-9)
    assert again.vx_mm_s == pytest.approx(detected.vx_mm_s, abs=1e-9)


def test_a_detection_with_an_earlier_timestamp_starts_a_new_track():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    found = ball_filter.update(-50.0, 30.0, 0.0)  # the clock went back, e.g. a restarted recording
    assert found == (-50.0, 30.0, 0.0, 0.0, True, False)


def test_a_missing_detection_with_an_earlier_timestamp_loses_the_ball():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    estimate = ball_filter.update(None, None, 0.0)
    assert (estimate.is_visible, estimate.is_predicted) == (False, False)


BAD_SETTINGS = [0.0, -1.0, math.nan, math.inf, True, "1.0", None]


@pytest.mark.parametrize("bad_value", BAD_SETTINGS)
def test_a_filter_is_not_made_with_a_setting_that_is_not_a_positive_number(bad_value):
    with pytest.raises(ValueError, match="filter_noise"):
        BallFilter(bad_value, LOST_TIMEOUT_MS)
    with pytest.raises(ValueError, match="lost_timeout_ms"):
        BallFilter(FILTER_NOISE, bad_value)


@pytest.mark.parametrize("bad_value", BAD_SETTINGS)
def test_a_setting_that_is_not_a_positive_number_is_refused_and_the_old_one_stays(bad_value):
    ball_filter = new_filter()
    with pytest.raises(ValueError, match="filter_noise"):
        ball_filter.filter_noise = bad_value
    with pytest.raises(ValueError, match="lost_timeout_ms"):
        ball_filter.lost_timeout_ms = bad_value
    assert (ball_filter.filter_noise, ball_filter.lost_timeout_ms) == (FILTER_NOISE, LOST_TIMEOUT_MS)


def test_a_changed_timeout_is_used_from_the_next_frame():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    ball_filter.lost_timeout_ms = 62.5  # 2 frames
    assert [miss_frames(ball_filter, frame, frame).is_visible for frame in (40, 41)] == [True, False]


def test_reset_forgets_the_ball():
    ball_filter = new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    ball_filter.reset()
    assert ball_filter.update(None, None, 40 * FRAME_S) == (0.0, 0.0, 0.0, 0.0, False, False)
    assert ball_filter.update(-50.0, 30.0, 41 * FRAME_S) == (-50.0, 30.0, 0.0, 0.0, True, False)


@pytest.mark.parametrize("bad_input", [
    (math.nan, 0.0, 40 * FRAME_S),
    (0.0, math.inf, 40 * FRAME_S),
    (80.0, -20.0, math.nan),
    (None, None, math.inf),
    (80.0, None, 40 * FRAME_S),
    (None, -20.0, 40 * FRAME_S),
], ids=["x is nan", "y is inf", "time is nan", "time is inf", "y is missing", "x is missing"])
def test_a_bad_input_is_refused_and_changes_nothing(bad_input):
    ball_filter, twin = new_filter(), new_filter()
    track_along_x(ball_filter, TRACKED_FRAMES)
    track_along_x(twin, TRACKED_FRAMES)
    with pytest.raises(ValueError):
        ball_filter.update(*bad_input)
    next_frame = (SPEED_MM_S * 40 * FRAME_S, -20.0, 40 * FRAME_S)
    assert ball_filter.update(*next_frame) == twin.update(*next_frame)
