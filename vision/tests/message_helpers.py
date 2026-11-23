"""Bus message helpers for the unit tests."""
from __future__ import annotations

from shared import topics as T
from shared.bus import now_s


def with_envelope(topic: str, fields: dict, writer: str, seq: int = 0, timestamp_s: float | None = None) -> dict:
    """A complete bus message, as the shared bus helper would build it (IF-03)."""
    envelope = {
        "timestamp_s": now_s() if timestamp_s is None else timestamp_s,
        "seq": seq,
        "version": T.topic_info(topic)["version"],
        "writer": writer,
    }
    return {**envelope, **fields}
