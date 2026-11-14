# A · Tilting Platform

Team: `@korzion/tilting-platform` · Design: *Ondos Module Design*, Part II-A

| | |
| --- | --- |
| Members | Beyzanur, Enis Talha, Mohammed, Aayan |
| Runs on | Platform ESP32 (ESP32-S3); platform bridge on the station laptop |
| Languages | C++ (PlatformIO) on the ESP32; Python 3.11 for the bridge |
| Interfaces | Owns IF-02. Uses IF-01, IF-05, IF-06, IF-07. |

## Parts (from the design document)

- Firmware (ESP32-S3): PlatformController, MotorController, IMUHandler, SafetyManager, GloveHandler, SerialHandler
- Platform bridge (Python): PlatformBridge, MQTTHandler
- Serial test script for the Dec 4 demo

Serial packet headers (IF-02) in `shared/` are owned by A. Firmware and bridge use the generated packet definitions in `shared/firmware/include/` (C++) and `shared/protocol/` (Python) instead of writing packet structs by hand; the byte layout is a DRAFT to be confirmed by A and B (`shared/interfaces/README.md`).

The internal folder layout of this module is decided by the module team.

## Tests and Dec 4 demo

Every test has its inputs in `fixtures/<TEST-ID>/` (input files + a README saying what can be edited) and runs with

```
python run_test.py <TEST-ID>
```

which prints PASS or FAIL for every check. The test computes the expected result itself and never needs another module.

| Test | Requirement | Fixtures |
| --- | --- | --- |
| A-T1 Two-axis tilt | A-R1 | [fixtures/A-T1](fixtures/A-T1/) |
| A-T2 Glove control | A-R2 | [fixtures/A-T2](fixtures/A-T2/) |
| A-T3 Laptop commands | A-R3 | [fixtures/A-T3](fixtures/A-T3/) |
| A-T4 State publishing | A-R4 | [fixtures/A-T4](fixtures/A-T4/) |
| A-T5 Safe state | A-R5 | [fixtures/A-T5](fixtures/A-T5/) |
