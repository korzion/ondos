# D · Auto Controller

Team: `@korzion/auto-controller` · Design: *Ondos Module Design*, Part II-D

> **Folder name:** The design document (D.4, D.5) says `ai/`; the repo uses `auto-controller/` with AI-only parts in `auto-controller/ai/`, so `ai/common/`, `ai/models/` and `ai/requirements.txt` stay valid inside the module folder.

| | |
| --- | --- |
| Members | İbrahim, Süleyman, Talha, Enis Talha, Yağmur |
| Runs on | Runtime on the station laptop; Learning offline |
| Languages | Python 3.11 |
| Interfaces | Owns IF-06 and IF-08. Uses IF-04, IF-02, IF-05, IF-07, IF-09. |

## Parts (from the design document)

- Runtime (AI and PID): AutoControllerApp, PIDController, OutputShaper — outside `ai/`
- `ai/`: everything that is only about the AI — AIController, ObservationBuilder (`ai/common/`), TrainEnv, RecordingReader, BCTrainer, PPOTrainer, Evaluator, models (`ai/models/`), `ai/requirements.txt`

Uses `shared/mazes/` (same route function as Vision) and recordings from `shared/samples/`.

The internal folder layout of this module is decided by the module team.

## Tests and Dec 4 demo

Every test has its inputs in `fixtures/<TEST-ID>/` (input files + a README saying what can be edited) and runs with

```
python run_test.py <TEST-ID>
```

which prints PASS or FAIL for every check. The test computes the expected result itself and never needs another module.

| Test | Requirement | Fixtures |
| --- | --- | --- |
| D-T1 AI in training environment | D-R1 | [fixtures/D-T1](fixtures/D-T1/) |
| D-T2 AI vs PID | D-R2 | [fixtures/D-T2](fixtures/D-T2/) |
| D-T3 Decision time | D-R3 | [fixtures/D-T3](fixtures/D-T3/) |
| D-T4 Only valid commands | D-R4 | [fixtures/D-T4](fixtures/D-T4/) |
| D-T5 PID output | D-R5 | [fixtures/D-T5](fixtures/D-T5/) |
| D-T6 Training rows | D-R6 | [fixtures/D-T6](fixtures/D-T6/) |
| D-T7 Signs | D-R7 | [fixtures/D-T7](fixtures/D-T7/) |
