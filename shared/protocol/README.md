# shared/protocol

Python side of the binary links.

- `packets.py` (generated): `pack(link, name, fields)` and `unpack(link, payload)` for IF-01 (`"espnow"`) and IF-02 (`"serial"`). Enum fields are names (`"glove"`), not numbers.
- `framing.py`: IF-02 serial framing, COBS + CRC-16/CCITT-FALSE; `FrameReader` turns serial bytes into payloads and counts broken frames.
- `monitor.py`: prints the packets arriving on a serial port: `python -m shared.protocol.monitor COM3` (needs `pip install pyserial`).

The byte layout is a DRAFT until A (serial) and B (ESP-NOW) confirm it; see `shared/interfaces/README.md`.
