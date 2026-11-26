import math

import pytest

from pid_controller import PIDController

SETTINGS = {
    "pid_kp_deg_per_mm": 0.1,
    "pid_ki_deg_per_mm_per_s": 0.05,
    "pid_kd_deg_per_mm_s": 0.02,
    "pid_integral_limit_deg": 2.0,
}
MAX_TILT_DEG = 5.0
TARGET_MM = (10.0, -10.0)
STEP_S = 0.05


def ball_at_rest(**fields: float) -> dict[str, float]:
    return {"x_mm": 0.0, "y_mm": 0.0, "vx_mm_s": 0.0, "vy_mm_s": 0.0, **fields}


@pytest.mark.parametrize("field", ["x_mm", "y_mm", "vx_mm_s", "vy_mm_s"])
@pytest.mark.parametrize("bad_value", [math.nan, math.inf])
def test_non_finite_ball_is_refused(field, bad_value):
    with pytest.raises(ValueError, match=field):
        PIDController(SETTINGS, MAX_TILT_DEG).compute(ball_at_rest(**{field: bad_value}), TARGET_MM, STEP_S)


def test_non_finite_target_is_refused():
    with pytest.raises(ValueError, match="target_x_mm"):
        PIDController(SETTINGS, MAX_TILT_DEG).compute(ball_at_rest(), (math.nan, 0.0), STEP_S)


def test_non_finite_dt_is_refused():
    with pytest.raises(ValueError, match="dt_s"):
        PIDController(SETTINGS, MAX_TILT_DEG).compute(ball_at_rest(), TARGET_MM, math.nan)


def test_refused_input_does_not_touch_the_integral():
    controller = PIDController(SETTINGS, MAX_TILT_DEG)
    assert controller.compute(ball_at_rest(), TARGET_MM, None) == pytest.approx((1.0, -1.0))
    with pytest.raises(ValueError):
        controller.compute(ball_at_rest(x_mm=math.nan), TARGET_MM, STEP_S)
    # one integral step only: 1.0 + 0.05·10·0.05 = 1.025
    assert controller.compute(ball_at_rest(), TARGET_MM, STEP_S) == pytest.approx((1.025, -1.025))
