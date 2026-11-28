// Topic-health panel (E.5 TopicHealthMonitor, E-R4, E.8): the age of the last message on every topic
// the app reads, which programs are online, and a warning when two programs write the same topic.
// The missing-data warnings outside the panel (banners, status lines) are set by on_missing_change.
import type { Callback, Message } from "@shared/bus/bus";
import {
    GAME_STATE, GAME_WARNING, VISION_BALL, VISION_MAZE, PLAN_DISTANCE_MAP, PLAN_ROUTE, VISION_STATUS,
    VISION_EVENT, VISION_EDIT_STATE, AI_TARGET_TILT, CONTROL_TARGET_TILT, AI_STATUS, PLATFORM_STATE,
    GLOVE_STATE, GAME_STATE_MAX_AGE_MS, WRITER_VALUES, Writer, sysOnline, topicInfo,
} from "@shared/topics";
import { BusClient } from "./busClient";
import { log_missing_change } from "./healthLog";

const MS_PER_S = 1000;

// Max delay of every topic the app reads (IF-07 "What the app reads"), from the "Control Station"
// reader rows of the interface appendix. ASSUMPTION (#83): null means the appendix gives no max delay for
// the Control Station (events, or topics only other modules time out), so the panel shows the age but
// never turns the row red.
// vision/image is left out: it has no envelope, and CameraTab subscribes to it only while open.
const MAX_DELAY_MS: Readonly<Record<string, number | null>> = {
    [GAME_STATE]: GAME_STATE_MAX_AGE_MS, // IF-05: "No GameManager"
    [PLATFORM_STATE]: 200, // IF-02: "Platform not connected"
    [GLOVE_STATE]: 200, // IF-02: glove panel shows "not connected"
    [VISION_BALL]: 200, // IF-04: plots freeze, health panel red
    [VISION_STATUS]: 3000, // IF-04: Vision panel shows "no status"
    [AI_STATUS]: 1000, // IF-06: AI section hidden
    [VISION_EDIT_STATE]: null,
    [VISION_MAZE]: null,
    [PLAN_DISTANCE_MAP]: null,
    [PLAN_ROUTE]: null,
    [VISION_EVENT]: null,
    [GAME_WARNING]: null,
    [AI_TARGET_TILT]: null,
    [CONTROL_TARGET_TILT]: null,
};

// Replay is started on demand and is normally offline, so it is not listed as a program.
const LISTED_PROGRAMS = WRITER_VALUES.filter((program) => program !== "replay");

const NO_VALUE_TEXT = "–";

// ASSUMPTION (#83): E.8 does not say how long the two-writer warning stays on. Here it stays on while the
// last message from a wrong writer is at most this old, the longest max delay above (vision/status).
const WRONG_WRITER_HOLD_S = 3;

export type MissingChangeCallback = (topic: string, is_missing: boolean) => void;

interface HealthRow {
    readonly root: HTMLTableRowElement;
    readonly writer: HTMLTableCellElement;
    readonly age: HTMLTableCellElement;
    readonly seq: HTMLTableCellElement;
    readonly status: HTMLTableCellElement;
}

interface TopicHealth {
    readonly max_delay_ms: number | null;
    readonly expected_writer: string; // the topic's writer in TOPIC_TABLE
    readonly row: HealthRow;
    last_t_recv_s: number | null;
    last_seq: number | null;
    last_writer: Writer | null;
    last_wrong_writer: Writer | null;
    last_wrong_t_recv_s: number | null;
    is_missing: boolean;
}

function add_cell(row: HTMLTableRowElement, text: string): HTMLTableCellElement {
    const cell = row.insertCell();
    cell.textContent = text;
    return cell;
}

function format_age(health: TopicHealth, now_s: number): string {
    if (health.last_t_recv_s === null) return NO_VALUE_TEXT;
    return `${(now_s - health.last_t_recv_s).toFixed(1)} s`;
}

function format_max_delay(max_delay_ms: number | null): string {
    return max_delay_ms === null ? NO_VALUE_TEXT : `${max_delay_ms / MS_PER_S} s`;
}

// E.8: every topic has one writer, its writer in TOPIC_TABLE. Stand-ins use the real program id, so
// they are not wrong writers. Returns the wrong writer while its last message is recent, else null.
function recent_wrong_writer(health: TopicHealth, now_s: number): Writer | null {
    if (health.last_wrong_t_recv_s === null) return null;
    if (now_s - health.last_wrong_t_recv_s > WRONG_WRITER_HOLD_S) return null;
    return health.last_wrong_writer;
}

// The two-writer warning wins: it means the data on the topic cannot be trusted even when fresh.
function status_text(health: TopicHealth, wrong_writer: Writer | null): string {
    if (wrong_writer !== null) return `Two writers: ${health.expected_writer}, ${wrong_writer}`;
    if (health.is_missing) return "Missing";
    if (health.last_t_recv_s === null) return "No data yet";
    return "OK";
}

// A topic with a max delay is missing when it never came or came longer ago than that.
function is_topic_missing(health: TopicHealth, now_s: number): boolean {
    if (health.max_delay_ms === null) return false;
    if (health.last_t_recv_s === null) return true;
    return (now_s - health.last_t_recv_s) * MS_PER_S > health.max_delay_ms;
}

export class TopicHealthMonitor {
    private readonly topics = new Map<string, TopicHealth>();
    private readonly online_programs = new Set<string>();
    private readonly programs_element: HTMLElement;
    private readonly on_missing_change: MissingChangeCallback;

    private readonly message_callback: Callback = (topic, msg, t_recv_s) => {
        const { writer, seq } = msg as Message;
        this.on_message(topic, writer as Writer, seq as number, t_recv_s);
    };

    constructor(bus_client: BusClient, root: HTMLElement, on_missing_change: MissingChangeCallback) {
        this.on_missing_change = on_missing_change;
        root.classList.add("health-panel");
        this.programs_element = this.create_programs_element(root);
        const table_body = this.create_table(root);

        for (const [topic, max_delay_ms] of Object.entries(MAX_DELAY_MS)) {
            const row = this.create_row(table_body, topic, max_delay_ms);
            this.topics.set(topic, {
                max_delay_ms, expected_writer: topicInfo(topic).writer, row, last_t_recv_s: null, last_seq: null,
                last_writer: null, last_wrong_writer: null, last_wrong_t_recv_s: null, is_missing: false,
            });
            bus_client.subscribe(topic, this.message_callback);
        }
        for (const program of WRITER_VALUES) {
            bus_client.subscribe(sysOnline(program), (_topic, msg) => this.on_online(program, msg === true));
        }
        this.show_programs();
    }

    // ASSUMPTION (#83): E.5 gives on_message(topic, seq, t_recv_s); writer is added for the two-writer check.
    on_message(topic: string, writer: Writer, seq: number, t_recv_s: number): void {
        const health = this.topics.get(topic);
        // Replay plays a topic only while its real writer is off, so it says nothing about the live writer.
        if (!health || writer === "replay") return;
        health.last_t_recv_s = t_recv_s;
        health.last_seq = seq;
        health.last_writer = writer;
        if (writer !== health.expected_writer) {
            health.last_wrong_writer = writer;
            health.last_wrong_t_recv_s = t_recv_s;
        }
    }

    on_online(program: string, is_online: boolean): void {
        if (is_online) this.online_programs.add(program);
        else this.online_programs.delete(program);
        this.show_programs();
    }

    check_topics(now_s: number): void {
        for (const [topic, health] of this.topics) {
            this.update_missing(topic, health, now_s);
            this.show_row(health, now_s);
        }
    }

    private update_missing(topic: string, health: TopicHealth, now_s: number): void {
        const is_missing = is_topic_missing(health, now_s);
        if (is_missing === health.is_missing) return;
        health.is_missing = is_missing;
        log_missing_change(topic, is_missing);
        this.on_missing_change(topic, is_missing);
    }

    private show_row(health: TopicHealth, now_s: number): void {
        const wrong_writer = recent_wrong_writer(health, now_s);
        health.row.writer.textContent = health.last_writer ?? NO_VALUE_TEXT;
        health.row.age.textContent = format_age(health, now_s);
        health.row.seq.textContent = health.last_seq === null ? NO_VALUE_TEXT : String(health.last_seq);
        health.row.status.textContent = status_text(health, wrong_writer);
        health.row.root.classList.toggle("is-unhealthy", health.is_missing || wrong_writer !== null);
    }

    private show_programs(): void {
        this.programs_element.replaceChildren(...LISTED_PROGRAMS.map((program) => this.create_program_badge(program)));
    }

    private create_program_badge(program: string): HTMLSpanElement {
        const is_online = this.online_programs.has(program);
        const badge = document.createElement("span");
        badge.className = is_online ? "program-badge" : "program-badge is-offline";
        badge.textContent = `${program}: ${is_online ? "online" : "offline"}`;
        return badge;
    }

    private create_programs_element(root: HTMLElement): HTMLElement {
        const element = document.createElement("div");
        element.className = "health-programs";
        root.appendChild(element);
        return element;
    }

    // Returns the body that the topic rows go into.
    private create_table(root: HTMLElement): HTMLTableSectionElement {
        const table = document.createElement("table");
        table.className = "health-table";
        const header = table.createTHead().insertRow();
        for (const title of ["Topic", "Writer", "Age", "Max delay", "seq", "Status"]) {
            header.appendChild(document.createElement("th")).textContent = title;
        }
        root.appendChild(table);
        return table.createTBody();
    }

    private create_row(table_body: HTMLTableSectionElement, topic: string, max_delay_ms: number | null): HealthRow {
        const root = table_body.insertRow();
        add_cell(root, topic);
        const writer = add_cell(root, NO_VALUE_TEXT);
        const age = add_cell(root, NO_VALUE_TEXT);
        add_cell(root, format_max_delay(max_delay_ms));
        const seq = add_cell(root, NO_VALUE_TEXT);
        const status = add_cell(root, NO_VALUE_TEXT);
        return { root, writer, age, seq, status };
    }
}
