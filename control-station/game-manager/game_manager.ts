// GameManager (E.5): decides state, mode, progress, finish and warnings and publishes game/state and
// game/warning. The rules are those of section 5 and IF-05 of the Module Design Document.
//
// Time: every handler reads the injected clock once; tick(now_s) gets the time from its caller.
// Message ages are judged from the envelope timestamp_s (IF-03), so tests can run on a fake clock.

import { ageS } from "../../shared/bus/bus";
import {
  GAME_STATE,
  GAME_WARNING,
  MODE_VALUES,
  variablesSpec,
  type Mode,
  type Result,
  type State,
  type WarningKind,
} from "../../shared/topics";
import { make_game_id } from "./game_id";
import {
  BALL_MAX_AGE_MS,
  EDIT_STATE_MAX_AGE_MS,
  GLOVE_STATE_MAX_AGE_MS,
  PLATFORM_STATE_MAX_AGE_MS,
  ROUTE_MAX_AGE_MS,
} from "./game_limits";
import type {
  BallMsg,
  Cell,
  CommandMsg,
  DistanceMapMsg,
  Envelope,
  EditStateMsg,
  GameStateFields,
  GameStateMsg,
  GameWarningFields,
  GloveStateMsg,
  MazeMsg,
  PlatformStateMsg,
  RouteMsg,
  VariablesMsg,
} from "./game_messages";
import {
  apply_variable_changes,
  build_variables_spec,
  default_game_variables,
  type GameVariables,
} from "./game_variables";
import { distance_mm, warning_intensity_pct, type PointMm } from "./warning_rules";

const MS_PER_S = 1000;
const FULL_PROGRESS_PCT = 100;
const VISION_PROGRAM = "vision";
const REPLAY_WRITER = "replay";
const UNREACHABLE_STEPS = -1;

/** Anything with the bus helper's publish(topic, fields); the Bus class fits, and so does a test double. */
export interface GamePublisher {
  publish(topic: string, fields: Record<string, unknown>): unknown;
}

export type Clock = () => number;

interface StillWindow extends PointMm {
  since_s: number;
}

export class GameManager {
  private state: State = "setup";
  private mode: Mode = MODE_VALUES[0];
  private game_id: string | null = null;
  private maze_id: string | null = null;
  private result: Result = "none";

  private elapsed_before_s = 0;
  private playing_since_s: number | null = null;
  private cell: Cell | null = null;
  private distance_to_exit_cells: number | null = null;
  private progress_pct = 0;
  private start_distance_cells: number | null = null;
  private best_distance_cells: number | null = null;

  private variables: GameVariables = default_game_variables();
  // exit_hold_frames and time_limit_s are "next" variables (E.7): fixed for the game when it starts.
  private game_exit_hold_frames = this.variables.exit_hold_frames;
  private game_time_limit_s = this.variables.time_limit_s;
  private has_published_spec = false;

  private ball: BallMsg | null = null;
  private maze: MazeMsg | null = null;
  private distance_map: DistanceMapMsg | null = null;
  private route: RouteMsg | null = null;
  private edit_state: EditStateMsg | null = null;
  private platform: PlatformStateMsg | null = null;
  private glove: GloveStateMsg | null = null;
  private is_vision_online = false;

  private exit_frames = 0;
  private last_ball_visible_s: number | null = null;
  private last_glove_connected_s: number | null = null;
  private mode_button_baseline: number | null = null;
  private read_maze_requested_s: number | null = null;
  private clear_e_stop_requested_s: number | null = null;

  private still_window: StillWindow | null = null;
  private away_since_s: number | null = null;
  private last_warning_s: Record<WarningKind, number | null> = { not_moving: null, away_from_exit: null };

  constructor(
    private readonly publisher: GamePublisher,
    private readonly clock: Clock,
    previous_state: GameStateMsg | null = null,
  ) {
    if (previous_state) this.restore_after_restart(previous_state);
  }

  // ------------------------------------------------------------------ public interface (E.5)

  on_command(msg: CommandMsg): void {
    if (is_replay(msg)) return;
    const now_s = this.clock();
    switch (msg.cmd) {
      case "start":
        return this.handle_start(now_s);
      case "pause":
        return this.handle_pause(now_s);
      case "resume":
        return this.handle_resume(now_s);
      case "stop":
        return this.handle_stop(now_s);
      case "new_game":
        return this.handle_new_game(now_s);
      case "set_mode":
        return this.handle_set_mode(msg.mode, now_s);
      case "e_stop":
        return this.enter_e_stop(now_s);
      case "clear_e_stop":
        return this.handle_clear_e_stop(msg.timestamp_s, now_s);
      case "read_maze":
        return this.handle_read_maze(msg.timestamp_s, now_s);
      default:
        // calibrate_camera, calibrate_glove and the replay commands are acted on by other programs (IF-07).
        return;
    }
  }

  on_ball(msg: BallMsg): void {
    if (is_replay(msg)) return;
    const now_s = this.clock();
    this.ball = msg;
    if (msg.is_visible) this.last_ball_visible_s = msg.timestamp_s;
    if (this.state === "playing") this.count_exit_frame(msg, now_s);
    this.update(now_s);
  }

  on_maze(msg: MazeMsg): void {
    if (is_replay(msg)) return;
    const now_s = this.clock();
    this.maze = msg;
    if (this.read_maze_requested_s !== null && msg.timestamp_s >= this.read_maze_requested_s) {
      this.read_maze_requested_s = null;
    }
    if (msg.maze_id !== this.maze_id) this.change_maze(msg.maze_id, now_s);
    this.update(now_s);
  }

  /**
   * ASSUMPTION: not in the E.5 method list, but setup → ready needs plan/distance_map (section 5.2),
   * so GameManager also reads it.
   */
  on_distance_map(msg: DistanceMapMsg): void {
    if (is_replay(msg)) return;
    this.distance_map = msg;
    this.update(this.clock());
  }

  on_route(msg: RouteMsg): void {
    if (is_replay(msg)) return;
    this.route = msg;
    this.update(this.clock());
  }

  on_edit_state(msg: EditStateMsg): void {
    if (is_replay(msg)) return;
    this.edit_state = msg;
    this.update(this.clock());
  }

  on_platform_state(msg: PlatformStateMsg): void {
    if (is_replay(msg)) return;
    const now_s = this.clock();
    this.platform = msg;
    if (msg.is_e_stop) this.enter_e_stop(now_s);
    else this.try_clear_e_stop(now_s);
    this.count_mode_button(msg, now_s);
    this.update(now_s);
  }

  on_glove_state(msg: GloveStateMsg): void {
    if (is_replay(msg)) return;
    this.glove = msg;
    if (msg.is_connected) this.last_glove_connected_s = msg.timestamp_s;
    this.update(this.clock());
  }

  /**
   * ASSUMPTION: not in the E.5 method list, but start and resume need sys/online/vision = true (section 5.3).
   * Same signature as TopicHealthMonitor.on_online.
   */
  on_online(program: string, is_online: boolean): void {
    if (program !== VISION_PROGRAM) return;
    this.is_vision_online = is_online;
    this.update(this.clock());
  }

  /**
   * ASSUMPTION: not in the E.5 method list; E.6 says GameManager publishes game/variables_spec,
   * so it also reads cs/variables/game, clamps the values and reports them back (IF-07).
   */
  on_variables(msg: VariablesMsg): void {
    if (is_replay(msg)) return;
    this.variables = apply_variable_changes(this.variables, msg);
    this.publish_variables_spec();
  }

  /** Called at 10 Hz: time-based rules, then the heartbeat. */
  tick(now_s: number): void {
    if (!this.has_published_spec) this.publish_variables_spec();
    this.update(now_s);
    this.publish_state(now_s);
  }

  // ------------------------------------------------------------------ commands

  private handle_start(now_s: number): void {
    if (this.state !== "ready") return this.refuse("start", `not allowed in ${this.state}`);
    const blockers = this.start_blockers(now_s);
    if (blockers.length > 0) return this.refuse("start", blockers.join("; "));
    this.start_game(now_s);
  }

  private handle_pause(now_s: number): void {
    if (this.state !== "playing") return this.refuse("pause", `not allowed in ${this.state}`);
    this.pause(now_s, "operator pause");
  }

  private handle_resume(now_s: number): void {
    if (this.state !== "paused") return this.refuse("resume", `not allowed in ${this.state}`);
    const blockers = this.resume_blockers(now_s);
    if (blockers.length > 0) return this.refuse("resume", blockers.join("; "));
    this.continue_game(now_s);
  }

  private handle_stop(now_s: number): void {
    if (this.state !== "playing" && this.state !== "paused") {
      return this.refuse("stop", `not allowed in ${this.state}`);
    }
    this.finish(now_s, "stopped");
  }

  private handle_new_game(now_s: number): void {
    if (this.state !== "finished") return this.refuse("new_game", `not allowed in ${this.state}`);
    this.enter_ready(now_s);
  }

  private handle_set_mode(mode: Mode | null, now_s: number): void {
    if (!this.can_change_mode()) return this.refuse("set_mode", `not allowed in ${this.state}`);
    if (mode === null) return this.refuse("set_mode", "no mode given");
    this.change_mode(mode, now_s);
  }

  private handle_clear_e_stop(command_time_s: number, now_s: number): void {
    if (this.state !== "e_stop") return this.refuse("clear_e_stop", `not allowed in ${this.state}`);
    this.clear_e_stop_requested_s = command_time_s;
    this.try_clear_e_stop(now_s);
  }

  /**
   * read_maze is acted on by Vision; GameManager only leaves ready (section 5.2). ASSUMPTION: after a read_maze
   * in setup or ready, the maze already known no longer counts: setup waits for a vision/maze published after
   * the command, otherwise it would go straight back to ready with the old scan.
   */
  private handle_read_maze(command_time_s: number, now_s: number): void {
    if (this.state !== "setup" && this.state !== "ready") return;
    this.read_maze_requested_s = command_time_s;
    this.set_state("setup", now_s);
  }

  // ------------------------------------------------------------------ transitions

  private enter_ready(now_s: number): void {
    this.game_id = make_game_id(now_s);
    this.result = "none";
    this.elapsed_before_s = 0;
    this.playing_since_s = null;
    this.progress_pct = 0;
    this.start_distance_cells = null;
    this.best_distance_cells = null;
    this.set_state("ready", now_s);
  }

  private start_game(now_s: number): void {
    this.game_exit_hold_frames = this.variables.exit_hold_frames;
    this.game_time_limit_s = this.variables.time_limit_s;
    this.last_warning_s = { not_moving: null, away_from_exit: null };
    this.continue_game(now_s);
  }

  /** Enter playing from ready (start) or paused (resume). */
  private continue_game(now_s: number): void {
    this.playing_since_s = now_s;
    this.reset_warning_windows();
    this.set_state("playing", now_s);
  }

  private pause(now_s: number, reason: string): void {
    this.stop_clock(now_s);
    console.info(`game_manager: paused: ${reason}`);
    this.set_state("paused", now_s);
  }

  private finish(now_s: number, result: Result): void {
    this.stop_clock(now_s);
    this.result = result;
    this.set_state("finished", now_s);
  }

  private enter_e_stop(now_s: number): void {
    if (this.state === "e_stop") return;
    if (this.is_game_running()) this.result = "aborted";
    this.stop_clock(now_s);
    this.clear_e_stop_requested_s = null;
    this.set_state("e_stop", now_s);
  }

  /** e_stop → setup once a platform/state newer than clear_e_stop shows is_e_stop = false (section 5.2). */
  private try_clear_e_stop(now_s: number): void {
    const requested_s = this.clear_e_stop_requested_s;
    if (this.state !== "e_stop" || requested_s === null || this.platform === null) return;
    if (this.platform.timestamp_s <= requested_s || this.platform.is_e_stop) return;
    this.clear_e_stop_requested_s = null;
    this.result = "none";
    this.set_state("setup", now_s);
  }

  private change_maze(maze_id: string, now_s: number): void {
    const had_maze = this.maze_id !== null;
    this.maze_id = maze_id;
    // Section 5.5 / IF-04: after a maze change the progress baseline and the exit counter start again.
    this.start_distance_cells = null;
    this.best_distance_cells = null;
    this.exit_frames = 0;
    // Section 5.2: a new maze_id in ready is handled like read_maze: ready → setup → ready with a new game_id.
    if (this.state === "ready" && had_maze) this.set_state("setup", now_s);
    // ASSUMPTION: a new maze while playing cannot come without a hand in the playfield; pause to be safe.
    if (this.state === "playing") this.pause(now_s, "maze changed during play");
  }

  private change_mode(mode: Mode, now_s: number): void {
    if (mode === this.mode) return;
    this.mode = mode;
    this.publish_state(now_s);
  }

  private set_state(next: State, now_s: number): void {
    if (next === this.state) return;
    console.info(`game_manager: ${this.state} -> ${next}`);
    this.state = next;
    this.exit_frames = 0;
    this.publish_state(now_s);
  }

  private refuse(cmd: string, reason: string): void {
    console.info(`game_manager: ${cmd} refused: ${reason}`);
  }

  // ------------------------------------------------------------------ rules run on every message and tick

  private update(now_s: number): void {
    this.refresh_ball_cell(now_s);
    if (this.state === "setup") this.try_enter_ready(now_s);
    if (this.state === "playing") this.check_playing(now_s);
  }

  private try_enter_ready(now_s: number): void {
    if (this.read_maze_requested_s !== null) return;
    if (this.is_maze_ready()) this.enter_ready(now_s);
  }

  private check_playing(now_s: number): void {
    const reason = this.pause_reason(now_s);
    if (reason !== null) return this.pause(now_s, reason);
    if (this.is_time_up(now_s)) return this.finish(now_s, "timeout");
    this.update_progress();
    this.check_warnings(now_s);
  }

  /** Section 5.2, playing → paused. Returns null while the game may go on. */
  private pause_reason(now_s: number): string | null {
    if (!this.is_edit_state_clear(now_s)) return "playfield not clear or edit_state stale";
    if (this.is_ball_lost(now_s)) return "ball lost";
    if (!this.is_fresh(this.platform, PLATFORM_STATE_MAX_AGE_MS, now_s)) return "platform/state lost";
    if (this.platform!.fault !== "none") return `platform fault ${this.platform!.fault}`;
    if (this.mode === "glove" && this.is_glove_lost(now_s)) return "glove lost";
    return null;
  }

  /** Section 5.3 resume rule. Each entry is one missing condition, for the log. */
  private resume_blockers(now_s: number): string[] {
    const blockers: string[] = [];
    if (!this.is_playfield_clear(now_s)) blockers.push("playfield not clear");
    if (!this.is_ball_fresh_and_visible(now_s)) blockers.push("ball not visible");
    if (!this.is_platform_ok(now_s)) blockers.push("platform/state stale, faulted or in e-stop");
    if (!this.has_valid_route(now_s)) blockers.push("no fresh valid route for the current maze");
    if (this.mode === "glove" && !this.is_glove_connected(now_s)) blockers.push("glove not connected");
    return blockers;
  }

  /**
   * Section 5.2 start: ball in the start cell, playfield clear, glove connected in glove mode.
   * ASSUMPTION: start also needs the other resume conditions (fresh ball, platform and route), because a game
   * started without them would pause at once, and IF-04 says a missing route blocks start.
   */
  private start_blockers(now_s: number): string[] {
    const blockers = this.resume_blockers(now_s);
    if (!this.is_ball_in_start_cell()) blockers.push("ball not in the start cell");
    return blockers;
  }

  // ------------------------------------------------------------------ conditions

  private is_maze_ready(): boolean {
    const maze = this.maze;
    const map = this.distance_map;
    if (maze === null || map === null || map.maze_id !== maze.maze_id) return false;
    return has_path_to_exit(maze, map);
  }

  private is_edit_state_clear(now_s: number): boolean {
    if (!this.is_fresh(this.edit_state, EDIT_STATE_MAX_AGE_MS, now_s)) return false;
    return this.edit_state!.state === "clear";
  }

  private is_playfield_clear(now_s: number): boolean {
    return this.is_edit_state_clear(now_s) && this.is_vision_online;
  }

  private is_ball_fresh_and_visible(now_s: number): boolean {
    return this.is_fresh(this.ball, BALL_MAX_AGE_MS, now_s) && this.ball!.is_visible;
  }

  /** IF-05: lost longer than ball_lost_pause_s; no vision/ball message at all counts as lost. */
  private is_ball_lost(now_s: number): boolean {
    if (this.last_ball_visible_s === null) return true;
    return now_s - this.last_ball_visible_s >= this.variables.ball_lost_pause_s;
  }

  private is_platform_ok(now_s: number): boolean {
    if (!this.is_fresh(this.platform, PLATFORM_STATE_MAX_AGE_MS, now_s)) return false;
    return this.platform!.fault === "none" && !this.platform!.is_e_stop;
  }

  private has_valid_route(now_s: number): boolean {
    const route = this.route;
    if (!this.is_fresh(route, ROUTE_MAX_AGE_MS, now_s) || route!.status !== "valid") return false;
    const maze_id = this.maze?.maze_id;
    return route!.maze_id === maze_id && this.distance_map?.maze_id === maze_id;
  }

  /**
   * ASSUMPTION: glove/state is_connected (on_glove_state) decides, not platform/state is_glove_connected;
   * both carry the same 300 ms rule from the bridge.
   */
  private is_glove_connected(now_s: number): boolean {
    return this.is_fresh(this.glove, GLOVE_STATE_MAX_AGE_MS, now_s) && this.glove!.is_connected;
  }

  private is_glove_lost(now_s: number): boolean {
    if (this.last_glove_connected_s === null) return true;
    return now_s - this.last_glove_connected_s >= this.variables.glove_lost_pause_s;
  }

  /** IF-04: if start_cell is null, the ball may start in any cell. */
  private is_ball_in_start_cell(): boolean {
    const start = this.maze?.start_cell ?? null;
    if (this.cell === null) return false;
    return start === null || same_cell(start, this.cell);
  }

  private is_time_up(now_s: number): boolean {
    return this.game_time_limit_s > 0 && this.elapsed_s(now_s) >= this.game_time_limit_s;
  }

  private is_game_running(): boolean {
    return this.state === "playing" || this.state === "paused";
  }

  private can_change_mode(): boolean {
    return this.state === "setup" || this.state === "ready";
  }

  private is_fresh(msg: Envelope | null, max_age_ms: number, now_s: number): boolean {
    if (msg === null) return false;
    return ageS(msg as unknown as Record<string, unknown>, now_s) * MS_PER_S <= max_age_ms;
  }

  // ------------------------------------------------------------------ finish, progress, mode button

  /** IF-05: counted on every vision/ball message in playing; a false frame resets the count. */
  private count_exit_frame(msg: BallMsg, now_s: number): void {
    this.exit_frames = msg.is_on_exit ? this.exit_frames + 1 : 0;
    if (this.exit_frames >= this.game_exit_hold_frames) this.finish(now_s, "completed");
  }

  /**
   * game/state cell and distance_to_exit_cells. ASSUMPTION: both are taken from the latest plan/route
   * (Vision's ball_cell and distance) when it is fresh, matches the active maze and the ball is visible;
   * otherwise they are null (unknown). GameManager does not compute cells itself.
   */
  private refresh_ball_cell(now_s: number): void {
    const route = this.route;
    const is_usable =
      this.is_fresh(route, ROUTE_MAX_AGE_MS, now_s) &&
      route!.maze_id === this.maze_id &&
      this.is_ball_fresh_and_visible(now_s);
    this.cell = is_usable ? route!.ball_cell : null;
    this.distance_to_exit_cells = is_usable ? route!.distance_to_exit_cells : null;
  }

  /** progress_pct = 100 × (1 − distance now / distance at start), clamped; frozen while the distance is unknown. */
  private update_progress(): void {
    const distance = this.distance_to_exit_cells;
    if (distance === null) return;
    this.start_distance_cells ??= distance;
    if (this.start_distance_cells <= 0) return;
    const pct = FULL_PROGRESS_PCT * (1 - distance / this.start_distance_cells);
    this.progress_pct = Math.min(FULL_PROGRESS_PCT, Math.max(0, pct));
  }

  /**
   * IF-05 mode button: the first value sets the baseline; a higher value in setup / ready with fresh
   * platform/state moves the mode forward once per press; a lower value is an ESP32 restart.
   */
  private count_mode_button(msg: PlatformStateMsg, now_s: number): void {
    const baseline = this.mode_button_baseline;
    const presses = msg.mode_button_presses;
    this.mode_button_baseline = presses;
    if (baseline === null || presses <= baseline) return;
    if (!this.can_change_mode() || !this.is_fresh(msg, PLATFORM_STATE_MAX_AGE_MS, now_s)) return;
    this.change_mode(next_mode(this.mode, presses - baseline), now_s);
  }

  // ------------------------------------------------------------------ warnings (IF-05, only in playing)

  private check_warnings(now_s: number): void {
    // IF-04 vision/ball reader table: while the ball data is missing, warnings pause.
    if (!this.is_ball_fresh_and_visible(now_s)) return this.reset_warning_windows();
    this.check_not_moving(now_s);
    this.check_away_from_exit(now_s);
  }

  /** not_moving: the ball stays within not_moving_radius_mm of the window start for not_moving_time_s. */
  private check_not_moving(now_s: number): void {
    const ball = this.ball!;
    const window = this.still_window;
    if (window === null || distance_mm(window, ball) > this.variables.not_moving_radius_mm) {
      this.still_window = { x_mm: ball.x_mm, y_mm: ball.y_mm, since_s: now_s };
      return;
    }
    this.warn_if_held("not_moving", now_s - window.since_s, this.variables.not_moving_time_s, now_s);
  }

  /** away_from_exit: the distance stays larger than the best of this game for away_hold_time_s. */
  private check_away_from_exit(now_s: number): void {
    const distance = this.distance_to_exit_cells;
    if (distance === null) {
      this.away_since_s = null;
      return;
    }
    if (this.best_distance_cells === null || distance <= this.best_distance_cells) {
      this.best_distance_cells = distance;
      this.away_since_s = null;
      return;
    }
    this.away_since_s ??= now_s;
    this.warn_if_held("away_from_exit", now_s - this.away_since_s, this.variables.away_hold_time_s, now_s);
  }

  /** Publishes the warning once the threshold is passed, at most every warning_cooldown_s per kind. */
  private warn_if_held(kind: WarningKind, held_s: number, threshold_s: number, now_s: number): void {
    if (held_s < threshold_s) return;
    const last_s = this.last_warning_s[kind];
    if (last_s !== null && now_s - last_s < this.variables.warning_cooldown_s) return;
    this.last_warning_s[kind] = now_s;
    const fields: GameWarningFields = { kind, intensity_pct: warning_intensity_pct(held_s - threshold_s, threshold_s) };
    this.publisher.publish(GAME_WARNING, { ...fields });
  }

  /**
   * ASSUMPTION: "time and warnings are frozen" in paused is read as: the still and away windows start
   * again when play continues, so no warning fires right after resume.
   */
  private reset_warning_windows(): void {
    this.still_window = null;
    this.away_since_s = null;
  }

  // ------------------------------------------------------------------ time and publishing

  private elapsed_s(now_s: number): number {
    const running_s = this.playing_since_s === null ? 0 : Math.max(0, now_s - this.playing_since_s);
    return this.elapsed_before_s + running_s;
  }

  private stop_clock(now_s: number): void {
    this.elapsed_before_s = this.elapsed_s(now_s);
    this.playing_since_s = null;
  }

  private build_state_fields(now_s: number): GameStateFields {
    return {
      state: this.state,
      mode: this.mode,
      game_id: this.game_id,
      maze_id: this.maze_id,
      elapsed_s: this.elapsed_s(now_s),
      cell: this.cell,
      distance_to_exit_cells: this.distance_to_exit_cells,
      progress_pct: this.progress_pct,
      result: this.result,
    };
  }

  private publish_state(now_s: number): void {
    this.publisher.publish(GAME_STATE, { ...this.build_state_fields(now_s) });
  }

  private publish_variables_spec(): void {
    this.has_published_spec = true;
    this.publisher.publish(variablesSpec("game"), build_variables_spec(this.variables));
  }

  /**
   * Section 5.4: after a restart the retained playing is not trusted; the old game becomes aborted and
   * GameManager starts in setup. ASSUMPTION: the mode of the previous run is kept, and the old game_id stays
   * in game/state with result = aborted until the next game enters ready.
   */
  private restore_after_restart(previous: GameStateMsg): void {
    this.mode = previous.mode;
    this.game_id = previous.game_id;
    if (previous.state === "playing" || previous.state === "paused") this.result = "aborted";
  }
}

// ------------------------------------------------------------------ helpers

function is_replay(msg: Envelope): boolean {
  return msg.writer === REPLAY_WRITER;
}

function same_cell(a: Cell, b: Cell): boolean {
  return a.row === b.row && a.col === b.col;
}

/** D5 mode order: glove → ai → simple → glove (the order of MODE_VALUES). */
function next_mode(mode: Mode, presses: number): Mode {
  const index = MODE_VALUES.indexOf(mode);
  return MODE_VALUES[(index + presses) % MODE_VALUES.length];
}

/**
 * Section 5.2 "a path to the exit exists". ASSUMPTION: with a start cell, its distance must be reachable;
 * without one (start_cell = null), at least one cell other than the exit must reach the exit.
 */
function has_path_to_exit(maze: MazeMsg, map: DistanceMapMsg): boolean {
  const start = maze.start_cell;
  if (start !== null) return (map.steps[start.row]?.[start.col] ?? UNREACHABLE_STEPS) > UNREACHABLE_STEPS;
  return map.steps.some((row) => row.some((steps) => steps > 0));
}
