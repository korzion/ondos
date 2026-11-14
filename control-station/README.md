# E · Control Station

Team: `@korzion/control-station` · Design: *Ondos Module Design*, Part II-E

| | |
| --- | --- |
| Members | Mohammed, Arif, Beyzanur, Süleyman, Yağmur |
| Runs on | Station laptop: desktop app plus background services (Windows and Linux) |
| Languages | TypeScript: Electron app, 3D Twin (Three.js), GameManager and Recorder (Node.js background processes) |
| Interfaces | Owns IF-05, IF-07 and IF-09. |

## Parts (from the design document)

- App: BusClient, TopBar, StartTab, StatusPanel, MazeView, VariablesTab, PlotsTab, Plot, TwinTab, CameraTab, TopicHealthMonitor, ReplayController
- Background processes: GameManager, Recorder
- 3D Twin: ThreeTwinViewport
- Fixture publisher script (in `fixtures/`) for the Dec 4 demo

Sample recordings in `shared/samples/` are owned by E.

The internal folder layout of this module is decided by the module team.

## Tests and Dec 4 demo

Every test has its inputs in `fixtures/<TEST-ID>/` (input files + a README saying what can be edited) and runs with

```
python run_test.py <TEST-ID>
```

which prints PASS or FAIL for every check. The test computes the expected result itself and never needs another module.

| Test | Requirement | Fixtures |
| --- | --- | --- |
| E-T1 Plot rate | E-R1 | [fixtures/E-T1](fixtures/E-T1/) |
| E-T2 Button states | E-R2 | [fixtures/E-T2](fixtures/E-T2/) |
| E-T3 Commands | E-R2 | [fixtures/E-T3](fixtures/E-T3/) |
| E-T4 E-stop not confirmed | E-R2 | [fixtures/E-T4](fixtures/E-T4/) |
| E-T5 Variables | E-R3 | [fixtures/E-T5](fixtures/E-T5/) |
| E-T6 Missing data | E-R4 | [fixtures/E-T6](fixtures/E-T6/) |
| E-T7 Recording | E-R5 | [fixtures/E-T7](fixtures/E-T7/) |
| E-T8 No replay in the recording | E-R5 | [fixtures/E-T8](fixtures/E-T8/) |
| E-T9 Camera and 3D | E-R6 | [fixtures/E-T9](fixtures/E-T9/) |
| E-T10 Game states | E-R7 | [fixtures/E-T10](fixtures/E-T10/) |
| E-T11 Finish | E-R8 | [fixtures/E-T11](fixtures/E-T11/) |
| E-T12 Heartbeat | E-R9 | [fixtures/E-T12](fixtures/E-T12/) |
| E-T13 Warnings | E-R10 | [fixtures/E-T13](fixtures/E-T13/) |
| E-T14 3D Twin | E-R6 | [fixtures/E-T14](fixtures/E-T14/) |
| E-T15 Safe replay | E-R11 | [fixtures/E-T15](fixtures/E-T15/) |
| E-T16 Windows and Linux | E-R12 | [fixtures/E-T16](fixtures/E-T16/) |
