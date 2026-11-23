"""Vision configuration file (C.5): plate size, ArUco markers and camera settings.

The hardware numbers live in config/vision_config.json, not in the code, so another plate
or camera only needs a different file.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vision.config_file import ConfigError, check_fields, is_number, read_json_object

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "vision_config.json"
MARKER_COUNT = 4  # one ArUco marker on each corner of every maze plate (C.4)
CONFIG_FIELDS = frozenset({
    "plate_width_mm", "plate_height_mm", "marker_dictionary", "marker_size_mm", "markers",
    "camera_index", "frame_width_px", "frame_height_px", "camera_fps_hz",
})
MARKER_FIELDS = frozenset({"id", "centre_x_mm", "centre_y_mm"})


@dataclass(frozen=True)
class MarkerConfig:
    """One ArUco marker: its ID and the centre of the marker in the board frame (D4)."""

    marker_id: int
    centre_x_mm: float
    centre_y_mm: float


@dataclass(frozen=True)
class VisionConfig:
    """Contents of the Vision configuration file."""

    plate_width_mm: float
    plate_height_mm: float
    marker_dictionary: str
    marker_size_mm: float
    markers: tuple[MarkerConfig, ...]
    camera_index: int
    frame_width_px: int
    frame_height_px: int
    camera_fps_hz: float


def load_vision_config(path: Path = DEFAULT_CONFIG_PATH) -> VisionConfig:
    """Read and check the configuration file; raise ConfigError on a missing or wrong field."""
    data = read_json_object(path)
    check_fields(data, CONFIG_FIELDS, str(path))
    return VisionConfig(
        plate_width_mm=_positive_number(data, "plate_width_mm"),
        plate_height_mm=_positive_number(data, "plate_height_mm"),
        marker_dictionary=_non_empty_string(data, "marker_dictionary"),
        marker_size_mm=_positive_number(data, "marker_size_mm"),
        markers=_markers(data["markers"]),
        camera_index=_non_negative_int(data, "camera_index"),
        frame_width_px=_positive_int(data, "frame_width_px"),
        frame_height_px=_positive_int(data, "frame_height_px"),
        camera_fps_hz=_positive_number(data, "camera_fps_hz"),
    )


def _markers(entries: object) -> tuple[MarkerConfig, ...]:
    if not isinstance(entries, list) or len(entries) != MARKER_COUNT:
        raise ConfigError(f"markers must be a list of {MARKER_COUNT} markers")
    markers = tuple(_marker(entry) for entry in entries)
    marker_ids = [marker.marker_id for marker in markers]
    if len(set(marker_ids)) != MARKER_COUNT:
        raise ConfigError(f"marker IDs must be unique, got {marker_ids}")
    return markers


def _marker(entry: object) -> MarkerConfig:
    if not isinstance(entry, dict):
        raise ConfigError("every marker must be a JSON object")
    check_fields(entry, MARKER_FIELDS, "marker")
    return MarkerConfig(
        marker_id=_non_negative_int(entry, "id"),
        centre_x_mm=_number(entry, "centre_x_mm"),
        centre_y_mm=_number(entry, "centre_y_mm"),
    )


def _number(data: dict, key: str) -> float:
    value = data[key]
    if not is_number(value):
        raise ConfigError(f"{key} must be a number, got {value!r}")
    return float(value)


def _positive_number(data: dict, key: str) -> float:
    value = _number(data, key)
    if value <= 0:
        raise ConfigError(f"{key} must be > 0, got {value!r}")
    return value


def _non_negative_int(data: dict, key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{key} must be an integer >= 0, got {value!r}")
    return value


def _positive_int(data: dict, key: str) -> int:
    value = _non_negative_int(data, key)
    if value == 0:
        raise ConfigError(f"{key} must be > 0, got {value!r}")
    return value


def _non_empty_string(data: dict, key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{key} must be a non-empty string, got {value!r}")
    return value
