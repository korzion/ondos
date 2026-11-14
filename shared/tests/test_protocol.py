import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from shared.protocol import packets
from shared.protocol.framing import FrameReader, cobs_decode, cobs_encode, crc16_ccitt_false, frame, unframe

ROOT = Path(__file__).resolve().parents[2]


def test_crc_check_value():
    # CRC-16/CCITT-FALSE check value for "123456789"
    assert crc16_ccitt_false(b"123456789") == 0x29B1


@pytest.mark.parametrize("data", [b"", b"\x00", b"\x00\x00", b"\x11\x22\x00\x33", bytes(range(1, 255)), bytes(range(256)) * 3])
def test_cobs_roundtrip(data):
    enc = cobs_encode(data)
    assert 0 not in enc
    assert cobs_decode(enc) == data


def test_frame_roundtrip_and_broken_frames():
    payload = packets.pack("serial", "TargetTilt", {"target_tilt_x_deg": 2.5, "target_tilt_y_deg": -1.0})
    raw = frame(payload)
    assert raw[-1] == 0 and 0 not in raw[:-1]
    assert unframe(raw[:-1]) == payload
    bad = bytearray(raw[:-1])
    bad[2] = 0x55 if bad[2] != 0x55 else 0x56  # corrupt one byte, never into a delimiter
    reader = FrameReader()
    out = list(reader.feed(raw + bytes(bad) + b"\x00" + raw))
    assert out == [payload, payload] and reader.broken_frames == 1


def test_packet_roundtrip_with_enums():
    fields = {"tilt_x_deg": 1.5, "tilt_y_deg": -0.5, "applied_tilt_x_deg": 1.0, "applied_tilt_y_deg": 0.0,
              "source": "glove", "mode": "simple", "mode_button_presses": 3, "is_e_stop": False,
              "is_laptop_connected": True, "is_glove_connected": True, "fault": "imu"}
    name, back = packets.unpack("serial", packets.pack("serial", "PlatformState", fields))
    assert name == "PlatformState" and back == fields


def test_haptic_pattern_ids_from_the_document():
    assert packets.CODES["haptic_pattern"] == {"not_moving": 1, "away_from_exit": 2, "mode_changed": 3, "calibrated": 4}
    assert packets.PACKETS["espnow"]["GloveData"]["msg_type"] == 1
    assert packets.PACKETS["espnow"]["GameInfo"]["msg_type"] == 10


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_cpp_framing_and_structs_match_python(tmp_path):
    src = tmp_path / "t.cpp"
    src.write_text(r'''
#include <cstdio>
#include "ondos_packets.h"
#include "ondos_framing.h"
int main() {
  ondos::serial::TargetTilt t; t.target_tilt_x_deg = 2.5f; t.target_tilt_y_deg = -1.0f;
  uint8_t tmp[64], out[64];
  size_t n = ondos::frame(reinterpret_cast<uint8_t*>(&t), sizeof t, tmp, out);
  for (size_t i = 0; i < n; ++i) printf("%02x", out[i]);
  return 0;
}''')
    exe = tmp_path / "t"
    subprocess.run(["g++", "-std=c++17", f"-I{ROOT / 'shared/firmware/include'}", str(src), "-o", str(exe)], check=True)
    cpp = bytes.fromhex(subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout)
    py = frame(packets.pack("serial", "TargetTilt", {"target_tilt_x_deg": 2.5, "target_tilt_y_deg": -1.0}))
    assert cpp == py
