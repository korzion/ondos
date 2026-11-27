"""EpisodeParams: the parameters of one TrainEnv episode, drawn at reset (IF-08, Parameters and
randomisation). The names are the names of the IF-08 table.

Randomising them keeps the AI from fitting one exact simulated platform, so it also works on
the real one (D.10, first risk).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from ai.randomised_parameter import RandomisedParameter
from ai.train_env_config import TrainEnvConfig


@dataclass(frozen=True)
class EpisodeParams:
    """Values that stay fixed during one episode. Offsets are (x, y), one value for each axis."""

    friction_coeff: float
    restitution: float
    latency_ms: float
    noise_std_mm: float
    tilt_offset_deg: tuple[float, float]
    start_offset_mm: tuple[float, float]
    step_dt_s: float

    def to_dict(self) -> dict:
        """The values of this episode, for the reset info (IF-08). They are not saved per episode:
        the same seed draws them again."""
        return asdict(self)


def nominal_episode_params(config: TrainEnvConfig, cell_size_mm: float) -> EpisodeParams:
    """The nominal values, for reset with randomize = false."""
    start_offset_mm = config.start_offset_cells.nominal * cell_size_mm
    return EpisodeParams(
        friction_coeff=config.friction_coeff.nominal,
        restitution=config.restitution.nominal,
        latency_ms=config.latency_ms.nominal,
        noise_std_mm=config.noise_std_mm.nominal,
        tilt_offset_deg=(config.tilt_offset_deg.nominal, config.tilt_offset_deg.nominal),
        start_offset_mm=(start_offset_mm, start_offset_mm),
        step_dt_s=config.step_dt_s.nominal,
    )


def random_episode_params(config: TrainEnvConfig, rng: np.random.Generator, cell_size_mm: float) -> EpisodeParams:
    """Values drawn from the ranges in the config; rng comes from reset(seed), so a seed repeats an episode."""
    return EpisodeParams(
        friction_coeff=_draw(rng, config.friction_coeff),
        restitution=_draw(rng, config.restitution),
        latency_ms=_draw(rng, config.latency_ms),
        noise_std_mm=_draw(rng, config.noise_std_mm),
        tilt_offset_deg=(_draw(rng, config.tilt_offset_deg), _draw(rng, config.tilt_offset_deg)),
        start_offset_mm=(_draw(rng, config.start_offset_cells) * cell_size_mm,
                         _draw(rng, config.start_offset_cells) * cell_size_mm),
        step_dt_s=_draw(rng, config.step_dt_s),
    )


def _draw(rng: np.random.Generator, parameter: RandomisedParameter) -> float:
    """A uniform value between random_min and random_max."""
    return float(rng.uniform(parameter.random_min, parameter.random_max))
