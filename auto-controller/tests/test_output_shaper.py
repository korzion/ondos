import math

import pytest

from output_shaper import OutputShaper

MAX_TILT_DEG = 5.0
BOUNDS_ONLY = {"max_tilt_deg": MAX_TILT_DEG}


def smoothing(pct: float) -> dict[str, float]:
    return {**BOUNDS_ONLY, "action_smoothing_pct": pct}


def shape_twice(first: tuple[float, float], second: tuple[float, float], limits: dict) -> tuple[float, float]:
    shaper = OutputShaper()
    shaper.shape(first, limits)
    return shaper.shape(second, limits)


def test_action_is_bounded_to_max_tilt():
    assert OutputShaper().shape((7.0, -9.0), BOUNDS_ONLY) == pytest.approx((5.0, -5.0))


def test_action_within_bounds_passes_unchanged():
    assert OutputShaper().shape((1.5, -2.5), BOUNDS_ONLY) == pytest.approx((1.5, -2.5))


def test_without_smoothing_pct_the_action_is_not_smoothed():
    assert shape_twice((1.0, 0.0), (3.0, 0.0), BOUNDS_ONLY) == pytest.approx((3.0, 0.0))


def test_first_action_is_not_smoothed():
    assert OutputShaper().shape((3.0, -1.0), smoothing(50.0)) == pytest.approx((3.0, -1.0))


def test_smoothing_mixes_previous_output_and_action():
    # 1·0.5 + 3·0.5 = 2
    assert shape_twice((1.0, 0.0), (3.0, 0.0), smoothing(50.0)) == pytest.approx((2.0, 0.0))


def test_smoothed_value_is_bounded():
    # 5·0.5 + 9·0.5 = 7, bounded to 5
    assert shape_twice((5.0, 0.0), (9.0, 0.0), smoothing(50.0)) == pytest.approx((5.0, 0.0))


@pytest.mark.parametrize("pct, expected", [
    (150.0, (1.0, 0.0)),   # limited to 100: keeps the previous output
    (-50.0, (3.0, 0.0)),   # limited to 0: no smoothing
])
def test_smoothing_pct_is_limited_to_0_100(pct, expected):
    assert shape_twice((1.0, 0.0), (3.0, 0.0), smoothing(pct)) == pytest.approx(expected)


def test_reset_forgets_the_previous_output():
    shaper = OutputShaper()
    shaper.shape((1.0, 0.0), smoothing(50.0))
    shaper.reset()
    assert shaper.shape((3.0, 0.0), smoothing(50.0)) == pytest.approx((3.0, 0.0))


@pytest.mark.parametrize("action", [(math.nan, 0.0), (0.0, math.inf)])
def test_non_finite_action_is_refused(action):
    with pytest.raises(ValueError):
        OutputShaper().shape(action, BOUNDS_ONLY)


@pytest.mark.parametrize("max_tilt_deg", [-5.0, math.nan])
def test_invalid_max_tilt_is_refused(max_tilt_deg):
    with pytest.raises(ValueError):
        OutputShaper().shape((1.0, 0.0), {"max_tilt_deg": max_tilt_deg})


def test_refused_action_keeps_the_previous_output():
    shaper = OutputShaper()
    shaper.shape((1.0, 0.0), smoothing(50.0))
    with pytest.raises(ValueError):
        shaper.shape((math.nan, 0.0), smoothing(50.0))
    assert shaper.shape((3.0, 0.0), smoothing(50.0)) == pytest.approx((2.0, 0.0))
