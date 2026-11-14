# auto-controller/ai

Everything in module D that is only about the AI (D.5):

- `common/` – ObservationBuilder: one implementation used in training and in the AI Controller
- `models/` – model files named by model_version `<method>-<YYYYMMDD>-<n>` (e.g. ppo-20261201-2), each with a small JSON beside it
- `requirements.txt` – pinned package versions for Learning and the AI Controller
- AIController, TrainEnv (IF-08), RecordingReader, BCTrainer, PPOTrainer, Evaluator

The runtime parts shared by AI and PID (AutoControllerApp, PIDController, OutputShaper) live outside this folder.
