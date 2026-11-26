import numpy as np
import pytest

from ai.common.action_scaling import ACTION_SPACE, FULL_TILT_SCALE_PCT, to_target_tilt_deg


@pytest.mark.parametrize("action, max_tilt_deg, tilt_scale_pct, expected", [
    ((1.0, -1.0), 10.0, 100.0, (10.0, -10.0)),
    ((0.5, 0.25), 12.0, 50.0, (3.0, 1.5)),
    ((0.0, 0.0), 10.0, 100.0, (0.0, 0.0)),
])
def test_action_is_scaled_to_degrees(action, max_tilt_deg, tilt_scale_pct, expected):
    assert to_target_tilt_deg(action, max_tilt_deg, tilt_scale_pct) == pytest.approx(expected)


def test_numpy_action_gives_plain_floats():
    tilt_deg = to_target_tilt_deg(np.array([0.5, -0.5], dtype=np.float32), 10.0, FULL_TILT_SCALE_PCT)
    assert tilt_deg == pytest.approx((5.0, -5.0))
    assert all(type(value) is float for value in tilt_deg)


def test_action_space_is_two_values_between_minus_one_and_one():
    assert ACTION_SPACE.shape == (2,)
    assert np.all(ACTION_SPACE.low == -1.0) and np.all(ACTION_SPACE.high == 1.0)
