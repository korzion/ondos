import { BusClient } from "./busClient";
import {
    CS_COMMAND, GAME_STATE, VISION_BALL, VISION_EDIT_STATE, PLATFORM_STATE,
    EditState, EditReason, Writer, Mode, State,
} from "@shared/topics";

// E-R2, E.8: an E-stop that platform/state has not confirmed after this long is warned about.
const E_STOP_CONFIRM_TIMEOUT_MS = 1000;

export type BannerKind =
    | "bus_not_connected" | "no_game_manager" | "platform_not_connected"
    | "maze_change" | "ball_not_visible" | "e_stop_not_confirmed" | "replay";

// Texts from E.8. Every BannerKind must have one, so a new kind without a text is a type error.
const BANNER_TEXT: Record<BannerKind, string> = {
    bus_not_connected: "Bus not connected",
    no_game_manager: "No GameManager",
    platform_not_connected: "Platform not connected",
    maze_change: "Maze change",
    ball_not_visible: "Ball not visible",
    e_stop_not_confirmed: "E-stop not confirmed: use the E-stop button",
    replay: "Replay",
};

// Only the fields TopBar reads; the shared Bus has already checked each message against its schema.
type GameStateMessage = { state: State; mode: Mode; elapsed_s: number };
type BallMessage = { is_visible: boolean };
type EditStateMessage = { state: EditState; reason: EditReason | null };
type PlatformStateMessage = { is_e_stop: boolean; writer: Writer };

function format_elapsed(elapsed_s: number): string {
    const whole_s = Math.floor(elapsed_s);
    const minutes = String(Math.floor(whole_s / 60)).padStart(2, "0");
    const seconds = String(whole_s % 60).padStart(2, "0");
    return `${minutes}:${seconds}`;
}

export class TopBar {
    private readonly bus_client: BusClient;
    private readonly root: HTMLElement;
    private readonly state_element: HTMLElement;
    private readonly e_stop_button: HTMLButtonElement;
    private readonly banners = new Map<BannerKind, HTMLElement>();
    private current_state: State | null = null;
    private e_stop_timer: ReturnType<typeof setTimeout> | null = null;

    constructor(bus_client: BusClient, root: HTMLElement) {
        this.bus_client = bus_client;
        this.root = root;
        this.state_element = this.create_state_element();
        this.create_banners();
        this.e_stop_button = this.create_e_stop_button();

        bus_client.subscribe(GAME_STATE, (_topic, msg) => this.on_game_state(msg as GameStateMessage));
        bus_client.subscribe(VISION_BALL, (_topic, msg) => this.on_ball(msg as BallMessage));
        bus_client.subscribe(VISION_EDIT_STATE, (_topic, msg) => this.on_edit_state(msg as EditStateMessage));
        bus_client.subscribe(PLATFORM_STATE, (_topic, msg) => this.on_platform_state(msg as PlatformStateMessage));
    }

    on_game_state(msg: GameStateMessage): void {
        this.current_state = msg.state;
        this.state_element.textContent = `${msg.state} · ${msg.mode} · ${format_elapsed(msg.elapsed_s)}`;
        if (msg.state !== "playing") {
            this.set_banner("ball_not_visible", false);
        }
    }

    on_ball(msg: BallMessage): void {
        this.set_banner("ball_not_visible", this.current_state === "playing" && !msg.is_visible);
    }

    set_banner(kind: BannerKind, is_on: boolean): void {
        this.banners.get(kind)!.hidden = !is_on;
        if (kind === "bus_not_connected") {
            // E-R2: the E-stop is enabled whenever the bus is connected, in every game state.
            this.e_stop_button.disabled = is_on;
        }
    }

    send_e_stop(): void {
        const is_sent = this.bus_client.publish(CS_COMMAND, { cmd: "e_stop", mode: null, file: null, speed: null });
        this.cancel_e_stop_timer();
        if (!is_sent) {
            // The command never left the app, so the operator has to use the physical button now.
            this.set_banner("e_stop_not_confirmed", true);
            return;
        }
        this.e_stop_timer = setTimeout(() => {
            this.e_stop_timer = null;
            this.set_banner("e_stop_not_confirmed", true);
        }, E_STOP_CONFIRM_TIMEOUT_MS);
    }

    private on_edit_state(msg: EditStateMessage): void {
        const is_maze_change = msg.state !== "clear";
        const banner = this.banners.get("maze_change")!;
        banner.textContent = msg.reason ? `${BANNER_TEXT.maze_change}: ${msg.reason}` : BANNER_TEXT.maze_change;
        this.set_banner("maze_change", is_maze_change);
    }

    private on_platform_state(msg: PlatformStateMessage): void {
        // A replayed is_e_stop must never count as confirming a real E-stop.
        if (msg.writer === "replay" || !msg.is_e_stop) return;
        this.cancel_e_stop_timer();
        this.set_banner("e_stop_not_confirmed", false);
    }

    private cancel_e_stop_timer(): void {
        if (this.e_stop_timer !== null) {
            clearTimeout(this.e_stop_timer);
            this.e_stop_timer = null;
        }
    }

    private create_state_element(): HTMLElement {
        const element = document.createElement("span");
        element.className = "top-bar-state";
        element.textContent = "No game state";
        this.root.appendChild(element);
        return element;
    }

    private create_e_stop_button(): HTMLButtonElement {
        const button = document.createElement("button");
        button.className = "e-stop-button";
        button.textContent = "E-STOP";
        button.disabled = true; // enabled once the bus connects (set_banner)
        button.addEventListener("click", () => this.send_e_stop());
        this.root.appendChild(button);
        return button;
    }

    private create_banners(): void {
        const banner_area = document.createElement("div");
        banner_area.className = "top-bar-banners";
        this.root.appendChild(banner_area);
        for (const kind of Object.keys(BANNER_TEXT) as BannerKind[]) {
            const banner = document.createElement("div");
            banner.className = "banner";
            banner.textContent = BANNER_TEXT[kind];
            banner.hidden = true;
            banner_area.appendChild(banner);
            this.banners.set(kind, banner);
        }
    }
}
