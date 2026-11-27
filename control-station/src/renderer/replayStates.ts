// The game/state lines of a recording file (IF-09), for ReplayController (#84).
// The replay tool never publishes game/state (GameManager keeps running), so the app reads the
// recorded states from the file and shows the one that matches the replay position.
import { GAME_STATE, Mode, Result, State } from "@shared/topics";

const HEADER_TYPE = "header";

export interface RecordedGameState {
    t_recv_s: number; // when the Recorder received it (IF-09); the replay tool keeps these gaps
    state: State;
    mode: Mode;
    elapsed_s: number;
    progress_pct: number;
    result: Result;
}

export interface RecordingStates {
    // t_recv_s of the first line the replay tool plays: the start of the replay position.
    start_t_recv_s: number;
    end_t_recv_s: number; // t_recv_s of the last line
    game_states: RecordedGameState[]; // in file order, so t_recv_s only grows
    unreadable_lines: number; // e.g. a last line cut off when the Recorder stopped
}

interface RecordingLine {
    t_recv_s: number;
    topic: string;
    msg: unknown;
}

function parse_line(text: string): RecordingLine | null {
    try {
        const line = JSON.parse(text) as RecordingLine;
        return typeof line.t_recv_s === "number" && typeof line.topic === "string" ? line : null;
    } catch {
        return null;
    }
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

export function read_recording_states(text: string): RecordingStates {
    const lines = text.split("\n").filter((line) => line.trim() !== "");
    check_header(lines[0]);

    const game_states: RecordedGameState[] = [];
    let start_t_recv_s: number | null = null;
    let end_t_recv_s = 0;
    let unreadable_lines = 0;
    for (const text_line of lines.slice(1)) {
        const line = parse_line(text_line);
        if (line === null) {
            unreadable_lines++;
            continue;
        }
        end_t_recv_s = line.t_recv_s;
        if (line.topic === GAME_STATE) {
            game_states.push(to_game_state(line));
            continue;
        }
        // The replay tool starts its clock at the first line it plays. game/state is never played;
        // the other skipped topics are retained ones that come within milliseconds of the first played line.
        start_t_recv_s ??= line.t_recv_s;
    }
    if (start_t_recv_s === null) throw new Error("the recording has no line the replay tool can play");
    return { start_t_recv_s, end_t_recv_s, game_states, unreadable_lines };
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
