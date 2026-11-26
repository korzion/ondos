"""Fixture publisher for the Control Station (issue #87, design document E.9).

    python control-station/fixtures/fixture_publisher/fixture_publisher.py [--host H] [--port P] [--data DIR] [--no-respond]

Plays the ready data files in data/ (lines {"t_s", "topic", "msg"}, the format of the playback tool's fixture mode)
for the platform bridge, Vision and the Auto Controller, and answers cs/command and cs/variables/<key> as
data/behaviour.json says. It has no maze, route or controller logic and never writes game/state or game/warning.
Prepare the data files with make_fixture.py (see README.md). Needs a broker: mosquitto -c shared/bus/mosquitto.conf
"""
import argparse
import json
import logging
import queue
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))  # repo root, for `import shared`

import paho.mqtt.client as mqtt  # noqa: E402

from engine import DataError, Engine  # noqa: E402
from shared import topics as T  # noqa: E402
from shared.bus import Bus, now_s  # noqa: E402
from topic_table import STAND_IN_PROGRAMS, Publication, writer_of  # noqa: E402

log = logging.getLogger("fixture_publisher")
TICK_S = 0.005
QUIT_KEY = "q"
_ANY_KEY = T.CONFIG_KEY_VALUES[0]
CS_VARIABLES_PATTERN = T.cs_variables(_ANY_KEY).replace(_ANY_KEY, "+")  # cs/variables/+, from the shared topic helper


class Publisher:
    def __init__(self, engine: Engine, host: str, port: int) -> None:
        self._engine = engine
        self._host, self._port = host, port
        self._buses: dict[str, Bus] = {}
        self._ball_seqs: dict[int, int] = {}  # sample number in the data -> seq of the vision/ball message sent for it
        self._incoming: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._listener = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ondos-fixture-listener")

    def run(self) -> None:
        self._connect_listener()
        threading.Thread(target=self._read_keys, daemon=True).start()
        print(self._engine.help_text())
        try:
            while not self._stop.is_set():
                self._handle_incoming()
                self._publish(self._engine.tick(now_s()))
                time.sleep(TICK_S)
        finally:
            self._close()

    # ------------------------------------------------------------------ incoming
    def _connect_listener(self) -> None:
        self._listener.on_connect = self._subscribe_to_app_topics
        self._listener.on_message = self._on_listener_message
        self._listener.connect(self._host, self._port)
        self._listener.loop_start()

    @staticmethod
    def _subscribe_to_app_topics(client, userdata, flags, reason_code, properties) -> None:
        for pattern in (T.CS_COMMAND, CS_VARIABLES_PATTERN):
            client.subscribe(pattern, qos=1)

    def _on_listener_message(self, client, userdata, message: mqtt.MQTTMessage) -> None:
        try:
            msg = json.loads(message.payload)
        except ValueError:
            return
        key = None if message.topic == T.CS_COMMAND else message.topic.rsplit("/", 1)[1]
        self._incoming.put(("command" if key is None else "variables", key, msg))

    def _read_keys(self) -> None:
        """Manual triggers: a letter and Enter (input() works the same on Windows and Linux)."""
        while not self._stop.is_set():
            try:
                line = input().strip()
            except EOFError:
                return
            if line == QUIT_KEY:
                self._stop.set()
            elif line:
                self._incoming.put(("key", line, None))

    def _handle_incoming(self) -> None:
        while not self._incoming.empty():
            kind, detail, msg = self._incoming.get()
            if kind == "command":
                self._engine.on_command(msg, now_s())
            elif kind == "variables":
                self._publish(self._engine.on_variables(detail, msg))
            elif not self._engine.press(detail, now_s()):
                print(self._engine.help_text())
            else:
                log.info("key %s", detail)

    # ------------------------------------------------------------------ outgoing
    def _publish(self, publications: list[Publication]) -> None:
        self._sync_connections()
        for publication in publications:
            self._send(publication)

    def _send(self, publication: Publication) -> None:
        """ball_seq must be the seq of the ball message it answers (IF-04), which only the bus knows.

        A route or tilt whose ball message was not sent is not sent either.
        """
        fields = publication.fields
        if "ball_seq" in fields:
            seq = self._ball_seqs.get(fields["ball_seq"])
            if seq is None:
                return
            fields = {**fields, "ball_seq": seq}
        bus = self._buses.get(publication.program)
        if bus is None or not bus.is_connected():
            self._ball_seqs.pop(publication.ball_index, None)
            return
        sent = bus.publish(publication.topic, fields)
        if publication.ball_index is not None:
            self._ball_seqs[publication.ball_index] = sent["seq"]

    def _sync_connections(self) -> None:
        """A program is online while it is not switched off: sys/online/<program> follows the bus connection."""
        for program in STAND_IN_PROGRAMS:
            bus = self._buses.get(program)
            is_wanted = program not in self._engine.offline_programs
            if is_wanted and bus is None:
                self._buses[program] = bus = Bus(program, self._host, self._port)
                bus.connect()
                log.info("%s online", program)
            elif not is_wanted and bus is not None:
                bus.close()
                del self._buses[program]
                if program == writer_of(T.VISION_BALL):
                    self._ball_seqs.clear()  # no ball messages from now on, and a new connection counts from 0
                log.info("%s offline", program)

    def _close(self) -> None:
        self._listener.loop_stop()
        self._listener.disconnect()
        for bus in self._buses.values():
            bus.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=T.BROKER_HOST)
    parser.add_argument("--port", type=int, default=T.BROKER_TCP_PORT)
    parser.add_argument("--data", type=Path, default=HERE / "data", help="folder with the ready data files")
    parser.add_argument("--no-respond", action="store_true", help="play the data but answer no command (E-T4)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        engine = Engine(args.data, respond=not args.no_respond)
        Publisher(engine, args.host, args.port).run()
    except DataError as error:
        print(f"data error: {error}", file=sys.stderr)
        return 2
    except ConnectionError as error:
        print(f"{error}. Start the broker: mosquitto -c shared/bus/mosquitto.conf", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
