# shared

Code and data used by more than one module (design document IF-03). A library in the repository, never a running module: using it does not make one module depend on another running module.

| Folder | What | Owner |
| --- | --- | --- |
| `interfaces/` | Single source of topic names, message schemas (JSON Schema), packet layouts and fixed constants; `topics.py` / `topics.ts` are generated from it | Shared |
| `bus/` | Bus helpers (envelope, sys/online) for Python and TypeScript; `mosquitto.conf` | Shared |
| `protocol/`, `firmware/include/` | IF-02 serial framing and IF-01 / IF-02 packet definitions for the bridge (Python) and the ESP32s (C++) | A (serial), B (ESP-NOW) |
| `mazes/` | Maze file format, consistency check, distance map and route function | C |
| `tools/replay/` | Playback tool: replay mode and fixture mode (IF-09) | Shared |
| `testing/` | Common base for every module's `run_test.py` | Shared |
| `samples/` | Sample recordings for standalone demos | E |

Every item has one owner. Nobody changes an item alone: a change needs the agreement of the modules that use it. Announce every change to the whole team.

## Starting decisions and how they change

Where the design document leaves a detail open (for example byte layouts or number codes), `shared/` holds a starting decision so that every module can begin now. Items marked DRAFT are such decisions.

- Proposals are welcome: open an issue or a PR and tag the modules that use the item.
- A change that affects one module, or that is easy to follow, is made.
- A change that affects many modules or many parameters is not made; the modules follow the current decision.

Birden fazla modülün kullandığı kod ve tanımlar. Buradaki her değişiklik, onu kullanan modüllerin onayıyla yapılır ve tüm ekibe duyurulur.
