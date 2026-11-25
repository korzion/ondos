# auto-controller/ai

Everything in module D that is only about the AI (D.5):

- `common/` – ObservationBuilder and the action scaling: one implementation used in training and in the AI Controller
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

`ObservationBuilder(scales).build(ball, tilt, previous_action, targets)` returns a dict of float32 arrays. The inputs may be plain Python or NumPy numbers and arrays. The keys are the bus field names (IF-08) and every value is divided by its scale:

| Key | Shape | From | Divided by |
| --- | --- | --- | --- |
| `vx_mm_s`, `vy_mm_s` | (1,) | vision/ball | `velocity_mm_s` |
| `tilt_x_deg`, `tilt_y_deg` | (1,) | platform/state (measured tilt) | `tilt_deg` |
| `target_tilt_x_deg`, `target_tilt_y_deg` | (1,) | the previous command, in degrees (0, 0 after a reset) | `tilt_deg` |
| `target_points_mm` | (3, 2) | plan/route points **minus the ball position**; a shorter route repeats its last point | `target_offset_mm` |

**`previous_action`:** the previous command in degrees.
- At runtime it is the last **published** target tilt (after `to_target_tilt_deg` and OutputShaper).
- In training it is the action the environment received.
- After a reset it is (0, 0); when to reset is decided by AutoControllerApp (#62).

`ObservationBuilder.observation_space()` is the matching `gymnasium.spaces.Dict`. The trainers use it, so a model fits the AI Controller.

## Action (`common/action_scaling.py`)

The network outputs a normalized action in `ACTION_SPACE = Box(-1, 1, (2,), float32)`; every model is trained with this space. `to_target_tilt_deg(action, max_tilt_deg, tilt_scale_pct)` turns it into `target_tilt_x_deg`, `target_tilt_y_deg`. Training and runtime use this same function:

| Where | Steps |
| --- | --- |
| Runtime | `AIController.act()` → `to_target_tilt_deg(action, max_tilt_deg, tilt_scale_pct)` → `OutputShaper.shape()` (final bounds, smoothing) |
| Training | the model's action → `to_target_tilt_deg(action, max_tilt_deg, FULL_TILT_SCALE_PCT)` → `TrainEnv.step()` |

`TrainEnv.step()` takes the action in **degrees**, ±max_tilt_deg, as IF-08 defines it. The small wrapper between the model and TrainEnv belongs to #65 / #67.

## Model files (`models/`)

| File | Content |
| --- | --- |
| `<model_version>.zip` | Stable-Baselines3 PPO file (`MultiInputPolicy`, the spaces above). A BC model is saved the same way, since PPO starts from its weights (D.5) |
| `<model_version>.json` | `{"model_version", "policy", "observation_scales", "training", "evaluation"}` (`ModelMetadata.to_dict()`); the first three are required |

`model_version` is `<method>-<YYYYMMDD>-<n>` with method `ppo` (policy `rl`) or `bc` (policy `imitation`). `n` counts the models of one day across both methods (`bc-20261201-1`, then `ppo-20261201-2`). Without a set model_version the newest model (latest date, then highest n) is loaded.

A model that cannot be used is refused with `ModelLoadError`, and the AI Controller keeps the model it had. That covers a missing file, a broken file, a wrong JSON, and another observation or action space.

The AI tests are not run by CI (`shared-checks.yml` only covers `shared/`); run them locally.
