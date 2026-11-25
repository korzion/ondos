"""Small untrained models for the tests, saved in the ai/models/ format."""
from __future__ import annotations

import json
from pathlib import Path

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from stable_baselines3 import PPO

from ai.common.observation_builder import ObservationBuilder
from ai.common.observation_scales import ObservationScales
from ai.model_metadata import ModelMetadata
from ai.model_versions import metadata_file, model_file, policy_of

ACTION_SPACE = spaces.Box(-1.0, 1.0, (2,), np.float32)


class StubEnv(gym.Env):
    """Only the spaces matter: PPO needs an environment to build its network."""

    def __init__(self, observation_space: spaces.Space) -> None:
        self.observation_space = observation_space
        self.action_space = ACTION_SPACE

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        return self.observation_space.sample(), {}

    def step(self, action):
        return self.observation_space.sample(), 0.0, False, False, {}


def save_model(models_dir: Path, model_version: str, scales: ObservationScales | None = None,
               observation_space: spaces.Space | None = None) -> None:
    """An untrained PPO model with its JSON, as the trainers will save them."""
    models_dir.mkdir(parents=True, exist_ok=True)
    space = observation_space or ObservationBuilder.observation_space()
    PPO("MultiInputPolicy", StubEnv(space), device="cpu", seed=0).save(model_file(models_dir, model_version))
    metadata = ModelMetadata(model_version, policy_of(model_version), scales or ObservationScales())
    metadata_file(models_dir, model_version).write_text(json.dumps(metadata.to_dict()), encoding="utf-8")
