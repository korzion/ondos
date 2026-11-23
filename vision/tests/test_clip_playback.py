"""Record mode and clip playback with generated frames (no camera needed)."""
import numpy as np
import pytest

from vision.clip_writer import ClipWriter
from vision.frame_grabber import FrameGrabber

WIDTH_PX, HEIGHT_PX, FPS_HZ = 64, 48, 30.0
FRAME_COUNT = 6
RECORDED_START_S = 1_700_000_000.0
RECORDED_GAPS_S = [0.010, 0.020, 0.010, 0.030, 0.010]  # uneven on purpose: playback must keep each gap


def make_frame(index: int) -> np.ndarray:
    return np.full((HEIGHT_PX, WIDTH_PX, 3), index * 30, dtype=np.uint8)


def recorded_times_s() -> list[float]:
    times_s = [RECORDED_START_S]
    for gap_s in RECORDED_GAPS_S:
        times_s.append(times_s[-1] + gap_s)
    return times_s


def write_clip(clip_dir) -> None:
    writer = ClipWriter(clip_dir, FPS_HZ)
    for index, t_s in enumerate(recorded_times_s()):
        writer.write(make_frame(index), t_s)
    writer.close()


def read_all(grabber: FrameGrabber) -> list[tuple[np.ndarray, float]]:
    samples = []
    while (sample := grabber.read()) is not None:
        samples.append(sample)
    return samples


def test_clip_plays_back_every_frame_with_the_recorded_gaps(tmp_path):
    write_clip(tmp_path / "clip")
    grabber = FrameGrabber(WIDTH_PX, HEIGHT_PX, FPS_HZ)
    assert grabber.open_clip(tmp_path / "clip")
    samples = read_all(grabber)
    assert grabber.is_clip_finished()
    assert len(samples) == FRAME_COUNT
    assert all(frame.shape == (HEIGHT_PX, WIDTH_PX, 3) for frame, _ in samples)
    played_gaps_s = [later - earlier for (_, earlier), (_, later) in zip(samples, samples[1:])]
    assert played_gaps_s == pytest.approx(RECORDED_GAPS_S, abs=1e-5)
    grabber.close()


def test_recording_a_played_clip_gives_the_same_frame_count(tmp_path):
    write_clip(tmp_path / "clip")
    grabber = FrameGrabber(WIDTH_PX, HEIGHT_PX, FPS_HZ)
    grabber.open_clip(tmp_path / "clip")
    grabber.start_recording(tmp_path / "copy")
    read_all(grabber)
    grabber.close()

    replay = FrameGrabber(WIDTH_PX, HEIGHT_PX, FPS_HZ)
    assert replay.open_clip(tmp_path / "copy")
    assert len(read_all(replay)) == FRAME_COUNT
    replay.close()


def test_recording_never_overwrites_a_clip(tmp_path):
    write_clip(tmp_path / "clip")
    with pytest.raises(FileExistsError):
        ClipWriter(tmp_path / "clip", FPS_HZ)


def test_missing_clip_cannot_be_opened(tmp_path):
    assert not FrameGrabber(WIDTH_PX, HEIGHT_PX, FPS_HZ).open_clip(tmp_path / "nothing")
