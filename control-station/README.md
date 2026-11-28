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

## Desktop app

The Electron app: the main process is in `src/main/`, the UI in `src/renderer/`. The UI imports `shared/` from the repository root (`@shared/bus/bus`, `@shared/topics`, `@shared/mazes/mazes`), so both folders need their packages; otherwise typecheck and build fail with `mqtt` and `ajv` not found:

```
npm ci              # in the repository root: mqtt and ajv for shared/
cd control-station
npm ci              # Electron, electron-vite and electron-builder
```

Then, in `control-station/`:

| Command | What it does |
| --- | --- |
| `npm run dev` | starts the app with live reload |
| `npm run typecheck` | checks the types of the app and GameManager without building |
| `npm run build` | builds the app into `out/` |
| `npm run dist:win` | Windows installer in `dist/` |
| `npm run dist:linux` | Linux AppImage in `dist/` |

The app connects to the broker over WebSocket at `ws://127.0.0.1:9001` (IF-03). Mosquitto opens that port only with the shared config:

```
mosquitto -c ../shared/bus/mosquitto.conf
```

On Ubuntu 24.04 the AppImage needs `sudo apt install libfuse2t64`, or run it with `--appimage-extract-and-run`.

### Maze view

The Start tab's right column shows the maze, north (+y) up: walls, the start cell, the exit marker (green), the path to the exit (yellow) and the ball (a grey ring when it is lost or older than 200 ms). A wall hit (`vision/event`) turns that wall red for 1 s. The path follows `plan/distance_map` from the `ball_cell` of `plan/route` with the shared maze helper (`shared/mazes/mazes.ts`), and is drawn only while the maze, the map and the route have the same `maze_id`, the route is younger than 300 ms and `vision/edit_state` is `clear` (a missing or stale edit state counts as not clear). "No path to the exit" is shown only for a route with status `no_path`. It redraws at 20 Hz while the Start tab is open (`maze_view_rate_hz` follows with the cs variables, #142).

## GameManager

A Node.js background process in `game-manager/`, separate from the Electron app. Run `npm ci` once at the repository root (GameManager takes `mqtt`, `ajv` and `tsx` from there), then from this folder:

```
npm run game-manager                 # broker at mqtt://127.0.0.1:1883
npm run game-manager <broker-url>    # another broker
```

## Recorder

The Recorder is a Node.js background process and continues running when the desktop app closes. Install the Control Station dependencies once at the repository root with `npm ci`, then start the Recorder from this folder:

```
npm run recorder                 # broker at mqtt://127.0.0.1:1883
npm run recorder -- <broker-url> # another broker
```

It writes one IF-09 JSONL file per game into `recordings/` in this folder by default. The recording folder and tail duration come from the Control Station variable spec and applied settings (`recording_folder` and `recording_tail_s`). The tail defaults to 2 seconds.

## Station: the background programs in one terminal

GameManager, the Recorder and the shared replay tool (`listen` mode, for the app's replay controls) run outside the app. Start the broker first, activate the Python venv (the replay tool is Python), then from this folder:

```
npm run station
```

- Each line starts with the program's name: `[game-manager]`, `[recorder]`, `[replay]`.
- Each program is its own process: if one stops, the others go on, and closing the app stops none of them (E-R5).
- Ctrl+C stops all three.
- **Keep this terminal open during a game.** Closing it stops the programs, and so the recording too.
- The app is started separately (`npm run dev` or the built app).
- The same command works on Windows and Linux (E-R12).
- The programs connect to the broker at start and stop if it is not there; start the broker first.

## Replay

The replay controls are on the Start tab (ReplayController). They list the files in `recordings/` in this folder, and the shared replay tool plays the chosen file. `npm run station` starts the tool together with GameManager and the Recorder (see above). To start it alone, from this folder with the Python venv active (it runs `python -m shared.tools.replay listen` from the repository root with the same folder):

```
npm run replay
```

The replay tool skips every topic whose real writer is online, so stop the fixture publisher before a replay. The publisher also has a script: `npm run fixture-publisher` (options after `--`, e.g. `npm run fixture-publisher -- --no-respond`).

Then choose a file and a speed (0.5x, 1x, 2x) and press Play. Pause, Play (to continue) and Stop send `replay_pause`, `replay_resume` and `replay_stop`. While the replay runs, the top bar shows the "Replay" banner and the controls show the recorded state, mode, time, progress and result.

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
