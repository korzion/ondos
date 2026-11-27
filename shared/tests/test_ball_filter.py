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
