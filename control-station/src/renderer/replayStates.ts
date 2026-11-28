// The game/state lines of a recording file (IF-09), for ReplayController (#84).
// The replay tool never publishes game/state (GameManager keeps running), so the app reads the
// recorded states from the file and shows the one that matches the replay position.
import { CS_COMMAND, GAME_STATE, Mode, Result, State, VISION_IMAGE } from "@shared/topics";

const HEADER_TYPE = "header";

// The lines the replay tool never publishes (NEVER_REPLAYED in shared/tools/replay/replay.py). The
// position bar starts and ends where the tool's playing does, so this follows the tool's rule.
const NEVER_REPLAYED_TOPICS: readonly string[] = [GAME_STATE, CS_COMMAND, VISION_IMAGE];
const NEVER_REPLAYED_PREFIXES: readonly string[] = ["cs/variables/", "sys/online/"];

export interface RecordedGameState {
    t_recv_s: number; // when the Recorder received it (IF-09); the replay tool keeps these gaps
    state: State;
    mode: Mode;
    elapsed_s: number;
    progress_pct: number;
    result: Result;
}

export interface RecordingStates {
    // t_recv_s of the first and the last line the replay tool plays: the ends of the replay position.
    start_t_recv_s: number;
    end_t_recv_s: number;
    game_states: RecordedGameState[]; // in file order, so t_recv_s only grows
}

interface RecordingLine {
    t_recv_s: number;
    topic: string;
    msg: unknown;
}

function parse_line(text: string): RecordingLine | null {
    try {
        const line = JSON.parse(text) as RecordingLine;
        return typeof line.t_recv_s === "number" && typeof line.topic === "string" && "msg" in line ? line : null;
    } catch {
        return null;
    }
}

function is_replayed(line: RecordingLine): boolean {
    if (NEVER_REPLAYED_TOPICS.includes(line.topic)) return false;
    if (NEVER_REPLAYED_PREFIXES.some((prefix) => line.topic.startsWith(prefix))) return false;
    return typeof line.msg === "object" && line.msg !== null && !Array.isArray(line.msg);
}

function check_header(first_line: string | undefined): void {
    try {
        if (first_line !== undefined && (JSON.parse(first_line) as { type?: unknown }).type === HEADER_TYPE) return;
    } catch {
        // falls through to the error below
    }
    throw new Error("the first line is not a recording header (IF-09)");
}

function to_game_state(line: RecordingLine): RecordedGameState {
    const msg = line.msg as Omit<RecordedGameState, "t_recv_s">;
    return {
        t_recv_s: line.t_recv_s,
        state: msg.state,
        mode: msg.mode,
        elapsed_s: msg.elapsed_s,
        progress_pct: msg.progress_pct,
        result: msg.result,
    };
}

/**
 * The recorded game states and the replay's start and end. Throws for a file the replay tool cannot
 * play: it stops at the first line that is not a recording line (read_jsonl in replay.py), so a
 * started replay would never come online.
 */
export function read_recording_states(text: string): RecordingStates {
    const lines = text.split("\n").filter((line) => line.trim() !== "");
    check_header(lines[0]);
    const parsed = lines.slice(1).map(parse_line);
    const unreadable_lines = parsed.filter((line) => line === null).length;
    if (unreadable_lines > 0) {
        throw new Error(`${unreadable_lines} unreadable lines, so the replay tool cannot play it`);
    }
    const recording_lines = parsed as RecordingLine[];
    const replayed = recording_lines.filter(is_replayed);
    if (replayed.length === 0) throw new Error("the recording has no line the replay tool can play");
    return {
        start_t_recv_s: replayed[0].t_recv_s,
        end_t_recv_s: replayed[replayed.length - 1].t_recv_s,
        game_states: recording_lines.filter((line) => line.topic === GAME_STATE).map(to_game_state),
    };
}

// The last recorded game state received at or before t_recv_s, or null before the first one.
export function game_state_at(game_states: readonly RecordedGameState[], t_recv_s: number): RecordedGameState | null {
    // Binary search: game/state comes at 10 Hz, so a long game has thousands of them.
    let low = 0;
    let high = game_states.length;
    while (low < high) {
        const middle = Math.floor((low + high) / 2);
        if (game_states[middle].t_recv_s <= t_recv_s) low = middle + 1;
        else high = middle;
    }
    return low === 0 ? null : game_states[low - 1];
}
