import numpy as np
import pytest

from ai.common.observation_builder import ROUTE_POINT_COUNT, TARGET_POINTS_KEY, ObservationBuilder
from ai.common.observation_scales import ObservationScales

SCALES = ObservationScales(velocity_mm_s=100.0, tilt_deg=10.0, target_offset_mm=50.0)
BALL = {"x_mm": 20.0, "y_mm": -10.0, "vx_mm_s": 50.0, "vy_mm_s": -25.0}
TILT = {"tilt_x_deg": 2.0, "tilt_y_deg": -4.0}
PREVIOUS_ACTION = (5.0, -1.0)
TARGETS = [[30.0, -10.0], [30.0, 40.0], [80.0, 40.0]]


def build(**changes):
    inputs = {"ball": BALL, "tilt": TILT, "previous_action": PREVIOUS_ACTION, "targets": TARGETS, **changes}
    return ObservationBuilder(SCALES).build(**inputs)


def test_values_are_divided_by_their_scales():
    observation = build()
    # Expected values written out by hand from SCALES.
    assert observation["vx_mm_s"][0] == pytest.approx(0.5)
    assert observation["vy_mm_s"][0] == pytest.approx(-0.25)
    assert observation["tilt_x_deg"][0] == pytest.approx(0.2)
    assert observation["tilt_y_deg"][0] == pytest.approx(-0.4)
    assert observation["target_tilt_x_deg"][0] == pytest.approx(0.5)
    assert observation["target_tilt_y_deg"][0] == pytest.approx(-0.1)


def test_route_points_are_relative_to_the_ball():
    expected = [[0.2, 0.0], [0.2, 1.0], [1.2, 1.0]]  # (point - ball) / 50 mm
    assert build()[TARGET_POINTS_KEY] == pytest.approx(np.array(expected))


def test_same_relative_route_gives_the_same_observation_anywhere_on_the_maze():
    shifted_ball = {**BALL, "x_mm": BALL["x_mm"] + 100.0}
    shifted_targets = [[x_mm + 100.0, y_mm] for x_mm, y_mm in TARGETS]
    assert build(ball=shifted_ball, targets=shifted_targets)[TARGET_POINTS_KEY] == pytest.approx(
        build()[TARGET_POINTS_KEY])


@pytest.mark.parametrize("point_count", [1, 2])
def test_a_short_route_repeats_its_last_point(point_count):
    points = build(targets=TARGETS[:point_count])[TARGET_POINTS_KEY]
    assert len(points) == ROUTE_POINT_COUNT
    for padded in points[point_count:]:
        assert padded == pytest.approx(points[point_count - 1])


def test_output_fits_the_observation_space():
    assert ObservationBuilder.observation_space().contains(build())


def test_default_scales_are_used_without_a_model():
    assert ObservationBuilder().scales == ObservationScales()


@pytest.mark.parametrize("changes", [
    {"targets": []},
    {"targets": [[1.0, float("nan")]]},
    {"targets": [[1.0]]},
    {"ball": {**BALL, "vx_mm_s": float("inf")}},
    {"ball": {**BALL, "x_mm": None}},
    {"tilt": {**TILT, "tilt_x_deg": True}},
    {"previous_action": (1.0,)},
])
def test_invalid_inputs_are_refused(changes):
    with pytest.raises(ValueError):
        build(**changes)


def test_missing_field_is_refused():
    with pytest.raises(KeyError):
        build(tilt={"tilt_x_deg": 1.0})


@pytest.mark.parametrize("bad_scales", [{"velocity_mm_s": 0.0}, {"tilt_deg": -1.0}, {"target_offset_mm": float("nan")}])
def test_scales_must_be_positive_numbers(bad_scales):
    with pytest.raises(ValueError):
        ObservationScales(**bad_scales)


def test_scales_round_trip_through_a_dict():
    assert ObservationScales.from_dict(SCALES.to_dict()) == SCALES
    with pytest.raises(ValueError):
        ObservationScales.from_dict({"velocity_mm_s": 1.0})
