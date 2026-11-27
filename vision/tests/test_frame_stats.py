import pytest

from vision.frame_stats import FrameStats, frame_age_ms

START_S = 1_000.0
FRAME_RATE_HZ = 30.0
FRAME_AGE_MS = 12.0


def record_frames(stats: FrameStats, duration_s: float) -> float:
    """Record frames at FRAME_RATE_HZ with FRAME_AGE_MS each; return the arrival time of the last one."""
    period_s = 1.0 / FRAME_RATE_HZ
    t_s = START_S
    for index in range(round(duration_s * FRAME_RATE_HZ)):
        t_s = START_S + index * period_s
        stats.record_frame(t_s, t_s + FRAME_AGE_MS / 1000.0)
    return t_s


def test_rate_and_age_over_the_last_second():
    stats = FrameStats()
    last_s = record_frames(stats, duration_s=3.0)
    assert stats.fps_hz(last_s) == pytest.approx(FRAME_RATE_HZ, abs=1)
    assert stats.mean_frame_age_ms(last_s) == pytest.approx(FRAME_AGE_MS)


def test_no_frames_gives_zero():
    stats = FrameStats()
    last_s = record_frames(stats, duration_s=1.0)
    assert stats.fps_hz(last_s + 2.0) == 0.0
    assert stats.mean_frame_age_ms(last_s + 2.0) == 0.0


def test_frame_age_is_the_time_since_the_frame_arrived():
    assert frame_age_ms(START_S, START_S + 0.025) == pytest.approx(25.0)


def test_frame_age_is_never_negative():
    assert frame_age_ms(START_S, START_S - 0.5) == 0.0
