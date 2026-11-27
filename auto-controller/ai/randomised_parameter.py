"""RandomisedParameter: a parameter of the IF-08 table that is drawn at reset (Parameters and randomisation)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RandomisedParameter:
    """Nominal value and the range a value is drawn from at reset."""

    nominal: float
    random_min: float
    random_max: float
