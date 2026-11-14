# shared/firmware/include

C++ headers for the platform ESP32 (A) and the glove ESP32 (B). Use these instead of writing packet structs by hand, so both sides always agree.

| Header | What |
| --- | --- |
| `ondos_packets.h` | IF-01 and IF-02 packet structs, msg_type numbers, number codes, safety timeouts (generated) |
| `ondos_framing.h` | IF-02 serial framing: COBS + CRC-16/CCITT-FALSE |
| `ondos_pairing.h` | ESP-NOW MAC addresses of the two boards (to be filled in by B) |

In a PlatformIO project, add the folder to the include path, e.g. in `platformio.ini`:

```
build_flags = -std=gnu++17 -I${PROJECT_DIR}/../../shared/firmware/include
```

(adjust the `../` to where the project is). `../examples/packet_check/` is a tiny project that sends a known packet; check it on the laptop with `python -m shared.protocol.monitor <port>`.

The byte layout is a DRAFT until A and B confirm it; to change it, edit `shared/interfaces/packets/` and run `python shared/interfaces/gen.py`.
