// ReplayController (E.5, #84): the app's replay controls. The shared replay tool plays the file
// (npm run replay); this class sends it the commands through StartTab and shows the replay
// position and the recorded state, time, progress and result in step with it, read from the file.
import { REPLAY_SPEED_VALUES, ReplaySpeed, sysOnline } from "@shared/topics";
import { Callback, Payload } from "@shared/bus/bus";
import { RECORDING_FILES_API_NAME, type RecordingFilesApi } from "../common/recordingFiles";
import { BusClient } from "./busClient";
import { StartTab } from "./startTab";
import { TopBar, format_elapsed } from "./topBar";
import { game_state_at, read_recording_states, type RecordedGameState, type RecordingStates } from "./replayStates";

// game/state is recorded at 10 Hz, so the position and the recorded state are shown as often.
const DISPLAY_INTERVAL_MS = 100;
// The replay tool waits this long after going online before it plays the first line (replay.py, run()).
const REPLAY_TOOL_START_DELAY_MS = 300;
// If the tool is not online this long after Play, it is not running or dropped the command (it plays
// one file at a time); the panel then gives up instead of waiting for ever.
const REPLAY_TOOL_START_TIMEOUT_MS = 5000;
const DEFAULT_SPEED: ReplaySpeed = 1;
const MS_PER_S = 1000;

// starting: replay command sent, waiting for sys/online/replay = true.
type ReplayPhase = "idle" | "starting" | "playing" | "paused";

const TITLE_TEXT = "Replay";
const NO_FILE_TEXT = "No recording selected";
const NO_RECORDINGS_TEXT = "No recordings yet";
const WAITING_TEXT = "Waiting for the replay tool (npm run replay)";
const NOT_STARTED_TEXT = "The replay tool did not start: is npm run replay running?";
const TOOL_BUSY_TEXT = "The replay tool is still playing a replay (Stop ends it)";
const BUS_NOT_CONNECTED_TEXT = "Bus not connected: the replay cannot start";
const NO_GAME_STATE_TEXT = "Recorded game: no game state yet";

declare global {
    interface Window {
        [RECORDING_FILES_API_NAME]: RecordingFilesApi; // given by the preload script
    }
}

function recording_files(): RecordingFilesApi {
    return window[RECORDING_FILES_API_NAME];
}

function error_text(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}

function format_recorded_state(game_state: RecordedGameState): string {
    return `Recorded game: ${game_state.state} · ${game_state.mode} · ${format_elapsed(game_state.elapsed_s)}`
        + ` · progress ${game_state.progress_pct}% · result ${game_state.result}`;
}

function create_element<K extends keyof HTMLElementTagNameMap>(tag: K, class_name: string): HTMLElementTagNameMap[K] {
    const element = document.createElement(tag);
    element.className = class_name;
    return element;
}

export class ReplayController {
    readonly root: HTMLElement = create_element("section", "replay-panel");
    private readonly bus_client: BusClient;
    private readonly start_tab: StartTab;
    private readonly top_bar: TopBar;
    private readonly file_select = create_element("select", "replay-select replay-file-select");
    private readonly speed_select = create_element("select", "replay-select");
    private readonly refresh_button: HTMLButtonElement;
    private readonly play_button: HTMLButtonElement;
    private readonly pause_button: HTMLButtonElement;
    private readonly stop_button: HTMLButtonElement;
    // File info, loading, waiting and errors.
    private readonly message_element = create_element("div", "replay-message");
    private readonly position_row = create_element("div", "replay-position-row");
    private readonly position_bar = create_element("progress", "replay-position-bar");
    private readonly position_text = create_element("span", "replay-position-text");
    private readonly recorded_state_element = create_element("div", "replay-recorded-state");

    private phase: ReplayPhase = "idle";
    private file: string | null = null;
    private recording: RecordingStates | null = null;
    private speed: ReplaySpeed = DEFAULT_SPEED;
    private display_timer: ReturnType<typeof setInterval> | null = null;
    private start_timer: ReturnType<typeof setTimeout> | null = null;
    // sys/online/replay: the tool is online only while it plays a file. A new replay waits until the
    // last one has gone offline, because the tool drops a replay command while it still plays.
    private is_tool_online = false;
    // Stop pressed while starting: the tool reads cs/command only once it is online, so the stop is
    // sent again then.
    private is_stop_pending = false;
    // Replay clock, in performance.now() milliseconds.
    private started_ms = 0;
    private paused_at_ms: number | null = null;
    private paused_total_ms = 0;

    private readonly replay_online_callback: Callback = (_topic: string, msg: Payload) => this.on_replay_online(msg === true);

    constructor(bus_client: BusClient, start_tab: StartTab, top_bar: TopBar) {
        this.bus_client = bus_client;
        this.start_tab = start_tab;
        this.top_bar = top_bar;
        this.refresh_button = this.create_button("Refresh", () => void this.refresh_files());
        this.play_button = this.create_button("Play", () => this.play(this.selected_speed()));
        this.pause_button = this.create_button("Pause", () => this.pause());
        this.stop_button = this.create_button("Stop", () => this.stop());
        this.build_panel();

        this.bus_client.subscribe(sysOnline("replay"), this.replay_online_callback);
        this.show_recording(null);
        void this.refresh_files();
    }

    open(file: string): void {
        this.file = file;
        this.show_recording(null);
        this.message_element.textContent = `Loading ${file} …`;
        void this.load_recording(file);
    }

    // Starts the replay, or continues it after pause(); speed is used only when it starts.
    play(speed: ReplaySpeed): void {
        if (this.phase === "paused") {
            this.start_tab.send_command("replay_resume");
            this.paused_total_ms += performance.now() - this.paused_at_ms!;
            this.paused_at_ms = null;
            this.set_phase("playing");
            return;
        }
        if (this.phase !== "idle" || this.file === null || this.recording === null || this.is_tool_online) return;
        if (!this.bus_client.is_connected()) {
            this.message_element.textContent = BUS_NOT_CONNECTED_TEXT;
            return;
        }
        this.speed = speed;
        this.is_stop_pending = false;
        this.start_tab.start_replay(this.file, speed);
        this.message_element.textContent = WAITING_TEXT;
        this.start_timer = setTimeout(() => this.on_start_timeout(), REPLAY_TOOL_START_TIMEOUT_MS);
        this.set_phase("starting");
    }

    pause(): void {
        if (this.phase !== "playing") return;
        this.start_tab.send_command("replay_pause");
        this.paused_at_ms = performance.now();
        this.set_phase("paused");
    }

    // Also stops a replay that came online after the panel gave up on it (start timeout).
    stop(): void {
        if (this.phase === "idle") {
            if (this.is_tool_online) this.start_tab.send_command("replay_stop");
            return;
        }
        if (this.phase === "starting") this.is_stop_pending = true;
        this.start_tab.send_command("replay_stop");
        this.finish();
        this.show_file_info(); // "waiting for the tool to finish" until it goes offline
    }

    private on_replay_online(is_online: boolean): void {
        this.is_tool_online = is_online;
        this.top_bar.set_banner("replay", is_online);
        if (is_online && this.is_stop_pending) {
            this.is_stop_pending = false;
            this.start_tab.send_command("replay_stop");
        }
        if (is_online && this.phase === "starting") {
            this.start_clock();
            return;
        }
        // The replay tool goes offline when the file ends or after replay_stop.
        if (!is_online && (this.phase === "playing" || this.phase === "paused")) {
            this.show_position();
            this.finish();
            return;
        }
        // Idle: a replay still playing after stop() or a late start keeps Stop on; once it has gone
        // offline, Play can be used again.
        if (this.phase === "idle") {
            this.show_file_info();
            this.update_controls();
        }
    }

    private on_start_timeout(): void {
        this.start_timer = null;
        if (this.phase !== "starting") return;
        this.finish();
        this.message_element.textContent = NOT_STARTED_TEXT;
    }

    private start_clock(): void {
        this.clear_start_timer();
        this.started_ms = performance.now() + REPLAY_TOOL_START_DELAY_MS;
        this.paused_at_ms = null;
        this.paused_total_ms = 0;
        this.show_file_info();
        this.display_timer = setInterval(() => this.show_position(), DISPLAY_INTERVAL_MS);
        this.set_phase("playing");
    }

    private clear_start_timer(): void {
        if (this.start_timer === null) return;
        clearTimeout(this.start_timer);
        this.start_timer = null;
    }

    private finish(): void {
        this.clear_start_timer();
        if (this.display_timer !== null) {
            clearInterval(this.display_timer);
            this.display_timer = null;
        }
        if (this.phase === "starting") this.show_file_info();
        this.set_phase("idle");
    }

    // Seconds since the start of the recording that the replay tool has played.
    private played_s(): number {
        const now_ms = this.paused_at_ms ?? performance.now();
        const played_ms = Math.max(0, now_ms - this.started_ms - this.paused_total_ms);
        return Math.min((played_ms / MS_PER_S) * this.speed, this.duration_s());
    }

    private duration_s(): number {
        return this.recording!.end_t_recv_s - this.recording!.start_t_recv_s;
    }

    private show_position(): void {
        this.show_played(this.played_s());
    }

    private show_played(played_s: number): void {
        const recording = this.recording!;
        this.position_bar.value = played_s;
        this.position_text.textContent = `${format_elapsed(played_s)} / ${format_elapsed(this.duration_s())}`;
        const game_state = game_state_at(recording.game_states, recording.start_t_recv_s + played_s);
        this.recorded_state_element.textContent = game_state === null ? NO_GAME_STATE_TEXT : format_recorded_state(game_state);
    }

    private async refresh_files(): Promise<void> {
        try {
            this.fill_file_select(await recording_files().list());
        } catch (error) {
            this.message_element.textContent = `Cannot list the recordings: ${error_text(error)}`;
        }
    }

    private async load_recording(file: string): Promise<void> {
        try {
            const recording = read_recording_states(await recording_files().read(file));
            if (this.file !== file) return; // another file was chosen while this one was loading
            this.show_recording(recording);
        } catch (error) {
            if (this.file !== file) return;
            this.message_element.textContent = `Cannot read ${file}: ${error_text(error)}`;
        }
    }

    // Shows a newly loaded recording at its start, or hides the position and state rows for null.
    private show_recording(recording: RecordingStates | null): void {
        this.recording = recording;
        this.position_row.hidden = recording === null;
        this.recorded_state_element.hidden = recording === null;
        if (recording !== null) {
            this.position_bar.max = this.duration_s();
            this.show_played(0);
            this.show_file_info();
        }
        this.update_controls();
    }

    private show_file_info(): void {
        if (this.recording === null) return;
        if (this.phase === "idle" && this.is_tool_online) {
            this.message_element.textContent = TOOL_BUSY_TEXT;
            return;
        }
        this.message_element.textContent = `${this.file} · ${this.recording.game_states.length} game states`;
    }

    private fill_file_select(files: string[]): void {
        const placeholder = files.length === 0 ? NO_RECORDINGS_TEXT : NO_FILE_TEXT;
        this.file_select.replaceChildren(new Option(placeholder, ""));
        for (const file of files) this.file_select.add(new Option(file, file));
        // Keep the open file selected if it is still there.
        if (this.file !== null && files.includes(this.file)) this.file_select.value = this.file;
    }

    private on_file_selected(): void {
        const file = this.file_select.value;
        if (file !== "") {
            this.open(file);
            return;
        }
        this.file = null;
        this.message_element.textContent = NO_FILE_TEXT;
        this.show_recording(null);
    }

    private selected_speed(): ReplaySpeed {
        return Number(this.speed_select.value) as ReplaySpeed;
    }

    private set_phase(phase: ReplayPhase): void {
        this.phase = phase;
        this.update_controls();
    }

    private update_controls(): void {
        const is_idle = this.phase === "idle";
        this.file_select.disabled = !is_idle;
        this.speed_select.disabled = !is_idle;
        this.refresh_button.disabled = !is_idle;
        const can_start = is_idle && this.recording !== null && !this.is_tool_online;
        this.play_button.disabled = !(this.phase === "paused" || can_start);
        this.pause_button.disabled = this.phase !== "playing";
        this.stop_button.disabled = is_idle && !this.is_tool_online;
    }

    private build_panel(): void {
        const title = create_element("h3", "replay-title");
        title.textContent = TITLE_TEXT;
        this.file_select.addEventListener("change", () => this.on_file_selected());
        for (const speed of REPLAY_SPEED_VALUES) {
            this.speed_select.add(new Option(`${speed}x`, String(speed), false, speed === DEFAULT_SPEED));
        }
        this.message_element.textContent = NO_FILE_TEXT;
        this.position_row.append(this.position_bar, this.position_text);

        this.root.append(
            title,
            this.create_row(this.file_select, this.speed_select, this.refresh_button),
            this.create_row(this.play_button, this.pause_button, this.stop_button),
            this.message_element,
            this.position_row,
            this.recorded_state_element,
        );
    }

    private create_row(...elements: HTMLElement[]): HTMLDivElement {
        const row = create_element("div", "command-row"); // same look as StartTab's command rows
        row.append(...elements);
        return row;
    }

    private create_button(label: string, on_click: () => void): HTMLButtonElement {
        const button = create_element("button", "command-button");
        button.textContent = label;
        button.addEventListener("click", on_click);
        return button;
    }
}
