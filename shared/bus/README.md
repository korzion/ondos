# shared/bus

Bus helpers for every laptop program (IF-03). They add the envelope (`timestamp_s`, `seq`, `version`, `writer`), take QoS and the retained flag from `shared/interfaces/topics.json`, check every message against its schema, drop repeated QoS 1 deliveries, drop `writer = replay` unless asked, and publish `sys/online/<program>` (true on connect, false through the MQTT Last Will).

## Broker

```
mosquitto -c shared/bus/mosquitto.conf      # TCP 1883 for programs, WebSocket 9001 for the app UI
```

Windows: install Mosquitto and run it as a service with this file. Linux: `sudo apt install mosquitto`.

## Python (bridge, Vision, Auto Controller, tools)

```python
from shared.bus import Bus
from shared import topics as T

bus = Bus("vision")                       # program id = envelope writer
bus.subscribe(T.GAME_STATE, on_state)     # on_state(topic, msg, t_recv_s)
bus.connect()
bus.publish(T.VISION_BALL, {"x_mm": 1.0, ...})   # only the topic's own fields
bus.unsubscribe(T.GAME_STATE, on_state)   # one callback; without it, the whole pattern
```

Setup once from the repository root: `pip install -e .`

## TypeScript (GameManager, Recorder, Control Station app)

```ts
import { Bus } from "../shared/bus/bus";
import { GAME_STATE } from "../shared/topics";

const bus = new Bus("game_manager");              // ws://127.0.0.1:9001 in the app UI
bus.subscribe(VISION_BALL, (topic, msg, tRecvS) => { ... });
await bus.connect();
bus.publish(GAME_STATE, { state: "setup", ... });
bus.unsubscribe(VISION_BALL, onBall);             // one callback; without it, the whole pattern
```

Setup once from the repository root: `npm install`. Tests: `npm test`.

Readers judge the age of a message by its `timestamp_s` (`age_s(msg)` / `ageS(msg)`), never by when it arrived (IF-03).
