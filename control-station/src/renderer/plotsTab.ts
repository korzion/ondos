// The Plots tab: one Plot per topic and unit, redrawn at plot_rate_hz while the tab is open
// (E.5 "PlotsTab", E-R1). Fields of one topic with different units (ball position and speed) get
// separate charts, so neither is squeezed by the other's scale.
import type { Callback, Message } from "@shared/bus/bus";
import { VISION_BALL, VISION_STATUS, PLATFORM_STATE, GLOVE_STATE, CONTROL_TARGET_TILT } from "@shared/topics";
import { BusClient } from "./busClient";
import { Plot } from "./plot";
import { Tab } from "./tab";

// E.7 and E-R1: 30 s visible, 20 Hz redraw.
// TODO(#142): these are live variables of the cs key. Connect them to cs/variables_spec with the cs variables.
const plot_window_s = 30;
const plot_rate_hz = 20;

const MS_PER_S = 1000;

// Fields shown at start: tilt, PID tilt, ball position and speed, and fps (design C.9, E.8).
// Only fields added with add_field are stored (kept small for the shared laptop, E.10).
const DEFAULT_PLOT_FIELDS: ReadonlyArray<{ topic: string; fields: readonly string[] }> = [
    { topic: VISION_BALL, fields: ["x_mm", "y_mm", "vx_mm_s", "vy_mm_s"] },
    { topic: PLATFORM_STATE, fields: ["tilt_x_deg", "tilt_y_deg"] },
    { topic: GLOVE_STATE, fields: ["hand_tilt_x_deg", "hand_tilt_y_deg"] },
    { topic: CONTROL_TARGET_TILT, fields: ["target_tilt_x_deg", "target_tilt_y_deg"] },
    { topic: VISION_STATUS, fields: ["fps_hz"] },
];

// The unit at the end of a field name (D4), longest first so "_mm_s" is not read as "_mm".
const UNIT_SUFFIXES: ReadonlyArray<{ suffix: string; unit: string }> = [
    { suffix: "_mm_s", unit: "mm/s" },
    { suffix: "_mm", unit: "mm" },
    { suffix: "_deg", unit: "deg" },
    { suffix: "_hz", unit: "Hz" },
    { suffix: "_pct", unit: "%" },
    { suffix: "_ms", unit: "ms" },
    { suffix: "_s", unit: "s" },
];

function unit_of(field: string): string {
    return UNIT_SUFFIXES.find(({ suffix }) => field.endsWith(suffix))?.unit ?? "";
}

interface UnitPlot {
    readonly plot: Plot;
    readonly panel: HTMLElement;
    readonly fields: Set<string>;
}

export class PlotsTab extends Tab {
    private readonly plots_by_topic = new Map<string, Map<string, UnitPlot>>(); // topic -> unit -> chart
    private draw_timer: ReturnType<typeof setInterval> | null = null;
    // One function object for every topic, so unsubscribe finds the same callback again.
    private readonly handle_message: Callback = (topic, msg, t_recv_s) =>
        this.on_message(topic, msg as Message, t_recv_s);

    constructor(title: string, bus_client: BusClient) {
        super(title, bus_client);
        for (const { topic, fields } of DEFAULT_PLOT_FIELDS) {
            for (const field of fields) this.add_field(topic, field);
        }
    }

    on_open(): void {
        super.on_open();
        this.draw();
        this.draw_timer = setInterval(() => this.draw(), MS_PER_S / plot_rate_hz);
    }

    on_close(): void {
        super.on_close();
        if (this.draw_timer === null) return;
        clearInterval(this.draw_timer);
        this.draw_timer = null;
    }

    add_field(topic: string, field: string): void {
        const unit = unit_of(field);
        const unit_plot = this.plots_by_topic.get(topic)?.get(unit) ?? this.create_unit_plot(topic, unit);
        unit_plot.fields.add(field);
        unit_plot.plot.add_field(field);
    }

    remove_field(topic: string, field: string): void {
        const unit = unit_of(field);
        const unit_plot = this.plots_by_topic.get(topic)?.get(unit);
        if (!unit_plot) return;
        unit_plot.fields.delete(field);
        unit_plot.plot.remove_field(field);
        if (unit_plot.fields.size === 0) this.remove_unit_plot(topic, unit, unit_plot);
    }

    on_message(topic: string, msg: Message, t_recv_s: number): void {
        for (const { plot } of this.plots_by_topic.get(topic)?.values() ?? []) plot.add_message(msg, t_recv_s);
    }

    draw(): void {
        for (const unit_plots of this.plots_by_topic.values()) {
            for (const { plot } of unit_plots.values()) plot.draw();
        }
    }

    // The first chart of a topic is subscribed and named after the topic alone; E-T1 finds a topic's
    // draws by that name. Later charts of the topic add their unit, so their draws stay apart.
    private create_unit_plot(topic: string, unit: string): UnitPlot {
        const unit_plots = this.plots_by_topic.get(topic) ?? new Map<string, UnitPlot>();
        const name = unit_plots.size === 0 ? topic : `${topic} ${unit}`;
        const panel = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = unit === "" ? topic : `${topic} (${unit})`;
        const chart_container = document.createElement("div");
        panel.append(heading, chart_container);
        this.root.appendChild(panel);

        const unit_plot: UnitPlot = { plot: new Plot(chart_container, plot_window_s, name), panel, fields: new Set() };
        if (unit_plots.size === 0) {
            this.plots_by_topic.set(topic, unit_plots);
            this.bus_client.subscribe(topic, this.handle_message);
        }
        unit_plots.set(unit, unit_plot);
        return unit_plot;
    }

    private remove_unit_plot(topic: string, unit: string, unit_plot: UnitPlot): void {
        unit_plot.panel.remove();
        const unit_plots = this.plots_by_topic.get(topic)!;
        unit_plots.delete(unit);
        if (unit_plots.size > 0) return;
        this.bus_client.unsubscribe(topic, this.handle_message);
        this.plots_by_topic.delete(topic);
    }
}
