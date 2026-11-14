# shared/interfaces

Single source of the bus and packet interfaces (design document, Appendix IF-01 … IF-09). Code is generated from here; nobody types a topic string or a field name by hand.

| Source (edit these) | What |
| --- | --- |
| `topics.json` | Every topic: writer, QoS, retained, payload type, schema, version (section 6.2, IF-03) |
| `schemas/*.schema.json` | JSON Schema (2020-12) of every message and file; `common.schema.json` holds every enum |
| `variables.json` | Configuration keys, their owner and the variable names of A.7 … E.7 |
| `constants.json` | The fixed numbers: safety timeouts, broker ports |
| `packets/*.json` | IF-01 (ESP-NOW) and IF-02 (serial) packets and their number codes — **DRAFT**, see below |
| `examples/` | One valid example per topic, and an example maze file |

| Generated (never edit) | Used by |
| --- | --- |
| `shared/topics.py`, `shared/topics.ts` | every laptop program: topic names, enums, constants |
| `schemas.bundle.json` | `shared/bus/bus.ts` |
| `shared/protocol/packets.py` | platform bridge |
| `shared/firmware/include/ondos_packets.h` | platform and glove firmware |

After changing a source:

```
python shared/interfaces/gen.py          # regenerate
python -m pytest                          # examples still valid, generated files up to date
```

CI fails when a generated file is out of date (`gen.py --check`).

## Rules the schemas enforce

- Envelope on every message except `vision/image` and `sys/online/<program>` (IF-03); `version` must be the supported one (all topics start at 1).
- Every field is required; a field without a value right now is `null` only where the document allows it (D4).
- No unknown fields; enum values exactly as in the document.
- Physical ranges that depend on settings (±max_tilt_deg, frame_age_ms targets) are not enforced here; percentages, counts and enums are.
- `cs/variables/<key>` and `<key>/variables_spec` may only use the variable names of that key.

## Starting decisions (not in the document)

| Item | Decision | Owner to confirm |
| --- | --- | --- |
| IF-01 / IF-02 byte layout | First byte msg_type, then the fields in the document's order, packed, little endian; bool = 1 byte; float = 4 bytes | B (IF-01), A (IF-02) |
| Number codes | `packets/codes.json` (e.g. mode glove=0, ai=1, simple=2). Haptic pattern IDs 1–4 and IF-01 msg_type 1, 2, 10, 11 are from the document | A, B |
| IF-02 message numbers | ESP32 → bridge 20–22, bridge → ESP32 30–34, InjectGloveData 40 (test build only, A-T2) | A |
| IF-02 Settings | One packet with all platform and glove variables | A |
| Ball and exit colour variables | `ball_h_min, ball_h_max, ball_s_min, ball_s_max, ball_v_min, ball_v_max` (and `exit_…`) for the document's "ball_h_min … ball_v_max" | C |
| Replay and sys/online | The playback tool does not replay `sys/online/*` lines; it publishes its own `sys/online/replay` (IF-09) | Shared |

Changes follow the rules in `shared/README.md`.
