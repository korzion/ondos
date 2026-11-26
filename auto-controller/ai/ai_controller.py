"""AIController (D.5): loads a trained model and computes the normalized action for an observation.

At runtime: act() → ai.common.action_scaling.to_target_tilt_deg() → OutputShaper.shape().
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO

from ai.common.action_scaling import ACTION_SPACE
from ai.common.observation_builder import ObservationBuilder
from ai.model_metadata import ModelLoadError, ModelMetadata, load_model_metadata
from ai.model_versions import (DEFAULT_MODELS_DIR, is_model_version, metadata_file, model_file,
                               newest_model_version)

MODEL_DEVICE = "cpu"  # a small MLP: the CPU answers well within the 5 ms of D-R3, and no GPU is needed


class NoModelError(RuntimeError):
    """act() was called before a model was loaded (ai/status = no_model)."""


class InvalidActionError(ValueError):
    """The model returned a non-finite action; it must never be published (D.8)."""


class AIController:
    """Loads a model from ai/models/ and turns an observation into a normalized action (−1…1 per axis)."""

    def __init__(self, models_dir: Path = DEFAULT_MODELS_DIR) -> None:
        self._models_dir = Path(models_dir)
        self._model: PPO | None = None
        self._metadata: ModelMetadata | None = None
        self._observation_builder: ObservationBuilder | None = None

    @property
    def model_version(self) -> str | None:
        """The loaded model (ai/target_tilt and ai/status model_version); None before load()."""
        return self._metadata.model_version if self._metadata else None

    @property
    def policy(self) -> str | None:
        """rl or imitation (ai/status policy); None before load()."""
        return self._metadata.policy if self._metadata else None

    @property
    def observation_builder(self) -> ObservationBuilder:
        """An ObservationBuilder with the loaded model's scales, so the model sees the numbers it was trained on."""
        if self._observation_builder is None:
            raise NoModelError("no model loaded")
        return self._observation_builder

    def load(self, model_version: str | None = None) -> None:
        """Load model_version, or the newest model when it is None (D.5 "On start").

        Raises ModelLoadError when the model cannot be used; a model loaded before stays in use."""
        version = model_version or newest_model_version(self._models_dir)
        if version is None:
            raise ModelLoadError(f"no model in {self._models_dir}")
        if not is_model_version(version):
            raise ModelLoadError(f"{version!r} is not a model_version (<method>-<YYYYMMDD>-<n>)")
        metadata = load_model_metadata(metadata_file(self._models_dir, version), version)
        model = _load_policy_file(model_file(self._models_dir, version))
        _check_spaces(model, version)
        self._model, self._metadata = model, metadata
        self._observation_builder = ObservationBuilder(metadata.observation_scales)

    def act(self, observation: dict[str, np.ndarray]) -> tuple[float, float]:
        """Normalized action (x, y), each in −1…1, for an observation from observation_builder.

        Raises NoModelError before load() and InvalidActionError for a non-finite action."""
        if self._model is None:
            raise NoModelError("no model loaded")
        action, _ = self._model.predict(observation, deterministic=True)
        action_x, action_y = (float(value) for value in np.asarray(action).reshape(-1))
        if not (math.isfinite(action_x) and math.isfinite(action_y)):
            raise InvalidActionError(f"model {self.model_version} returned a non-finite action {action}")
        return action_x, action_y


def _load_policy_file(path: Path) -> PPO:
    if not path.is_file():
        raise ModelLoadError(f"{path}: model file not found")
    try:
        return PPO.load(path, device=MODEL_DEVICE)
    except Exception as error:
        # The file comes from disk and SB3 raises many kinds of errors for a broken one (e.g. AssertionError
        # for a truncated zip); every one must become ai/status = no_model, never a crash of the App (D.8).
        raise ModelLoadError(f"{path}: cannot be loaded ({type(error).__name__}: {error})") from None


def _check_spaces(model: PPO, model_version: str) -> None:
    """A model trained on another observation or action space would get wrong inputs or give actions outside
    −1…1 silently, so it is refused."""
    if model.observation_space != ObservationBuilder.observation_space():
        raise ModelLoadError(f"{model_version} was trained on another observation than ObservationBuilder builds")
    if model.action_space != ACTION_SPACE:
        raise ModelLoadError(f"{model_version} was trained on another action space than {ACTION_SPACE}")
