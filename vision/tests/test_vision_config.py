import json
from pathlib import Path

import pytest

from vision.config_file import ConfigError
from vision.vision_config import DEFAULT_CONFIG_PATH, MARKER_COUNT, load_vision_config


def write_modified_config(tmp_path: Path, change) -> Path:
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "vision_config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_default_config_loads():
    config = load_vision_config()
    assert len(config.markers) == MARKER_COUNT
    assert {marker.marker_id for marker in config.markers} == {0, 1, 2, 3}
    assert config.plate_width_mm > 0 and config.frame_width_px > 0


def test_markers_lie_inside_the_plate():
    config = load_vision_config()
    for marker in config.markers:
        assert abs(marker.centre_x_mm) < config.plate_width_mm / 2
        assert abs(marker.centre_y_mm) < config.plate_height_mm / 2


def test_missing_field_is_an_error(tmp_path):
    path = write_modified_config(tmp_path, lambda data: data.pop("camera_index"))
    with pytest.raises(ConfigError, match="camera_index"):
        load_vision_config(path)


def test_unknown_field_is_an_error(tmp_path):
    path = write_modified_config(tmp_path, lambda data: data.update(camera_idx=1))
    with pytest.raises(ConfigError, match="camera_idx"):
        load_vision_config(path)


def test_duplicate_marker_ids_are_an_error(tmp_path):
    path = write_modified_config(tmp_path, lambda data: data["markers"][1].update(id=0))
    with pytest.raises(ConfigError, match="unique"):
        load_vision_config(path)


def test_wrong_number_is_an_error(tmp_path):
    path = write_modified_config(tmp_path, lambda data: data.update(plate_width_mm=-1))
    with pytest.raises(ConfigError, match="plate_width_mm"):
        load_vision_config(path)


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_vision_config(tmp_path / "nothing.json")
