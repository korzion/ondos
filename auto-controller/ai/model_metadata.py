"""ModelMetadata: the small JSON beside each model file (D.5: observation scales, training data, evaluation results).

    {"model_version": "ppo-20261201-2", "policy": "rl",
     "observation_scales": {"velocity_mm_s": 500.0, "tilt_deg": 15.0, "target_offset_mm": 100.0},
     "training": {...}, "evaluation": {...}}

model_version, policy and observation_scales are required; training and evaluation are free-form
objects written by the trainers and the Evaluator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ai.common.observation_scales import ObservationScales
from ai.model_versions import policy_of

REQUIRED_FIELDS = frozenset({"model_version", "policy", "observation_scales"})
OPTIONAL_FIELDS = frozenset({"training", "evaluation"})


class ModelLoadError(RuntimeError):
    """A model cannot be used: its file or JSON is missing, unreadable, or does not match (ai/status = no_model)."""


@dataclass(frozen=True)
class ModelMetadata:
    """Contents of a model's JSON."""

    model_version: str
    policy: str
    observation_scales: ObservationScales
    training: dict = field(default_factory=dict)
    evaluation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """The JSON object to save beside the model file (used by the trainers)."""
        return {
            "model_version": self.model_version,
            "policy": self.policy,
            "observation_scales": self.observation_scales.to_dict(),
            "training": self.training,
            "evaluation": self.evaluation,
        }


def load_model_metadata(path: Path, model_version: str) -> ModelMetadata:
    """Read and check the JSON of model_version; raise ModelLoadError when it is missing or wrong."""
    data = _read_json_object(Path(path))
    _check_fields(data, path)
    if data["model_version"] != model_version:
        raise ModelLoadError(f"{path}: model_version {data['model_version']!r} does not match the file name")
    if data["policy"] != policy_of(model_version):
        raise ModelLoadError(f"{path}: policy {data['policy']!r} does not match the method of {model_version}")
    try:
        scales = ObservationScales.from_dict(data["observation_scales"])
    except (TypeError, ValueError) as error:
        raise ModelLoadError(f"{path}: {error}") from None
    return ModelMetadata(model_version, data["policy"], scales,
                         data.get("training", {}), data.get("evaluation", {}))


def _read_json_object(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ModelLoadError(f"{path}: model JSON not found") from None
    except json.JSONDecodeError as error:
        raise ModelLoadError(f"{path}: not valid JSON ({error})") from None
    if not isinstance(data, dict):
        raise ModelLoadError(f"{path}: the top level must be a JSON object")
    return data


def _check_fields(data: dict, path: Path) -> None:
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        raise ModelLoadError(f"{path}: missing field(s) {sorted(missing)}")
    unknown = set(data) - REQUIRED_FIELDS - OPTIONAL_FIELDS
    if unknown:
        raise ModelLoadError(f"{path}: unknown field(s) {sorted(unknown)}")
