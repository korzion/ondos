"""Print the IF-02 packets that arrive on a serial port (read only).

    pip install pyserial
    python -m shared.protocol.monitor COM3          # Windows
    python -m shared.protocol.monitor /dev/ttyUSB0  # Linux
"""
from __future__ import annotations

import argparse

from shared.protocol.framing import FrameReader
from shared.protocol.packets import unpack


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("--baud", type=int, default=921600)
    a = ap.parse_args()
    import serial  # pyserial

    reader = FrameReader()
    with serial.Serial(a.port, a.baud, timeout=0.1) as port:
        print(f"listening on {a.port} at {a.baud} baud, Ctrl+C to stop")
        while True:
            for payload in reader.feed(port.read(256)):
                try:
                    name, fields = unpack("serial", payload)
                    print(name, fields)
                except ValueError as e:
                    print("unknown packet:", e, payload.hex())
            if reader.broken_frames:
                print(f"broken frames so far: {reader.broken_frames}")
                reader.broken_frames = 0


if __name__ == "__main__":
    main()
