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


def position_one_frame_after_a_jump_mm(filter_noise):
    ball_filter = BallFilter(filter_noise, LOST_TIMEOUT_MS)
    for frame in range(40):
        ball_filter.update(0.0, 0.0, frame * FRAME_S)
    return ball_filter.update(10.0, 0.0, 40 * FRAME_S).x_mm


def resting_velocity_spread_mm_s(filter_noise):
    noise = random.Random(1)
    ball_filter = BallFilter(filter_noise, LOST_TIMEOUT_MS)
    estimates = [ball_filter.update(noise.gauss(0.0, 1.0), 0.0, frame * FRAME_S) for frame in range(500)]
    return statistics.pstdev(estimate.vx_mm_s for estimate in estimates)


def test_a_higher_filter_noise_reacts_faster():
    smooth, default, fast = (position_one_frame_after_a_jump_mm(noise) for noise in (0.1, 1.0, 10.0))
    assert 0.0 < smooth < default < fast < 10.0


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
