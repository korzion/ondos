"""Convert IF-09 JSONL game recordings into causally joined training rows (D.5, D-R6)."""
from __future__ import annotations

import copy
import itertools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared import topics as T
from shared.interfaces import ValidationError, validate, validate_file

EXCLUSION_REASONS = (
    "replay",
    "invalid_message",
    "missing_game_state",
    "stale_game_state",
    "not_playing",
    "ball_not_visible",
    "invalid_ball",
    "missing_maze",
    "missing_distance_map",
    "missing_route",
    "maze_mismatch",
    "invalid_route",
    "stale_route",
    "route_mismatch",
    "missing_platform_state",
    "platform_fault_or_estop",
    "invalid_platform_state",
    "stale_platform_state",
)

_IMITATION_SOURCES = frozenset({"glove", "ai", "simple"})
_SNAPSHOT_TOPICS = frozenset({
    T.GAME_STATE,
    T.PLATFORM_STATE,
    T.VISION_MAZE,
    T.PLAN_DISTANCE_MAP,
    T.PLAN_ROUTE,
})


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _new_excluded_counts() -> dict[str, int]:
    return {reason: 0 for reason in EXCLUSION_REASONS}


@dataclass(frozen=True)
class TrainingRow:
    """Single training sample joined causally from a recorded vision/ball message."""

    # Provenance & causality timestamps (Recorder clock t_recv_s)
    game_id: str
    maze_id: str
    mode: str
    ball_seq: int
    route_ball_seq: int
    t_recv_s: float
    t_game_state_s: float
    t_platform_state_s: float
    t_maze_s: float
    t_distance_map_s: float
    t_route_s: float

    # Observation fields (D4 units)
    x_mm: float
    y_mm: float
    vx_mm_s: float
    vy_mm_s: float
    is_predicted: bool
    is_on_exit: bool
    tilt_x_deg: float
    tilt_y_deg: float
    target_points_mm: list[list[float]]
    distance_to_exit_cells: int | None
    ball_cell: dict[str, int] | None

    # Maze snapshot summary
    maze_rows: int
    maze_cols: int
    cell_size_mm: float

    # Label fields (IF-09: applied tilt from platform/state, never raw glove tilt)
    applied_tilt_x_deg: float
    applied_tilt_y_deg: float
    source: str

    # Freshness & imitation flags (IF-09)
    platform_age_ms: float
    game_state_age_ms: float
    route_age_ms: float
    is_platform_stale: bool
    is_usable_for_imitation: bool


@dataclass
class RecordingStats:
    """Counts of processed, kept, stale-marked, and excluded recording samples."""

    total_lines: int = 0
    ball_samples: int = 0
    kept_rows: int = 0
    stale_platform_marked: int = 0
    imitation_rows: int = 0
    excluded: dict[str, int] = field(default_factory=_new_excluded_counts)
    maze_ids: list[str] = field(default_factory=list)


@dataclass
class LoadedRecording:
    """Parsed recording output containing clean rows, stale-marked rows, and stats."""

    path: Path
    header: dict[str, Any]
    rows: list[TrainingRow]
    all_rows: list[TrainingRow]
    stats: RecordingStats


class RecordingReader:
    """Reads IF-09 JSONL recordings and joins valid samples without future or cross-maze leakage."""

    def __init__(self, validate_messages: bool = True) -> None:
        self.validate_messages = validate_messages
        self._loaded: LoadedRecording | None = None

    def load(self, path: str | Path) -> LoadedRecording:
        """Load and parse an IF-09 JSONL recording file into causal TrainingRows."""
        rec_path = Path(path)
        raw_lines = [line for line in rec_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not raw_lines:
            raise ValueError(f"{rec_path}: empty recording file")

        try:
            header = json.loads(raw_lines[0])
        except json.JSONDecodeError as exc:
            raise ValueError(f"{rec_path}:1: invalid JSON header: {exc}") from exc

        try:
            validate_file("recording_header", header)
        except ValidationError as exc:
            raise ValueError(f"{rec_path}:1: invalid recording header: {exc}") from exc

        if header.get("format_version") != T.RECORDING_FORMAT_VERSION:
            raise ValueError(
                f"{rec_path}:1: unsupported format_version {header.get('format_version')!r}"
            )

        stats = RecordingStats(total_lines=len(raw_lines) - 1)
        parsed_lines: list[tuple[float, int, str, Any]] = []

        for line_no, raw in enumerate(raw_lines[1:], start=2):
            try:
                entry = json.loads(raw)
                validate_file("recording_line", entry)
            except (json.JSONDecodeError, ValidationError):
                stats.excluded["invalid_message"] += 1
                continue

            t_recv_s = entry["t_recv_s"]
            if not _is_finite_number(t_recv_s):
                stats.excluded["invalid_message"] += 1
                continue

            parsed_lines.append((float(t_recv_s), line_no, entry["topic"], entry["msg"]))

        # Process strictly in Recorder clock order (t_recv_s) to prevent any future leakage.
        parsed_lines.sort(key=lambda item: (item[0], item[1]))

        snapshots: dict[str, tuple[float, dict[str, Any]]] = {}
        rows: list[TrainingRow] = []
        all_rows: list[TrainingRow] = []

        for t_now, group_iter in itertools.groupby(parsed_lines, key=lambda item: item[0]):
            group = list(group_iter)
            non_ball = [item for item in group if item[2] != T.VISION_BALL]
            ball_items = [item for item in group if item[2] == T.VISION_BALL]

            # Update context messages received at t_now before evaluating ball samples at t_now.
            for _, _, topic, msg in non_ball:
                if self._is_replay_message(msg):
                    stats.excluded["replay"] += 1
                    continue
                if not self._validate_topic_message(topic, msg):
                    stats.excluded["invalid_message"] += 1
                    continue
                if topic in _SNAPSHOT_TOPICS and isinstance(msg, dict):
                    snapshots[topic] = (t_now, copy.deepcopy(msg))

            for _, _, _, ball_msg in ball_items:
                if self._is_replay_message(ball_msg):
                    stats.excluded["replay"] += 1
                    continue
                if not self._validate_topic_message(T.VISION_BALL, ball_msg) or not isinstance(
                    ball_msg, dict
                ):
                    stats.excluded["invalid_message"] += 1
                    continue

                stats.ball_samples += 1
                row, reason = self._build_row(t_now, ball_msg, snapshots, header)
                if row is None:
                    assert reason is not None
                    stats.excluded[reason] += 1
                    continue

                all_rows.append(row)
                if row.is_platform_stale:
                    stats.stale_platform_marked += 1
                    stats.excluded["stale_platform_state"] += 1
                else:
                    rows.append(row)
                    stats.kept_rows += 1
                    if row.maze_id not in stats.maze_ids:
                        stats.maze_ids.append(row.maze_id)
                    if row.is_usable_for_imitation:
                        stats.imitation_rows += 1

        loaded = LoadedRecording(
            path=rec_path,
            header=header,
            rows=rows,
            all_rows=all_rows,
            stats=stats,
        )
        self._loaded = loaded
        return loaded

    def training_rows(
        self,
        path: str | Path | LoadedRecording | None = None,
        *,
        include_stale_platform: bool = False,
        for_imitation: bool = False,
    ) -> list[TrainingRow]:
        """Return training rows from a loaded or specified recording."""
        loaded = self._resolve_loaded(path)
        if for_imitation:
            return [row for row in loaded.rows if row.is_usable_for_imitation]
        if include_stale_platform:
            return list(loaded.all_rows)
        return list(loaded.rows)

    def imitation_rows(
        self, path: str | Path | LoadedRecording | None = None
    ) -> list[TrainingRow]:
        """Return only rows usable for imitation learning (fresh platform, active source)."""
        return self.training_rows(path, for_imitation=True)

    def _resolve_loaded(
        self, path: str | Path | LoadedRecording | None
    ) -> LoadedRecording:
        if isinstance(path, LoadedRecording):
            return path
        if path is not None:
            return self.load(path)
        if self._loaded is None:
            raise RuntimeError("No recording loaded yet; call load(path) first")
        return self._loaded

    @staticmethod
    def _is_replay_message(msg: Any) -> bool:
        return isinstance(msg, dict) and msg.get("writer") == "replay"

    def _validate_topic_message(self, topic: str, msg: Any) -> bool:
        if not self.validate_messages:
            return True
        try:
            validate(topic, msg)
        except ValidationError:
            return False
        except KeyError:
            # Ignore unrecognized future topics without discarding the recording line stream.
            return True
        return True

    @staticmethod
    def _build_row(
        t_now: float,
        ball_msg: dict[str, Any],
        snapshots: dict[str, tuple[float, dict[str, Any]]],
        header: dict[str, Any],
    ) -> tuple[TrainingRow | None, str | None]:
        game_snap = snapshots.get(T.GAME_STATE)
        if game_snap is None:
            return None, "missing_game_state"
        t_game, game_msg = game_snap
        game_state_age_ms = (t_now - t_game) * 1000.0
        if game_state_age_ms > T.GAME_STATE_MAX_AGE_MS:
            return None, "stale_game_state"
        if game_msg["state"] != "playing":
            return None, "not_playing"

        active_maze_id = game_msg["maze_id"]
        if active_maze_id is None:
            return None, "missing_maze"

        if not ball_msg["is_visible"]:
            return None, "ball_not_visible"
        if not all(
            _is_finite_number(ball_msg[k])
            for k in ("x_mm", "y_mm", "vx_mm_s", "vy_mm_s")
        ):
            return None, "invalid_ball"

        maze_snap = snapshots.get(T.VISION_MAZE)
        if maze_snap is None:
            return None, "missing_maze"
        dmap_snap = snapshots.get(T.PLAN_DISTANCE_MAP)
        if dmap_snap is None:
            return None, "missing_distance_map"
        route_snap = snapshots.get(T.PLAN_ROUTE)
        if route_snap is None:
            return None, "missing_route"

        t_maze, maze_msg = maze_snap
        t_dmap, dmap_msg = dmap_snap
        t_route, route_msg = route_snap

        if (
            maze_msg["maze_id"] != active_maze_id
            or dmap_msg["maze_id"] != active_maze_id
            or route_msg["maze_id"] != active_maze_id
        ):
            return None, "maze_mismatch"

        if route_msg["status"] != "valid" or not route_msg["target_points_mm"]:
            return None, "invalid_route"
        if route_msg["ball_seq"] > ball_msg["seq"]:
            return None, "route_mismatch"

        route_age_ms = (t_now - t_route) * 1000.0
        if route_age_ms > T.CONTROLLER_INPUT_MAX_AGE_MS:
            return None, "stale_route"

        platform_snap = snapshots.get(T.PLATFORM_STATE)
        if platform_snap is None:
            return None, "missing_platform_state"
        t_platform, platform_msg = platform_snap

        if platform_msg["is_e_stop"] or platform_msg["fault"] != "none":
            return None, "platform_fault_or_estop"
        if not all(
            _is_finite_number(platform_msg[k])
            for k in (
                "tilt_x_deg",
                "tilt_y_deg",
                "applied_tilt_x_deg",
                "applied_tilt_y_deg",
            )
        ):
            return None, "invalid_platform_state"

        platform_age_ms = (t_now - t_platform) * 1000.0
        is_platform_stale = platform_age_ms > T.CONTROLLER_INPUT_MAX_AGE_MS
        source = platform_msg["source"]
        is_usable_for_imitation = (not is_platform_stale) and (
            source in _IMITATION_SOURCES
        )

        row = TrainingRow(
            game_id=game_msg["game_id"] or header["game_id"],
            maze_id=active_maze_id,
            mode=game_msg["mode"],
            ball_seq=ball_msg["seq"],
            route_ball_seq=route_msg["ball_seq"],
            t_recv_s=t_now,
            t_game_state_s=t_game,
            t_platform_state_s=t_platform,
            t_maze_s=t_maze,
            t_distance_map_s=t_dmap,
            t_route_s=t_route,
            x_mm=float(ball_msg["x_mm"]),
            y_mm=float(ball_msg["y_mm"]),
            vx_mm_s=float(ball_msg["vx_mm_s"]),
            vy_mm_s=float(ball_msg["vy_mm_s"]),
            is_predicted=bool(ball_msg["is_predicted"]),
            is_on_exit=bool(ball_msg["is_on_exit"]),
            tilt_x_deg=float(platform_msg["tilt_x_deg"]),
            tilt_y_deg=float(platform_msg["tilt_y_deg"]),
            target_points_mm=[
                [float(pt[0]), float(pt[1])] for pt in route_msg["target_points_mm"]
            ],
            distance_to_exit_cells=route_msg["distance_to_exit_cells"],
            ball_cell=copy.deepcopy(route_msg["ball_cell"]),
            maze_rows=int(maze_msg["rows"]),
            maze_cols=int(maze_msg["cols"]),
            cell_size_mm=float(maze_msg["cell_size_mm"]),
            applied_tilt_x_deg=float(platform_msg["applied_tilt_x_deg"]),
            applied_tilt_y_deg=float(platform_msg["applied_tilt_y_deg"]),
            source=source,
            platform_age_ms=platform_age_ms,
            game_state_age_ms=game_state_age_ms,
            route_age_ms=route_age_ms,
            is_platform_stale=is_platform_stale,
            is_usable_for_imitation=is_usable_for_imitation,
        )
        return row, None
