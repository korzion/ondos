# C · Vision

Team: `@korzion/vision` · Design: *Ondos Module Design*, Part II-C

| | |
| --- | --- |
| Members | Talha, Mert, İbrahim, Yağmur |
| Runs on | Station laptop (own process) |
| Languages | Python 3.11 (OpenCV, NumPy) |
| Interfaces | Owns IF-04 and the maze file format. |

## Parts (from the design document)

- VisionNode, FrameGrabber, BoardCalibrator, BallTracker, EventDetector, MazeReader, OverlayRenderer, PathPlanner, EditDetector
- Configuration file: plate size, marker IDs/sizes/positions, camera_index

`shared/mazes/` (maze format, consistency check, distance map and route function) is owned by C.

The internal folder layout of this module is decided by the module team.

## Tests and Dec 4 demo

Every test has its inputs in `fixtures/<TEST-ID>/` (input files + a README saying what can be edited) and runs with

```
python run_test.py <TEST-ID>
```

which prints PASS or FAIL for every check. The test computes the expected result itself and never needs another module.

| Test | Requirement | Fixtures |
| --- | --- | --- |
| C-T1 Position accuracy | C-R1 | [fixtures/C-T1](fixtures/C-T1/) |
| C-T2 Delay | C-R2 | [fixtures/C-T2](fixtures/C-T2/) |
| C-T3 Maze scan | C-R3 | [fixtures/C-T3](fixtures/C-T3/) |
| C-T4 Exit detection | C-R4 | [fixtures/C-T4](fixtures/C-T4/) |
| C-T5 Lost ball | C-R5 | [fixtures/C-T5](fixtures/C-T5/) |
| C-T6 Wall hits | C-R6 | [fixtures/C-T6](fixtures/C-T6/) |
| C-T7 Route | C-R7 | [fixtures/C-T7](fixtures/C-T7/) |
| C-T8 Maze change | C-R8 | [fixtures/C-T8](fixtures/C-T8/) |
| C-T9 False pauses | C-R9 | [fixtures/C-T9](fixtures/C-T9/) |
