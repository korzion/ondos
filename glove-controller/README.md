# B · Glove Controller

Team: `@korzion/glove-controller` · Design: *Ondos Module Design*, Part II-B

| | |
| --- | --- |
| Members | Aayan, Arif, Mert |
| Runs on | Glove ESP32 (ESP32-C3) |
| Languages | C++ (PlatformIO) |
| Interfaces | Owns IF-01. B never talks to the laptop. |

## Parts (from the design document)

- Glove firmware: ImuFilter, HapticController, EspNowLink
- Receiver ESP32 test firmware (stand-in for the platform on Dec 4): sends GameInfo at 5 Hz, prints packets, sends Haptic commands

ESP-NOW packet headers (IF-01) and the pairing MAC config header in `shared/` are owned by B. Firmware and bridge use the generated packet definitions in `shared/firmware/include/` (C++) and `shared/protocol/` (Python) instead of writing packet structs by hand; the byte layout is a DRAFT to be confirmed by A and B (`shared/interfaces/README.md`).

The internal folder layout of this module is decided by the module team.

## Tests and Dec 4 demo

Every test has its inputs in `fixtures/<TEST-ID>/` (input files + a README saying what can be edited) and runs with

```
python run_test.py <TEST-ID>
```

which prints PASS or FAIL for every check. The test computes the expected result itself and never needs another module.

| Test | Requirement | Fixtures |
| --- | --- | --- |
| B-T1 Rate and delay | B-R1 | [fixtures/B-T1](fixtures/B-T1/) |
| B-T2 Vibration patterns | B-R2 | [fixtures/B-T2](fixtures/B-T2/) |
| B-T3 Disconnect | B-R4 | [fixtures/B-T3](fixtures/B-T3/) |
| B-T4 Calibration and signs | B-R3 | [fixtures/B-T4](fixtures/B-T4/) |
