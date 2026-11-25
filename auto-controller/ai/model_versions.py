"""Model files in ai/models/ and their model_version names (D.5).

A model is <model_version>.zip (a Stable-Baselines3 PPO file) with <model_version>.json beside it.
model_version is <method>-<YYYYMMDD>-<n>, e.g. ppo-20261201-2; the method gives the policy kind.
"""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT_MODELS_DIR = Path(__file__).resolve().parent / "models"
MODEL_FILE_SUFFIX = ".zip"
METADATA_FILE_SUFFIX = ".json"
MODEL_VERSION_PATTERN = re.compile(r"^(?P<method>ppo|bc)-(?P<date>\d{8})-(?P<number>\d+)$")
# ai/status policy (IF-06) of each training method: PPO = reinforcement learning, BC = behaviour cloning.
POLICY_BY_METHOD = {"ppo": "rl", "bc": "imitation"}


def is_model_version(text: str) -> bool:
    return MODEL_VERSION_PATTERN.match(text) is not None


def policy_of(model_version: str) -> str:
    """ai/status policy of a model: rl for ppo-…, imitation for bc-…"""
    match = MODEL_VERSION_PATTERN.match(model_version)
    if match is None:
        raise ValueError(f"{model_version!r} is not a model_version (<method>-<YYYYMMDD>-<n>)")
    return POLICY_BY_METHOD[match["method"]]


def model_file(models_dir: Path, model_version: str) -> Path:
    return Path(models_dir) / f"{model_version}{MODEL_FILE_SUFFIX}"


def metadata_file(models_dir: Path, model_version: str) -> Path:
    return Path(models_dir) / f"{model_version}{METADATA_FILE_SUFFIX}"


def list_model_versions(models_dir: Path = DEFAULT_MODELS_DIR) -> list[str]:
    """model_version of every complete model (model file and JSON) in models_dir, oldest first."""
    models_dir = Path(models_dir)
    if not models_dir.is_dir():
        return []
    versions = [path.stem for path in models_dir.glob(f"*{MODEL_FILE_SUFFIX}")
                if is_model_version(path.stem) and metadata_file(models_dir, path.stem).is_file()]
    return sorted(versions, key=_age_key)


def newest_model_version(models_dir: Path = DEFAULT_MODELS_DIR) -> str | None:
    """The model loaded on start when no model_version is set (D.5); None if there is no model."""
    versions = list_model_versions(models_dir)
    return versions[-1] if versions else None


def _age_key(model_version: str) -> tuple[str, int, str]:
    match = MODEL_VERSION_PATTERN.match(model_version)
    return match["date"], int(match["number"]), match["method"]
