import random
import statistics

import pytest

from shared.ball_filter import axis_kalman
from shared.ball_filter.axis_kalman import MEASUREMENT_NOISE_STD_MM, PROCESS_NOISE_MM2_PER_S3, AxisKalman

FRAME_S = 1 / 32  # a frame period that is exact in binary


def track(axis, positions_mm, frame_s=FRAME_S):
    # one measurement per frame, the first one starts the track; gives the filtered position of every frame
    axis.start(positions_mm[0])
    filtered_mm = [axis.position_mm]
    for position_mm in positions_mm[1:]:
        axis.predict(frame_s, PROCESS_NOISE_MM2_PER_S3)
        axis.correct(position_mm)
        filtered_mm.append(axis.position_mm)
    return filtered_mm


def test_a_started_axis_is_at_the_measurement_and_at_rest():
    axis = AxisKalman()
    axis.start(12.5)
    assert (axis.position_mm, axis.velocity_mm_s) == (12.5, 0.0)


def test_two_frames_give_the_numbers_of_the_worked_example(monkeypatch):
    # worked by hand with the matrix form of the filter: measurement variance 1, start variances (1, 300^2),
    # dt = 1 s and process noise 3, so that Q = [[1, 1.5], [1.5, 3]]
    monkeypatch.setattr(axis_kalman, "MEASUREMENT_NOISE_STD_MM", 1.0)
    monkeypatch.setattr(axis_kalman, "INITIAL_VELOCITY_STD_MM_S", 300.0)
    axis = AxisKalman()
    axis.start(0.0)
    axis.predict(1.0, 3.0)
    axis.correct(10.0)
    assert (axis.position_mm, axis.velocity_mm_s) == pytest.approx((9.999888893, 9.999833339), abs=1e-8)
    axis.predict(1.0, 3.0)
    axis.correct(22.0)
    assert (axis.position_mm, axis.velocity_mm_s) == pytest.approx((21.749963109, 11.375025824), abs=1e-8)


def test_a_restarted_axis_behaves_like_a_new_one():
    used_axis, new_axis = AxisKalman(), AxisKalman()
    track(used_axis, [2.0 * frame for frame in range(40)])
    assert track(used_axis, [5.0, 6.0, 8.0]) == track(new_axis, [5.0, 6.0, 8.0])
    assert used_axis.velocity_mm_s == new_axis.velocity_mm_s


def test_the_velocity_of_a_steady_motion_is_found():
    axis = AxisKalman()
    track(axis, [2.0 * frame for frame in range(40)])  # 2 mm per frame = 64 mm/s
    assert axis.velocity_mm_s == pytest.approx(64.0, rel=0.01)
    assert axis.position_mm == pytest.approx(78.0, abs=0.05)


@pytest.mark.parametrize("frame_s", [1 / 32, 1 / 64])
def test_the_velocity_of_a_moving_ball_is_found_within_three_frames(frame_s):
    axis = AxisKalman()
    track(axis, [200.0 * frame * frame_s for frame in range(3)], frame_s)  # C-R5: tracking back within 3 frames
    assert axis.velocity_mm_s == pytest.approx(200.0, rel=0.1)


def test_a_long_rest_does_not_stop_the_filter_from_following_a_move():
    axis = AxisKalman()
    track(axis, [0.0] * 300 + [10.0] * 10)
    assert axis.position_mm == pytest.approx(10.0, abs=1.0)


def test_noisy_measurements_of_a_resting_ball_are_smoothed():
    noise = random.Random(1)
    measured_mm = [noise.gauss(0.0, MEASUREMENT_NOISE_STD_MM) for _ in range(500)]
    filtered_mm = track(AxisKalman(), measured_mm)
    assert statistics.pstdev(filtered_mm) < 0.9 * statistics.pstdev(measured_mm)


def test_after_a_longer_gap_a_measurement_is_trusted_more():
    def position_after_gap_mm(gap_frames):
        axis = AxisKalman()
        track(axis, [0.0] * 20)
        axis.predict(gap_frames * FRAME_S, PROCESS_NOISE_MM2_PER_S3)
        axis.correct(5.0)
        return axis.position_mm

    assert position_after_gap_mm(1) < position_after_gap_mm(6) < 5.0


def test_a_dropped_frame_does_not_disturb_a_steady_motion():
    axis = AxisKalman()
    track(axis, [2.0 * frame for frame in range(20)])
    axis.predict(2 * FRAME_S, PROCESS_NOISE_MM2_PER_S3)  # frame 20 is missing
    axis.correct(2.0 * 21)
    assert axis.velocity_mm_s == pytest.approx(64.0, rel=0.01)
    assert axis.position_mm == pytest.approx(42.0, abs=0.05)
