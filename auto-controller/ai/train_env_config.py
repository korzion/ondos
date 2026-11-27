"""TrainEnvConfig: Learning's own configuration of TrainEnv (IF-08, Parameters and randomisation).

The numbers live in config/train_env.json, not in the code, so a measured value only changes
the file. The whole configuration is saved with each model (IF-08), see to_dict().
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ai.randomised_parameter import RandomisedParameter

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "train_env.json"
COMMENT_KEY = "$comment"  # a JSON file has no comments; this key holds the explanation and is skipped
VALUE_KEY = "value"
NOMINAL_KEY = "nominal"
RANDOM_MIN_KEY = "random_min"
RANDOM_MAX_KEY = "random_max"


@dataclass(frozen=True)
class TrainEnvConfig:
    """Contents of config/train_env.json, with the names of the IF-08 table."""

    max_tilt_deg: float
    max_tilt_speed_deg_s: float

    plate_width_mm: float
    plate_height_mm: float
    ball_mass_g: float

    friction_coeff: RandomisedParameter
    restitution: RandomisedParameter
    latency_ms: RandomisedParameter
    noise_std_mm: RandomisedParameter
    tilt_offset_deg: RandomisedParameter
    step_dt_s: RandomisedParameter
    start_offset_cells: RandomisedParameter  # start_offset_mm in cell sizes: IF-08 gives ±cell_size/4

    filter_noise: float
    lost_timeout_ms: float
    occlusion_rate_per_s: float
    occlusion_wall_gap_mm: float
    occlusion_min_ms: float
    occlusion_max_ms: float
    frame_drop_chance: float

    time_limit_s: float
    exit_hold_frames: int
    wall_hit_min_speed_mm_s: float

    progress_reward_per_mm: float
    time_penalty_per_s: float
    wall_hit_penalty: float
    tilt_change_penalty_per_deg2: float

    def to_dict(self) -> dict:
        """All values, to be saved in the model's JSON beside the model file (D.5)."""
        return asdict(self)


def load_train_env_config(path: Path = DEFAULT_CONFIG_PATH) -> TrainEnvConfig:
    """Read the configuration file; raise ValueError on a missing or unknown field."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop(COMMENT_KEY, None)
    _check_fields(data, path)
    return TrainEnvConfig(**{name: _read_entry(entry) for name, entry in data.items()})


def _read_entry(entry: dict) -> float | RandomisedParameter:
    """A plain value, or a randomised parameter when the entry has a nominal value."""
    if NOMINAL_KEY not in entry:
        return entry[VALUE_KEY]
    return RandomisedParameter(entry[NOMINAL_KEY], entry[RANDOM_MIN_KEY], entry[RANDOM_MAX_KEY])


def _check_fields(data: dict, path: Path) -> None:
    """A typo in a field name must not be ignored silently."""
    expected = {field.name for field in fields(TrainEnvConfig)}
    missing = expected - set(data)
    if missing:
        raise ValueError(f"{path}: missing field(s) {sorted(missing)}")
    unknown = set(data) - expected
    if unknown:
        raise ValueError(f"{path}: unknown field(s) {sorted(unknown)}")
