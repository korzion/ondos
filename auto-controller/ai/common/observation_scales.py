"""ObservationScales: what each observation value is divided by, so the network sees values near ±1.

The scales are saved in the model's JSON (D.5 "observation scales"), so training and the AI
Controller divide by the same numbers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

from ai.common.finite_number import is_finite_number

# STARTING VALUES, to be tuned with the first trained models.
DEFAULT_VELOCITY_SCALE_MM_S = 500.0     # a fast ball on the plate
DEFAULT_TILT_SCALE_DEG = 15.0           # above any max_tilt_deg the platform allows
DEFAULT_TARGET_OFFSET_SCALE_MM = 100.0  # a few cells between the ball and its route points


@dataclass(frozen=True)
class ObservationScales:
    """Divisors of the observation values, by kind of value."""

    velocity_mm_s: float = DEFAULT_VELOCITY_SCALE_MM_S
    tilt_deg: float = DEFAULT_TILT_SCALE_DEG
    target_offset_mm: float = DEFAULT_TARGET_OFFSET_SCALE_MM

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if not is_finite_number(value) or value <= 0:
                raise ValueError(f"observation scale {field.name} must be a number > 0, got {value!r}")

    @classmethod
    def from_dict(cls, data: dict) -> ObservationScales:
        """Read the scales from a model's JSON; every scale must be there."""
        expected = {field.name for field in fields(cls)}
        if set(data) != expected:
            raise ValueError(f"observation scales must be exactly {sorted(expected)}, got {sorted(data)}")
        return cls(**data)

    def to_dict(self) -> dict[str, float]:
        return asdict(self)
