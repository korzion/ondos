# auto-controller/ai

Everything in module D that is only about the AI (D.5):

- `common/` – ObservationBuilder: one implementation used in training and in the AI Controller
- `models/` – model files named by model_version `<method>-<YYYYMMDD>-<n>` (e.g. ppo-20261201-2), each with a small JSON beside it
- `requirements.txt` – pinned package versions for Learning and the AI Controller
- AIController, TrainEnv (IF-08), RecordingReader, BCTrainer, PPOTrainer, Evaluator

The runtime parts shared by AI and PID (AutoControllerApp, PIDController, OutputShaper) live outside this folder.

## Setup and tests

`auto-controller/` is on `sys.path` (it holds `run_test.py`), so this folder is imported as the package `ai` (`from ai.ai_controller import AIController`).

```
pip install -e ".[dev]"                                                       # repository root: shared library
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu    # CPU build is enough (Linux default wheel has CUDA)
pip install -r auto-controller/ai/requirements.txt
python -m pytest auto-controller/ai/tests                                     # unit tests of the AI part
```

## Observation (`common/`, used in training and at runtime)

`ObservationBuilder(scales).build(ball, tilt, previous_action, targets)` returns a dict of float32 arrays. The keys are the bus field names (IF-08) and every value is divided by its scale:

| Key | Shape | From | Divided by |
| --- | --- | --- | --- |
| `vx_mm_s`, `vy_mm_s` | (1,) | vision/ball | `velocity_mm_s` |
| `tilt_x_deg`, `tilt_y_deg` | (1,) | platform/state (measured tilt) | `tilt_deg` |
| `target_tilt_x_deg`, `target_tilt_y_deg` | (1,) | the previous command, in degrees (0, 0 after a reset) | `tilt_deg` |
| `target_points_mm` | (3, 2) | plan/route points **minus the ball position**; a shorter route repeats its last point | `target_offset_mm` |

`ObservationBuilder.observation_space()` is the matching `gymnasium.spaces.Dict`; TrainEnv and the trainers use it so a model fits the AI Controller. The action space is `Box(-1, 1, (2,))`: `AIController.act()` returns this normalized action, and `AIController.to_target_tilt_deg(action, max_tilt_deg, tilt_scale_pct)` turns it into degrees (OutputShaper applies the final bounds).

## Model files (`models/`)

| File | Content |
| --- | --- |
| `<model_version>.zip` | Stable-Baselines3 PPO file (`MultiInputPolicy`, the spaces above). A BC model is saved the same way, since PPO starts from its weights (D.5) |
| `<model_version>.json` | `{"model_version", "policy", "observation_scales", "training", "evaluation"}` (`ModelMetadata.to_dict()`); the first three are required |

`model_version` is `<method>-<YYYYMMDD>-<n>` with method `ppo` (policy `rl`) or `bc` (policy `imitation`). Without a set model_version the newest model (date, then n) is loaded. A model trained on another observation space is refused.
