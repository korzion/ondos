"""Start Vision from the repository root.

    python -m vision                      # USB camera (camera_index from config/vision_config.json)
    python -m vision --clip DIR           # play a recorded clip folder instead of the camera
    python -m vision --record DIR         # also save every frame and its arrival time to DIR
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from shared import topics as T
from shared.bus import Bus
from vision.board_calibrator import BoardCalibrator
from vision.config_file import ConfigError
from vision.frame_grabber import FrameGrabber
from vision.vision_config import DEFAULT_CONFIG_PATH, load_vision_config
from vision.vision_node import VisionNode
from vision.vision_variables import DEFAULT_VARIABLES_PATH, VisionVariables

PROGRAM_ID = "vision"  # envelope writer and sys/online/vision (IF-03)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

log = logging.getLogger("vision")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m vision", description="Ondos Vision (module C).")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Vision configuration file")
    parser.add_argument("--variables", type=Path, default=DEFAULT_VARIABLES_PATH, help="control variable definitions")
    parser.add_argument("--clip", type=Path, help="play this recorded clip folder instead of the camera")
    parser.add_argument("--record", type=Path, help="record every frame and its arrival time to this folder")
    parser.add_argument("--host", default=T.BROKER_HOST, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=T.BROKER_TCP_PORT, help="MQTT broker port")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        config = load_vision_config(args.config)
        variables = VisionVariables.load(args.variables, default_overrides={"camera_index": config.camera_index})
        grabber = FrameGrabber(config.frame_width_px, config.frame_height_px, config.camera_fps_hz)
        if args.record is not None:
            grabber.start_recording(args.record)
        node = VisionNode(variables, grabber, Bus(PROGRAM_ID, args.host, args.port), BoardCalibrator(config),
                          clip_dir=args.clip)
        node.run()
    except (ConfigError, ConnectionError, FileExistsError, FileNotFoundError) as error:
        log.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
