// The Plots tab: one Plot per topic, redrawn at plot_rate_hz while the tab is open (E.5 "PlotsTab", E-R1).
import type { Callback, Message } from "@shared/bus/bus";
import { VISION_BALL, PLATFORM_STATE, GLOVE_STATE, CONTROL_TARGET_TILT } from "@shared/topics";
import { BusClient } from "./busClient";
import { Plot } from "./plot";
import { Tab } from "./tab";

// E.7 and E-R1: 30 s visible, 20 Hz redraw.
// TODO(#78): these are live variables of the cs key. Connect them to cs/variables_spec when VariablesTab exists.
const plot_window_s = 30;
const plot_rate_hz = 20;

const MS_PER_S = 1000;

// Fields shown at start. Only fields added with add_field are stored (kept small for the shared laptop, E.10).
const DEFAULT_PLOT_FIELDS: ReadonlyArray<{ topic: string; fields: readonly string[] }> = [
    { topic: VISION_BALL, fields: ["x_mm", "y_mm"] },
    { topic: PLATFORM_STATE, fields: ["tilt_x_deg", "tilt_y_deg"] },
    { topic: GLOVE_STATE, fields: ["hand_tilt_x_deg", "hand_tilt_y_deg"] },
    { topic: CONTROL_TARGET_TILT, fields: ["target_tilt_x_deg", "target_tilt_y_deg"] },
];

interface TopicPlot {
    readonly plot: Plot;
    readonly panel: HTMLElement;
    readonly fields: Set<string>;
}

export class PlotsTab extends Tab {
    private readonly topic_plots = new Map<string, TopicPlot>();
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
        const topic_plot = this.topic_plots.get(topic) ?? this.create_topic_plot(topic);
        topic_plot.fields.add(field);
        topic_plot.plot.add_field(field);
    }

    remove_field(topic: string, field: string): void {
        const topic_plot = this.topic_plots.get(topic);
        if (!topic_plot) return;
        topic_plot.fields.delete(field);
        topic_plot.plot.remove_field(field);
        if (topic_plot.fields.size === 0) this.remove_topic_plot(topic, topic_plot);
    }

    on_message(topic: string, msg: Message, t_recv_s: number): void {
        this.topic_plots.get(topic)?.plot.add_message(msg, t_recv_s);
    }

    draw(): void {
        for (const { plot } of this.topic_plots.values()) plot.draw();
    }

    private create_topic_plot(topic: string): TopicPlot {
        const panel = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = topic;
        const chart_container = document.createElement("div");
        panel.append(heading, chart_container);
        this.root.appendChild(panel);

        const topic_plot: TopicPlot = { plot: new Plot(chart_container, plot_window_s), panel, fields: new Set() };
        this.topic_plots.set(topic, topic_plot);
        this.bus_client.subscribe(topic, this.handle_message);
        return topic_plot;
    }

    private remove_topic_plot(topic: string, topic_plot: TopicPlot): void {
        this.bus_client.unsubscribe(topic, this.handle_message);
        topic_plot.panel.remove();
        this.topic_plots.delete(topic);
    }
}
