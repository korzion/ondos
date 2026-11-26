// The Twin tab: hosts the 3D Twin (E.5 "TwinTab"). While the tab is open it receives the maze, the
// ball, the plate tilt and the AI's target points, checks how old they are and draws a frame on every
// screen refresh (E-R6: 60 FPS, at most 20 ms from message to screen). A hidden tab draws nothing (E.10).
import type { Callback, Message } from "@shared/bus/bus";
import { nowS } from "@shared/bus/bus";
import { AI_STATUS, PLATFORM_STATE, VISION_BALL, VISION_MAZE } from "@shared/topics";
import { BusClient } from "./busClient";
import { Tab } from "./tab";
import { BallLook, ThreeTwinViewport, TwinFrame } from "./threeTwinViewport";

// How long each message may be missing before the twin reacts (reader tables for the 3D Twin).
const BALL_MAX_AGE_MS = 200; // IF-04 vision/ball: freeze the view
const PLATFORM_MAX_AGE_MS = 200; // IF-02 platform/state: freeze the view, show a stale-data warning
const AI_STATUS_MAX_AGE_MS = 1000; // IF-06 ai/status: hide the AI overlay
const MS_PER_S = 1000;
const STATS_PERIOD_MS = 1000; // the FPS and delay shown are over the last second

const OVERLAY_MARGIN = "8px";
const OVERLAY_FONT_SIZE = "13px";
const NO_MAZE_TEXT = "No maze";
const STALE_TEXT = "Stale data:";
const BALL_LOOK_TEXT: Partial<Record<BallLook, string>> = {
    predicted: "Ball position predicted",
    lost: "Ball not visible",
};

interface LatestMessage {
    msg: Message;
    t_recv_s: number;
}

export class TwinTab extends Tab {
    private readonly viewport: ThreeTwinViewport;
    private readonly view_area: HTMLElement;
    private readonly status_text: HTMLElement;
    private readonly stats_text: HTMLElement;
    private has_maze = false;
    private ball: LatestMessage | null = null;
    private platform: LatestMessage | null = null;
    private ai_status: LatestMessage | null = null;
    private frame_request: number | null = null;
    // For the FPS and delay shown in the corner (E-R6, used by E-T14). The oldest message not yet
    // drawn, and the oldest one in the frame drawn last (on the screen when the next frame starts).
    private oldest_undrawn_s: number | null = null;
    private oldest_in_last_frame_s: number | null = null;
    private frames_in_period = 0;
    private largest_delay_ms = 0;
    private period_start_s = 0;
    private is_stats_shown = true;

    // One function object per topic, so unsubscribe finds the same callback again.
    private readonly handle_maze: Callback = (_topic, msg) => this.on_maze(msg as Message);
    private readonly handle_ball: Callback = (_topic, msg, t_recv_s) => { this.ball = this.receive(msg, t_recv_s); };
    private readonly handle_platform: Callback = (_topic, msg, t_recv_s) => { this.platform = this.receive(msg, t_recv_s); };
    private readonly handle_ai_status: Callback = (_topic, msg, t_recv_s) => { this.ai_status = this.receive(msg, t_recv_s); };
    private readonly subscriptions: ReadonlyArray<[string, Callback]> = [
        [VISION_MAZE, this.handle_maze],
        [VISION_BALL, this.handle_ball],
        [PLATFORM_STATE, this.handle_platform],
        [AI_STATUS, this.handle_ai_status],
    ];

    constructor(title: string, bus_client: BusClient) {
        super(title, bus_client);
        this.view_area = this.create_view_area();
        this.status_text = this.create_overlay_text({ top: OVERLAY_MARGIN, left: OVERLAY_MARGIN });
        this.stats_text = this.create_overlay_text({ bottom: OVERLAY_MARGIN, right: OVERLAY_MARGIN });
        this.stats_text.style.cursor = "pointer";
        this.stats_text.addEventListener("click", () => this.toggle_stats());
        this.viewport = new ThreeTwinViewport(this.view_area);
    }

    // E.5 and E.10: messages are received and frames drawn only while the tab is open.
    on_open(): void {
        super.on_open();
        for (const [topic, callback] of this.subscriptions) this.bus_client.subscribe(topic, callback);
        this.oldest_undrawn_s = null;
        this.oldest_in_last_frame_s = null;
        this.start_stats_period(nowS());
        this.frame_request = requestAnimationFrame(this.draw_frame);
    }

    on_close(): void {
        super.on_close();
        for (const [topic, callback] of this.subscriptions) this.bus_client.unsubscribe(topic, callback);
        if (this.frame_request !== null) cancelAnimationFrame(this.frame_request);
        this.frame_request = null;
    }

    private on_maze(msg: Message): void {
        this.has_maze = true;
        this.viewport.set_maze(msg);
    }

    private receive(msg: unknown, t_recv_s: number): LatestMessage {
        if (this.oldest_undrawn_s === null) this.oldest_undrawn_s = t_recv_s;
        return { msg: msg as Message, t_recv_s };
    }

    // ------------------------------------------------------------------ one frame

    private readonly draw_frame = (): void => {
        if (!this.is_tab_active()) return;
        const now_s = nowS();
        this.measure_delay(now_s);
        const stale_topics = this.stale_topics(now_s);
        this.viewport.set_stale(stale_topics.length > 0);
        const frame = this.build_frame(now_s, stale_topics);
        this.viewport.update(frame);
        this.count_frame(now_s);
        this.show_status(stale_topics, frame.ball_look);
        this.frame_request = requestAnimationFrame(this.draw_frame);
    };

    // A topic is stale when it never came or came longer ago than its limit.
    private stale_topics(now_s: number): string[] {
        const stale: string[] = [];
        if (is_older_than(this.ball, now_s, BALL_MAX_AGE_MS)) stale.push(VISION_BALL);
        if (is_older_than(this.platform, now_s, PLATFORM_MAX_AGE_MS)) stale.push(PLATFORM_STATE);
        return stale;
    }

    private build_frame(now_s: number, stale_topics: string[]): TwinFrame {
        const platform = this.platform?.msg;
        const is_ai_fresh = !is_older_than(this.ai_status, now_s, AI_STATUS_MAX_AGE_MS);
        return {
            ball: this.ball?.msg ?? null,
            ball_look: this.ball_look(stale_topics.includes(VISION_BALL)),
            tilt_x_deg: (platform?.tilt_x_deg as number | undefined) ?? 0,
            tilt_y_deg: (platform?.tilt_y_deg as number | undefined) ?? 0,
            target_points_mm: is_ai_fresh ? (this.ai_status!.msg.target_points_mm as number[][]) : [],
        };
    }

    // The most important look wins: stale > lost > predicted > normal.
    private ball_look(is_ball_stale: boolean): BallLook {
        if (is_ball_stale || this.ball === null) return "stale";
        if (!this.ball.msg.is_visible) return "lost";
        if (this.ball.msg.is_predicted) return "predicted";
        return "normal";
    }

    // ------------------------------------------------------------------ text over the view

    private show_status(stale_topics: string[], look: BallLook): void {
        const lines: string[] = [];
        if (!this.has_maze) lines.push(NO_MAZE_TEXT);
        if (stale_topics.length > 0) lines.push(`${STALE_TEXT} ${stale_topics.join(", ")}`);
        else if (BALL_LOOK_TEXT[look]) lines.push(BALL_LOOK_TEXT[look]!);
        set_text(this.status_text, lines.join("\n"));
    }

    // E-R6 "from message to screen": a frame drawn in one screen refresh is on the screen when the
    // next one starts, so a message's delay is taken then, not when its frame was drawn.
    private measure_delay(now_s: number): void {
        if (this.oldest_in_last_frame_s !== null) {
            const delay_ms = (now_s - this.oldest_in_last_frame_s) * MS_PER_S;
            this.largest_delay_ms = Math.max(this.largest_delay_ms, delay_ms);
        }
        this.oldest_in_last_frame_s = this.oldest_undrawn_s;
        this.oldest_undrawn_s = null;
    }

    private count_frame(now_s: number): void {
        this.frames_in_period++;
        const period_ms = (now_s - this.period_start_s) * MS_PER_S;
        if (period_ms < STATS_PERIOD_MS) return;
        this.show_stats((this.frames_in_period * MS_PER_S) / period_ms);
        this.start_stats_period(now_s);
    }

    private show_stats(fps: number): void {
        const text = this.is_stats_shown ? `${fps.toFixed(0)} FPS · ${this.largest_delay_ms.toFixed(0)} ms` : "FPS";
        set_text(this.stats_text, text);
    }

    private start_stats_period(now_s: number): void {
        this.frames_in_period = 0;
        this.largest_delay_ms = 0;
        this.period_start_s = now_s;
    }

    private toggle_stats(): void {
        this.is_stats_shown = !this.is_stats_shown;
        if (!this.is_stats_shown) set_text(this.stats_text, "FPS");
    }

    // ------------------------------------------------------------------ layout

    // The view fills the tab area (#app), whose height the page layout sets; the viewport follows
    // its size (ResizeObserver), so no window size is read here.
    private create_view_area(): HTMLElement {
        this.root.style.height = "100%";
        const area = document.createElement("div");
        Object.assign(area.style, { position: "relative", height: "100%" }); // texts and the reset button lie over the view
        this.root.appendChild(area);
        return area;
    }

    private create_overlay_text(position: Partial<CSSStyleDeclaration>): HTMLElement {
        const text = document.createElement("div");
        Object.assign(text.style, { position: "absolute", whiteSpace: "pre", fontSize: OVERLAY_FONT_SIZE, zIndex: "1" }, position);
        this.view_area.appendChild(text);
        return text;
    }
}

function is_older_than(latest: LatestMessage | null, now_s: number, max_age_ms: number): boolean {
    return latest === null || (now_s - latest.t_recv_s) * MS_PER_S > max_age_ms;
}

// Changing the page only when the text changes keeps a frame cheap.
function set_text(element: HTMLElement, text: string): void {
    if (element.textContent !== text) element.textContent = text;
}
