import { BusClient } from "./busClient";
import {
    VISION_STATUS, GLOVE_STATE, AI_STATUS, VISION_EDIT_STATE,
    EditState, EditReason, AiStatus, ActiveController, Policy, Writer,
} from "@shared/topics";

const STATUS_TOPICS = [VISION_STATUS, GLOVE_STATE, AI_STATUS, VISION_EDIT_STATE] as const;
type StatusTopic = (typeof STATUS_TOPICS)[number];

// AI doesn't have a "missing" state, the section is hidden instead
const MISSING_TEXT: Record<Exclude<StatusTopic, typeof AI_STATUS>, string> = {
    [VISION_STATUS]: "Vision: no status",
    [GLOVE_STATE]: "Glove: not connected",
    [VISION_EDIT_STATE]: "Maze: not clear",
};

type VisionStatusMessage = { is_camera_ok: boolean; is_calibrated: boolean; markers_found: number; fps_hz: number };
type GloveStateMessage = { is_connected: boolean; is_calibrated: boolean; battery_pct: number };
type AiStatusMessage = { active_controller: ActiveController; status: AiStatus; policy: Policy | null };
type EditStateMessage = { state: EditState; reason: EditReason | null };

// Every maze plate carries 4 ArUco markers on its corners (section 5.5).
const PLATE_MARKER_COUNT = 4;

function format_vision_status(msg: VisionStatusMessage): string {
    const camera = msg.is_camera_ok ? "camera OK" : "camera fault";
    const calibration = msg.is_calibrated ? "calibrated" : "not calibrated";
    return `Vision: ${camera}, ${calibration}, markers ${msg.markers_found}/${PLATE_MARKER_COUNT}, ${msg.fps_hz.toFixed(0)} fps`;
}

function format_glove_status(msg: GloveStateMessage): string {
    // Calibration and battery come from the glove itself, so they mean nothing while it is not connected.
    if (!msg.is_connected) return "Glove: not connected";
    const calibration = msg.is_calibrated ? "calibrated" : "not calibrated";
    return `Glove: connected, ${calibration}, battery ${msg.battery_pct}%`;
}

function format_ai_status(msg: AiStatusMessage): string {
    const policy = msg.policy === null ? "" : ` (${msg.policy})`;
    return `AI: ${msg.active_controller} controller, ${msg.status}${policy}`;
}

// Texts from section 5.5. Section 5.5 has "Maze OK – press Resume", but the panel shows this
// line in every game state, not only while paused, so it leaves out "press Resume".
function format_edit_state(msg: EditStateMessage): string {
    if (msg.state === "clear" && msg.reason === null) return "Maze OK";
    if (msg.state === "clear" && msg.reason === "no_path") return "No path to the exit";
    return `Maze: ${msg.reason ?? msg.state}`;
}

function format_status(topic: StatusTopic, msg: object): string {
    switch (topic) {
        case VISION_STATUS:
            return format_vision_status(msg as VisionStatusMessage);
        case GLOVE_STATE:
            return format_glove_status(msg as GloveStateMessage);
        case AI_STATUS:
            return format_ai_status(msg as AiStatusMessage);
        case VISION_EDIT_STATE:
            return format_edit_state(msg as EditStateMessage);
    }
}

// on_status and set_missing take plain strings (E.5); this narrows them to the four topics.
function is_status_topic(topic: string): topic is StatusTopic {
    return (STATUS_TOPICS as readonly string[]).includes(topic);
}

export class StatusPanel {
    private readonly sections: Map<StatusTopic, HTMLDivElement> = new Map();

    constructor(bus_client: BusClient, root: HTMLDivElement) {
        root.classList.add("status-panel");
        for (const topic of STATUS_TOPICS) {
            const section = document.createElement("div");
            section.className = "status-line";
            root.appendChild(section);
            this.sections.set(topic, section);

            this.set_missing(topic);

            bus_client.subscribe(topic, (msg_topic, msg) => this.on_status(msg_topic, msg as object));
        }
    }

    on_status(topic: string, msg: object): void {
        if (!is_status_topic(topic)) return;

        const section = this.sections.get(topic)!;
        const replay_mark = (msg as { writer?: Writer }).writer === "replay" ? " (replay)" : "";
        section.textContent = format_status(topic, msg) + replay_mark;
        // A new message ends a "missing" state.
        section.hidden = false;
        section.classList.remove("is-missing");
    }

    // Called by TopicHealthMonitor (#83)
    set_missing(topic: string): void {
        if (!is_status_topic(topic)) return;
        const section = this.sections.get(topic)!;
        if (topic === AI_STATUS) {
            section.hidden = true;
            return;
        }

        section.textContent = MISSING_TEXT[topic];
        section.classList.add("is-missing"); // shown in red, so a missing source stands out
    }
}