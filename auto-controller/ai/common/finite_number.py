"""The number check of the AI inputs: plain Python numbers and NumPy numbers alike."""
from __future__ import annotations

import math
import numbers


def is_finite_number(value: object) -> bool:
    """True for a finite int or float, including NumPy numbers (np.float32, np.int64), which a physics
    environment returns; False for bool, None, NaN and infinity."""
    return isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value)
