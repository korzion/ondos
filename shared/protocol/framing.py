"""IF-02 serial framing: COBS + CRC-16/CCITT-FALSE (owner: A).

frame = COBS(payload + crc16(payload) little endian) + b"\\x00"
The same algorithm is in shared/firmware/include/ondos_framing.h for the ESP32.
"""
from __future__ import annotations


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final xor."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out = bytearray()
    block = bytearray()
    for b in data:
        if b == 0:
            out.append(len(block) + 1)
            out += block
            block.clear()
        else:
            block.append(b)
            if len(block) == 254:
                out.append(255)
                out += block
                block.clear()
    out.append(len(block) + 1)
    out += block
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0 or i + code > len(data) + (0 if code > 1 else 1):
            raise ValueError("bad COBS data")
        out += data[i + 1:i + code]
        i += code
        if code < 255 and i < len(data):
            out.append(0)
    return bytes(out)


def frame(payload: bytes) -> bytes:
    crc = crc16_ccitt_false(payload)
    return cobs_encode(payload + bytes((crc & 0xFF, crc >> 8))) + b"\x00"


def unframe(raw: bytes) -> bytes:
    """raw = bytes between two 0x00 delimiters. Returns the payload; ValueError on a broken frame."""
    data = cobs_decode(raw)
    if len(data) < 3:
        raise ValueError("frame too short")
    payload, crc = data[:-2], data[-2] | (data[-1] << 8)
    if crc16_ccitt_false(payload) != crc:
        raise ValueError("CRC mismatch")
    return payload


class FrameReader:
    """Feed it serial bytes; it yields complete payloads and counts broken frames."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.broken_frames = 0

    def feed(self, data: bytes):
        self._buf += data
        while True:
            end = self._buf.find(0)
            if end < 0:
                return
            raw = bytes(self._buf[:end])
            del self._buf[:end + 1]
            if not raw:
                continue
            try:
                yield unframe(raw)
            except ValueError:
                self.broken_frames += 1
