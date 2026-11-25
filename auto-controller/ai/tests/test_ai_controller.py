import json
import time

import numpy as np
import pytest
from gymnasium import spaces

import ai.ai_controller as ai_controller_module
from ai.ai_controller import AIController, InvalidActionError, NoModelError
from ai.common.observation_scales import ObservationScales
from ai.model_metadata import ModelLoadError
from ai.tests.model_helpers import save_model

BALL = {"x_mm": 0.0, "y_mm": 0.0, "vx_mm_s": 30.0, "vy_mm_s": -10.0}
TILT = {"tilt_x_deg": 1.0, "tilt_y_deg": 0.5}
TARGETS = [[40.0, 0.0], [40.0, 40.0]]
TIMING_SAMPLES = 1000
TIMING_PERCENTILE = 99
DECISION_BUDGET_MS = 5.0  # D-R3; the full measurement is D-T3


@pytest.fixture
def models_dir(tmp_path):
    return tmp_path / "models"


def loaded_controller(models_dir, model_version="ppo-20261201-1", **model_options) -> AIController:
    save_model(models_dir, model_version, **model_options)
    controller = AIController(models_dir)
    controller.load(model_version)
    return controller


def observation_for(controller: AIController) -> dict:
    return controller.observation_builder.build(BALL, TILT, (0.0, 0.0), TARGETS)


def test_load_sets_version_policy_and_scales(models_dir):
    scales = ObservationScales(velocity_mm_s=250.0)
    controller = loaded_controller(models_dir, "bc-20261130-3", scales=scales)
    assert controller.model_version == "bc-20261130-3"
    assert controller.policy == "imitation"
    assert controller.observation_builder.scales == scales


def test_without_a_version_the_newest_model_is_loaded(models_dir):
    save_model(models_dir, "ppo-20261201-1")
    save_model(models_dir, "ppo-20261202-1")
    controller = AIController(models_dir)
    controller.load()
    assert controller.model_version == "ppo-20261202-1"


def test_act_gives_a_deterministic_action_within_limits(models_dir):
    controller = loaded_controller(models_dir)
    observation = observation_for(controller)
    action = controller.act(observation)
    assert len(action) == 2 and all(-1.0 <= value <= 1.0 for value in action)
    assert controller.act(observation) == action


def test_act_before_load_is_refused():
    with pytest.raises(NoModelError):
        AIController().act({})
    with pytest.raises(NoModelError):
        AIController().observation_builder


@pytest.mark.parametrize("model_version", [None, "ppo-20261201-1", "latest"])
def test_missing_model_cannot_be_loaded(models_dir, model_version):
    with pytest.raises(ModelLoadError):
        AIController(models_dir).load(model_version)


def test_model_json_must_match_the_file_name(models_dir):
    save_model(models_dir, "ppo-20261201-1")
    metadata_path = models_dir / "ppo-20261201-1.json"
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata_path.write_text(json.dumps({**data, "model_version": "ppo-20261201-2"}), encoding="utf-8")
    with pytest.raises(ModelLoadError, match="does not match"):
        AIController(models_dir).load("ppo-20261201-1")


def test_broken_model_file_cannot_be_loaded(models_dir):
    save_model(models_dir, "ppo-20261201-1")
    (models_dir / "ppo-20261201-1.zip").write_bytes(b"not a zip")
    with pytest.raises(ModelLoadError):
        AIController(models_dir).load("ppo-20261201-1")


def test_model_trained_on_another_observation_is_refused(models_dir):
    other_space = spaces.Dict({"vx_mm_s": spaces.Box(-np.inf, np.inf, (1,), np.float32)})
    save_model(models_dir, "ppo-20261201-1", observation_space=other_space)
    with pytest.raises(ModelLoadError, match="another observation"):
        AIController(models_dir).load("ppo-20261201-1")


def test_failed_load_keeps_the_model_in_use(models_dir):
    controller = loaded_controller(models_dir)
    with pytest.raises(ModelLoadError):
        controller.load("ppo-20991231-1")
    assert controller.model_version == "ppo-20261201-1"


def test_non_finite_action_is_refused(models_dir, monkeypatch):
    controller = loaded_controller(models_dir)

    class NanModel:
        def predict(self, observation, deterministic):
            return np.array([np.nan, 0.0], dtype=np.float32), None

    monkeypatch.setattr(ai_controller_module.PPO, "load", lambda *args, **kwargs: NanModel())
    monkeypatch.setattr(ai_controller_module, "_check_observation_space", lambda model, version: None)
    controller.load("ppo-20261201-1")
    with pytest.raises(InvalidActionError):
        controller.act(observation_for(controller))


@pytest.mark.parametrize("action, max_tilt_deg, tilt_scale_pct, expected", [
    ((1.0, -1.0), 10.0, 100.0, (10.0, -10.0)),
    ((0.5, 0.25), 12.0, 50.0, (3.0, 1.5)),
    ((0.0, 0.0), 10.0, 100.0, (0.0, 0.0)),
])
def test_action_is_scaled_to_degrees(action, max_tilt_deg, tilt_scale_pct, expected):
    assert AIController.to_target_tilt_deg(action, max_tilt_deg, tilt_scale_pct) == pytest.approx(expected)


def test_decision_time_is_far_below_the_budget(models_dir):
    """Not the D-R3 test (D-T3 measures from message arrival to publish); a guard against a slow policy."""
    controller = loaded_controller(models_dir)
    observation = observation_for(controller)
    durations_ms = []
    for _ in range(TIMING_SAMPLES):
        start_s = time.perf_counter()
        controller.act(observation)
        durations_ms.append((time.perf_counter() - start_s) * 1000.0)
    p99_ms = float(np.percentile(durations_ms, TIMING_PERCENTILE))
    print(f"act() p{TIMING_PERCENTILE} = {p99_ms:.3f} ms")
    assert p99_ms < DECISION_BUDGET_MS
