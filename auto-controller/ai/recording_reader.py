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

_MS_PER_S = 1000.0
_IMITATION_SOURCES = frozenset({"glove", "ai", "simple"})
_COMMAND_TOPICS = frozenset({T.AI_TARGET_TILT, T.CONTROL_TARGET_TILT})
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

    # Provenance & timestamps (Recorder clock t_recv_s)
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

    # Episode boundary and prior command fields for ObservationBuilder previous_action
    prev_command_x_deg: float | None
    prev_command_y_deg: float | None
    is_episode_start: bool

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


@dataclass
class _EpisodeTracker:
    """Tracks episode discontinuities and the latest valid controller tilt command."""

    episode_broken: bool = True
    last_episode_key: tuple[str, str, str] | None = None
    last_command: tuple[str, float, float] | None = None


class RecordingReader:
    """Reads IF-09 JSONL recordings and joins valid samples without future or cross-maze leakage."""

    def __init__(self, validate_messages: bool = True) -> None:
        self.validate_messages = validate_messages
        self._loaded: LoadedRecording | None = None

    def load(self, path: str | Path) -> LoadedRecording:
        """Load and parse an IF-09 JSONL recording file into causal TrainingRows."""
        rec_path = Path(path)
        header, body_lines = self._read_header(rec_path)
        stats = RecordingStats(total_lines=len(body_lines))
        clean_lines = self._parse_and_validate_lines(body_lines, stats)
        routes_by_ball_seq = self._index_routes(clean_lines)

        snapshots: dict[str, tuple[float, dict[str, Any]]] = {}
        tracker = _EpisodeTracker()
        rows: list[TrainingRow] = []
        all_rows: list[TrainingRow] = []

        for t_now, group_iter in itertools.groupby(clean_lines, key=lambda item: item[0]):
            group = list(group_iter)
            self._update_snapshots(t_now, group, snapshots, tracker)
            self._process_ball_group(
                t_now, group, snapshots, routes_by_ball_seq, header, tracker, rows, all_rows, stats
            )
            self._update_last_command(group, tracker)

        loaded = LoadedRecording(
            path=rec_path, header=header, rows=rows, all_rows=all_rows, stats=stats
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

    def _process_ball_group(
        self,
        t_now: float,
        group: list[tuple[float, int, str, Any]],
        snapshots: dict[str, tuple[float, dict[str, Any]]],
        routes_by_ball_seq: dict[int, list[tuple[float, dict[str, Any]]]],
        header: dict[str, Any],
        tracker: _EpisodeTracker,
        rows: list[TrainingRow],
        all_rows: list[TrainingRow],
        stats: RecordingStats,
    ) -> None:
        for _, _, topic, ball_msg in group:
            if topic != T.VISION_BALL:
                continue
            stats.ball_samples += 1
            row, reason = self._build_row(
                t_now, ball_msg, snapshots, routes_by_ball_seq, header, tracker
            )
            if row is None:
                assert reason is not None
                stats.excluded[reason] += 1
                continue
            self._record_row(row, rows, all_rows, stats, tracker)

    @staticmethod
    def _read_header(rec_path: Path) -> tuple[dict[str, Any], list[str]]:
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
        return header, raw_lines[1:]

    def _parse_and_validate_lines(
        self, body_lines: list[str], stats: RecordingStats
    ) -> list[tuple[float, int, str, Any]]:
        clean_lines: list[tuple[float, int, str, Any]] = []
        for line_no, raw in enumerate(body_lines, start=2):
            try:
                entry = json.loads(raw)
                validate_file("recording_line", entry)
            except (json.JSONDecodeError, ValidationError):
                stats.excluded["invalid_message"] += 1
                continue
            t_recv_s, topic, msg = entry["t_recv_s"], entry["topic"], entry["msg"]
            if not _is_finite_number(t_recv_s):
                stats.excluded["invalid_message"] += 1
                continue
            if self._is_replay_message(msg):
                stats.excluded["replay"] += 1
                continue
            if not self._validate_topic_message(topic, msg) or (
                topic == T.VISION_BALL and not isinstance(msg, dict)
            ):
                stats.excluded["invalid_message"] += 1
                continue
            clean_lines.append((float(t_recv_s), line_no, topic, msg))
        # Sort strictly by Recorder clock (t_recv_s) to prevent future context leakage.
        clean_lines.sort(key=lambda item: (item[0], item[1]))
        return clean_lines

    @staticmethod
    def _index_routes(
        clean_lines: list[tuple[float, int, str, Any]],
    ) -> dict[int, list[tuple[float, dict[str, Any]]]]:
        routes_by_ball_seq: dict[int, list[tuple[float, dict[str, Any]]]] = {}
        for t_recv_s, _, topic, msg in clean_lines:
            if topic == T.PLAN_ROUTE and isinstance(msg, dict):
                ball_seq = int(msg["ball_seq"])
                routes_by_ball_seq.setdefault(ball_seq, []).append(
                    (t_recv_s, copy.deepcopy(msg))
                )
        return routes_by_ball_seq

    @staticmethod
    def _update_snapshots(
        t_now: float,
        group: list[tuple[float, int, str, Any]],
        snapshots: dict[str, tuple[float, dict[str, Any]]],
        tracker: _EpisodeTracker,
    ) -> None:
        for _, _, topic, msg in group:
            if topic == T.VISION_BALL or topic not in _SNAPSHOT_TOPICS or not isinstance(msg, dict):
                continue
            if topic == T.GAME_STATE and msg.get("state") != "playing":
                tracker.episode_broken = True
                tracker.last_command = None
            elif topic == T.PLATFORM_STATE and (msg.get("is_e_stop") or msg.get("fault") != "none"):
                tracker.episode_broken = True
                tracker.last_command = None
            elif topic == T.VISION_MAZE:
                prev_maze = snapshots.get(T.VISION_MAZE)
                if prev_maze is not None and prev_maze[1].get("maze_id") != msg.get("maze_id"):
                    tracker.episode_broken = True
                    tracker.last_command = None
            snapshots[topic] = (t_now, copy.deepcopy(msg))

    @staticmethod
    def _update_last_command(
        group: list[tuple[float, int, str, Any]], tracker: _EpisodeTracker
    ) -> None:
        for _, _, topic, msg in group:
            if topic not in _COMMAND_TOPICS or not isinstance(msg, dict):
                continue
            tilt_x = msg.get("target_tilt_x_deg")
            tilt_y = msg.get("target_tilt_y_deg")
            maze_id = msg.get("maze_id")
            if _is_finite_number(tilt_x) and _is_finite_number(tilt_y) and isinstance(maze_id, str):
                tracker.last_command = (maze_id, float(tilt_x), float(tilt_y))

    @staticmethod
    def _record_row(
        row: TrainingRow,
        rows: list[TrainingRow],
        all_rows: list[TrainingRow],
        stats: RecordingStats,
        tracker: _EpisodeTracker,
    ) -> None:
        all_rows.append(row)
        if row.is_platform_stale:
            stats.stale_platform_marked += 1
            stats.excluded["stale_platform_state"] += 1
            return
        rows.append(row)
        stats.kept_rows += 1
        tracker.episode_broken = False
        tracker.last_episode_key = (row.game_id, row.maze_id, row.mode)
        if row.maze_id not in stats.maze_ids:
            stats.maze_ids.append(row.maze_id)
        if row.is_usable_for_imitation:
            stats.imitation_rows += 1

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
            # Ignore unrecognized future topics without discarding the recording stream.
            return True
        return True

    @classmethod
    def _build_row(
        cls,
        t_now: float,
        ball_msg: dict[str, Any],
        snapshots: dict[str, tuple[float, dict[str, Any]]],
        routes_by_ball_seq: dict[int, list[tuple[float, dict[str, Any]]]],
        header: dict[str, Any],
        tracker: _EpisodeTracker,
    ) -> tuple[TrainingRow | None, str | None]:
        game_ctx, reason = cls._check_game_state(t_now, snapshots)
        if reason is not None:
            return None, reason
        assert game_ctx is not None
        t_game, game_msg, game_state_age_ms = game_ctx

        ball_err = cls._check_ball(ball_msg)
        if ball_err is not None:
            return None, ball_err

        plan_ctx, reason = cls._check_planning(
            t_now, ball_msg, game_msg["maze_id"], snapshots, routes_by_ball_seq
        )
        if reason is not None:
            return None, reason
        assert plan_ctx is not None

        plat_ctx, reason = cls._check_platform(t_now, snapshots)
        if reason is not None:
            return None, reason
        assert plat_ctx is not None

        return cls._make_training_row(
            t_now, ball_msg, t_game, game_msg, game_state_age_ms, plan_ctx, plat_ctx, header, tracker
        ), None

    @staticmethod
    def _check_game_state(
        t_now: float, snapshots: dict[str, tuple[float, dict[str, Any]]]
    ) -> tuple[tuple[float, dict[str, Any], float] | None, str | None]:
        game_snap = snapshots.get(T.GAME_STATE)
        if game_snap is None:
            return None, "missing_game_state"
        t_game, game_msg = game_snap
        game_state_age_ms = (t_now - t_game) * _MS_PER_S
        if game_state_age_ms > T.GAME_STATE_MAX_AGE_MS:
            return None, "stale_game_state"
        if game_msg["state"] != "playing":
            return None, "not_playing"
        if game_msg["maze_id"] is None:
            return None, "missing_maze"
        return (t_game, game_msg, game_state_age_ms), None

    @staticmethod
    def _check_ball(ball_msg: dict[str, Any]) -> str | None:
        if not ball_msg["is_visible"]:
            return "ball_not_visible"
        if not all(_is_finite_number(ball_msg[k]) for k in ("x_mm", "y_mm", "vx_mm_s", "vy_mm_s")):
            return "invalid_ball"
        return None

    @staticmethod
    def _check_planning(
        t_now: float,
        ball_msg: dict[str, Any],
        active_maze_id: str,
        snapshots: dict[str, tuple[float, dict[str, Any]]],
        routes_by_ball_seq: dict[int, list[tuple[float, dict[str, Any]]]],
    ) -> tuple[
        tuple[float, dict[str, Any], float, dict[str, Any], float, dict[str, Any], float] | None,
        str | None,
    ]:
        maze_snap = snapshots.get(T.VISION_MAZE)
        if maze_snap is None:
            return None, "missing_maze"
        dmap_snap = snapshots.get(T.PLAN_DISTANCE_MAP)
        if dmap_snap is None:
            return None, "missing_distance_map"
        t_maze, maze_msg = maze_snap
        t_dmap, dmap_msg = dmap_snap
        if maze_msg["maze_id"] != active_maze_id or dmap_msg["maze_id"] != active_maze_id:
            return None, "maze_mismatch"
        route_pair, reason = RecordingReader._select_route(
            t_now, int(ball_msg["seq"]), active_maze_id, snapshots, routes_by_ball_seq
        )
        if reason is not None:
            return None, reason
        assert route_pair is not None
        t_route, route_msg, route_age_ms = route_pair
        return (t_maze, maze_msg, t_dmap, dmap_msg, t_route, route_msg, route_age_ms), None

    @staticmethod
    def _select_route(
        t_now: float,
        ball_seq: int,
        active_maze_id: str,
        snapshots: dict[str, tuple[float, dict[str, Any]]],
        routes_by_ball_seq: dict[int, list[tuple[float, dict[str, Any]]]],
    ) -> tuple[tuple[float, dict[str, Any], float] | None, str | None]:
        candidates = routes_by_ball_seq.get(ball_seq, [])
        if not candidates:
            latest_route = snapshots.get(T.PLAN_ROUTE)
            if latest_route is None:
                return None, "missing_route"
            if latest_route[1]["maze_id"] != active_maze_id:
                return None, "maze_mismatch"
            return None, "route_mismatch"
        t_route, route_msg = min(candidates, key=lambda item: abs(item[0] - t_now))
        if route_msg["maze_id"] != active_maze_id:
            return None, "maze_mismatch"
        if route_msg["status"] != "valid" or not route_msg["target_points_mm"]:
            return None, "invalid_route"
        route_age_ms = abs(t_route - t_now) * _MS_PER_S
        if route_age_ms > T.CONTROLLER_INPUT_MAX_AGE_MS:
            return None, "stale_route"
        return (t_route, route_msg, route_age_ms), None

    @staticmethod
    def _check_platform(
        t_now: float, snapshots: dict[str, tuple[float, dict[str, Any]]]
    ) -> tuple[tuple[float, dict[str, Any], float] | None, str | None]:
        platform_snap = snapshots.get(T.PLATFORM_STATE)
        if platform_snap is None:
            return None, "missing_platform_state"
        t_platform, platform_msg = platform_snap
        if platform_msg["is_e_stop"] or platform_msg["fault"] != "none":
            return None, "platform_fault_or_estop"
        if not all(
            _is_finite_number(platform_msg[k])
            for k in ("tilt_x_deg", "tilt_y_deg", "applied_tilt_x_deg", "applied_tilt_y_deg")
        ):
            return None, "invalid_platform_state"
        platform_age_ms = (t_now - t_platform) * _MS_PER_S
        return (t_platform, platform_msg, platform_age_ms), None

    @staticmethod
    def _make_training_row(
        t_now: float,
        ball_msg: dict[str, Any],
        t_game: float,
        game_msg: dict[str, Any],
        game_state_age_ms: float,
        plan_ctx: tuple[float, dict[str, Any], float, dict[str, Any], float, dict[str, Any], float],
        plat_ctx: tuple[float, dict[str, Any], float],
        header: dict[str, Any],
        tracker: _EpisodeTracker,
    ) -> TrainingRow:
        t_maze, maze_msg, t_dmap, _, t_route, route_msg, route_age_ms = plan_ctx
        t_platform, platform_msg, platform_age_ms = plat_ctx
        game_id = game_msg["game_id"] or header["game_id"]
        maze_id, mode = game_msg["maze_id"], game_msg["mode"]
        episode_key = (game_id, maze_id, mode)
        is_episode_start = tracker.episode_broken or (
            tracker.last_episode_key is not None and episode_key != tracker.last_episode_key
        )
        prev_cmd_x: float | None = None
        prev_cmd_y: float | None = None
        if not is_episode_start and tracker.last_command is not None and tracker.last_command[0] == maze_id:
            prev_cmd_x, prev_cmd_y = tracker.last_command[1], tracker.last_command[2]

        is_platform_stale = platform_age_ms > T.CONTROLLER_INPUT_MAX_AGE_MS
        source = platform_msg["source"]
        return TrainingRow(
            game_id=game_id, maze_id=maze_id, mode=mode,
            ball_seq=ball_msg["seq"], route_ball_seq=route_msg["ball_seq"],
            t_recv_s=t_now, t_game_state_s=t_game, t_platform_state_s=t_platform,
            t_maze_s=t_maze, t_distance_map_s=t_dmap, t_route_s=t_route,
            x_mm=float(ball_msg["x_mm"]), y_mm=float(ball_msg["y_mm"]),
            vx_mm_s=float(ball_msg["vx_mm_s"]), vy_mm_s=float(ball_msg["vy_mm_s"]),
            is_predicted=bool(ball_msg["is_predicted"]), is_on_exit=bool(ball_msg["is_on_exit"]),
            tilt_x_deg=float(platform_msg["tilt_x_deg"]), tilt_y_deg=float(platform_msg["tilt_y_deg"]),
            target_points_mm=[[float(pt[0]), float(pt[1])] for pt in route_msg["target_points_mm"]],
            distance_to_exit_cells=route_msg["distance_to_exit_cells"],
            ball_cell=copy.deepcopy(route_msg["ball_cell"]),
            maze_rows=int(maze_msg["rows"]), maze_cols=int(maze_msg["cols"]),
            cell_size_mm=float(maze_msg["cell_size_mm"]),
            applied_tilt_x_deg=float(platform_msg["applied_tilt_x_deg"]),
            applied_tilt_y_deg=float(platform_msg["applied_tilt_y_deg"]),
            source=source,
            prev_command_x_deg=prev_cmd_x, prev_command_y_deg=prev_cmd_y,
            is_episode_start=is_episode_start,
            platform_age_ms=platform_age_ms, game_state_age_ms=game_state_age_ms,
            route_age_ms=route_age_ms, is_platform_stale=is_platform_stale,
            is_usable_for_imitation=(not is_platform_stale) and (source in _IMITATION_SOURCES),
        )
