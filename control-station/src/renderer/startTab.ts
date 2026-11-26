import { Tab } from "./tab";
import { BusClient } from "./busClient";
import { CS_COMMAND, GAME_STATE, State, Command, Mode, MODE_VALUES, ReplaySpeed, RouteStatus, PLAN_ROUTE, VISION_MAZE, Writer, VISION_EVENT, GAME_WARNING, WarningKind, WallSide } from "@shared/topics";
import { Payload, Callback } from "@shared/bus/bus";
import { StatusPanel } from "./statusPanel";

type CommandArgs = { mode: Mode | null; file: string | null; speed: ReplaySpeed | null };

const MAX_LOG_LINES = 200; // default until log_max_lines comes from the cs variables (VariablesTab)

const ALLOWED_COMMANDS: Record<State, readonly Command[]> = {
    setup:    ["set_mode", "read_maze", "calibrate_camera", "calibrate_glove"],
    ready:    ["start", "set_mode", "read_maze", "calibrate_camera", "calibrate_glove"],
    playing:  ["pause", "stop"],
    paused:   ["resume", "stop", "read_maze", "calibrate_glove"],
    finished: ["new_game"],
    e_stop:   ["clear_e_stop"],
};

// The game-command buttons in the order the tab shows them, one row each: game, then maze and
// calibration. Set mode has its own row next to the mode select.
const COMMAND_ROWS: readonly (readonly Command[])[] = [
    ["start", "pause", "resume", "stop", "new_game", "clear_e_stop"],
    ["read_maze", "calibrate_camera", "calibrate_glove"],
];

// Button text for each command
const BUTTON_LABELS: Partial<Record<Command, string>> = {
    set_mode: "Set mode",
    start: "Start",
    pause: "Pause",
    resume: "Resume",
    stop: "Stop",
    new_game: "New game",
    clear_e_stop: "Clear E-stop",
    read_maze: "Read maze",
    calibrate_camera: "Calibrate camera",
    calibrate_glove: "Calibrate glove",
};

// Every bus message carries these (IF-03); the log leaves them out. Same list as in shared/bus/bus.ts, which does not export it.
const ENVELOPE_FIELDS = ["timestamp_s", "seq", "version", "writer"];

// The short text after the topic in a log line.
function format_log_summary(topic: string, msg: object): string {
    if (topic === GAME_WARNING) {
        const warning = msg as { kind: WarningKind; intensity_pct: number };
        return `${warning.kind} ${warning.intensity_pct}%`;
    }
    if (topic === VISION_EVENT) {
        const hit = msg as { wall_side: WallSide; cell: { row: number; col: number }; impact_speed_mm_s: number };
        return `wall hit ${hit.wall_side}, cell ${hit.cell.row},${hit.cell.col}, ${hit.impact_speed_mm_s} mm/s`;
    }
    // Any other topic, e.g. VariablesTab's errors: every field except the envelope.
    const fields = Object.fromEntries(Object.entries(msg).filter(([name]) => !ENVELOPE_FIELDS.includes(name)));
    return JSON.stringify(fields);
}

function create_row(): HTMLDivElement {
    const row = document.createElement("div");
    row.className = "command-row";
    return row;
}

export class StartTab extends Tab {
    private readonly buttons = new Map<Command, HTMLButtonElement>();
    private readonly mode_select: HTMLSelectElement = document.createElement("select");
    private readonly log_list: HTMLUListElement = document.createElement("ul");
    private current_state: State | null = null;
    private maze_id: string | null = null;
    private route: { maze_id: string; status: RouteStatus } | null = null;
    readonly status_panel: StatusPanel;

    private readonly game_state_callback: Callback = (_topic: string, msg: Payload) => this.update_buttons((msg as {state: State}).state);

    private readonly log_callback: Callback = (topic, msg) => this.add_log(topic, msg as object);

    private readonly maze_callback: Callback = (_topic: string, msg: Payload) => {
        if ((msg as { writer: Writer }).writer === "replay") return;
        this.maze_id = (msg as { maze_id: string }).maze_id;
        this.update_buttons(this.current_state);
    };

    private readonly route_callback: Callback = (_topic: string, msg: Payload) => {
        if ((msg as { writer: Writer }).writer === "replay") return;
        this.route = (msg as { maze_id: string; status: RouteStatus });
        this.update_buttons(this.current_state);
    };

    constructor(bus_client: BusClient) {
        super("Start", bus_client);
        this.root.classList.add("start-tab");

        this.root.appendChild(this.create_mode_row());
        for (const commands of COMMAND_ROWS) {
            this.root.appendChild(this.create_command_row(commands));
        }

        const status_panel_root = document.createElement("div");
        this.root.appendChild(status_panel_root);
        this.status_panel = new StatusPanel(bus_client, status_panel_root);

        this.log_list.className = "log-list";
        this.root.appendChild(this.log_list);

        // disable the buttons until state arrives
        this.update_buttons(null);

        // Subscribed for the tab's whole life, not only while it is open: subscribing again on open
        // would hand update_buttons() the cached game/state and undo update_buttons(null) from
        // TopicHealthMonitor (#83, "No GameManager").
        this.bus_client.subscribe(GAME_STATE, this.game_state_callback);
        this.bus_client.subscribe(VISION_MAZE, this.maze_callback);
        this.bus_client.subscribe(PLAN_ROUTE, this.route_callback);

        // For logs
        this.bus_client.subscribe(GAME_WARNING, this.log_callback);
        this.bus_client.subscribe(VISION_EVENT, this.log_callback);
    }

    update_buttons(state: State | null): void {
        this.current_state = state;
        const allowed = state === null ? [] : ALLOWED_COMMANDS[state];
        this.mode_select.disabled = !allowed.includes("set_mode");

        for (const [command, button] of this.buttons) {
            button.disabled = !allowed.includes(command);
        }

        this.buttons.get("resume")!.disabled ||= !this.has_valid_route();
    }

    // Called by ReplayController (#84). file is a name inside the replay tool's recordings folder.
    start_replay(file: string, speed: ReplaySpeed): void {
        this.send_command("replay", { file, speed });
    }

    send_command(cmd: Command, args: Partial<CommandArgs> = {}): void {
        this.bus_client.publish(CS_COMMAND, { cmd, mode: null, file: null, speed: null, ...args });
    }

    private create_mode_row(): HTMLDivElement {
        const row = create_row();
        this.mode_select.className = "mode-select";
        for (const mode of MODE_VALUES) {
            const option = document.createElement("option");
            option.value = mode;
            option.textContent = mode;
            this.mode_select.appendChild(option);
        }
        row.appendChild(this.mode_select);
        row.appendChild(this.create_button("set_mode", () => this.send_command("set_mode", { mode: this.mode_select.value as Mode })));
        return row;
    }

    private create_command_row(commands: readonly Command[]): HTMLDivElement {
        const row = create_row();
        for (const command of commands) {
            row.appendChild(this.create_button(command, () => this.send_command(command)));
        }
        return row;
    }

    // Registers the button in this.buttons, so update_buttons() greys it out by the IF-07 table.
    private create_button(command: Command, on_click: () => void): HTMLButtonElement {
        const button = document.createElement("button");
        button.className = "command-button";
        button.textContent = BUTTON_LABELS[command] ?? command;
        button.addEventListener("click", on_click);
        this.buttons.set(command, button);
        return button;
    }

    private has_valid_route(): boolean {
        return this.route !== null && this.route.status === "valid" && this.route.maze_id === this.maze_id;
    }

    add_log(topic: string, msg: object): void {
        const line = document.createElement("li");
        line.className = "log-line";
        const time_s = (msg as { timestamp_s?: number }).timestamp_s ?? Date.now() / 1000;
        const time_text = new Date(time_s * 1000).toLocaleTimeString();
        const replay_mark = (msg as { writer?: Writer }).writer === "replay" ? "[replay] " : "";
        line.textContent = `[${time_text}] ${replay_mark}${topic}: ${format_log_summary(topic, msg)}`;
        this.log_list.prepend(line);

        // Remove old lines if we exceed MAX_LOG_LINES
        while (this.log_list.childElementCount > MAX_LOG_LINES) {
            this.log_list.removeChild(this.log_list.lastChild!);
        }
    }
}
