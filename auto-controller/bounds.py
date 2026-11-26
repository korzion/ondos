"""Symmetric bounds shared by PIDController and OutputShaper."""


def clamp_symmetric(value: float, bound: float) -> float:
    """Limit value to the range [-bound, +bound]."""
    return max(-bound, min(bound, value))
