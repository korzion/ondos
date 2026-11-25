// One chart: keeps the time and value data of its fields, drops anything older than the plot window
// and draws it with uPlot (E.5 "Plot").
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { log_draw } from "./drawLog";

const PLOT_HEIGHT_PX = 160;
const SERIES_COLORS = ["#4fc3f7", "#ffb74d", "#81c784", "#e57373", "#ba68c8", "#fff176"];
const AXIS_COLOR = "#e6e8eb";
const GRID_COLOR = "#3a424d";

type Message = Record<string, unknown>;

export class Plot {
    private readonly container: HTMLElement;
    private readonly window_s: number;
    private readonly name: string; // only for the draw log (E-T1)
    private readonly times_s: number[] = [];
    private readonly values_by_field = new Map<string, (number | null)[]>();
    private chart: uPlot | null = null;
    private is_chart_outdated = false;
    private has_new_data = false;

    constructor(container: HTMLElement, window_s: number, name = "") {
        this.container = container;
        this.window_s = window_s;
        this.name = name;
    }

    add_field(field: string): void {
        if (this.values_by_field.has(field)) return;
        // Samples that arrived before this field was added have no value for it.
        this.values_by_field.set(field, new Array<number | null>(this.times_s.length).fill(null));
        this.is_chart_outdated = true;
    }

    remove_field(field: string): void {
        if (!this.values_by_field.delete(field)) return;
        this.is_chart_outdated = true;
        if (this.values_by_field.size === 0) this.discard_data();
    }

    add_message(msg: Message, t_recv_s: number): void {
        if (this.values_by_field.size === 0) return;
        this.times_s.push(t_recv_s);
        for (const [field, values] of this.values_by_field) {
            const value = msg[field];
            values.push(typeof value === "number" && Number.isFinite(value) ? value : null);
        }
        this.drop_samples_older_than(t_recv_s - this.window_s);
        this.has_new_data = true;
    }

    draw(): void {
        if (this.values_by_field.size === 0) return;
        if (this.container.clientWidth === 0) return; // hidden tab: uPlot cannot size itself yet
        if (this.is_chart_outdated) this.rebuild_chart();
        if (!this.chart) this.rebuild_chart();
        if (!this.has_new_data) return; // no new data: the plot stays frozen (E.8, vision or platform stopped)
        this.resize_to_container();
        this.chart!.setData(this.chart_data(), false);
        // The right edge is the newest sample, not the clock, so the time axis stops when the data stops.
        const newest_s = this.times_s[this.times_s.length - 1];
        this.chart!.setScale("x", { min: newest_s - this.window_s, max: newest_s });
        this.has_new_data = false;
    }

    private drop_samples_older_than(cutoff_s: number): void {
        let old_count = 0;
        while (old_count < this.times_s.length && this.times_s[old_count] < cutoff_s) old_count++;
        if (old_count === 0) return;
        this.times_s.splice(0, old_count);
        for (const values of this.values_by_field.values()) values.splice(0, old_count);
    }

    private chart_data(): uPlot.AlignedData {
        return [this.times_s, ...this.values_by_field.values()];
    }

    private rebuild_chart(): void {
        this.chart?.destroy();
        this.chart = new uPlot(this.chart_options(), this.chart_data(), this.container);
        this.is_chart_outdated = false;
        this.has_new_data = true;
    }

    // Logs what uPlot really shows. It reads the scale from uPlot, so a wrong setScale in draw() shows in the log (E-T1).
    private log_chart_draw(chart: uPlot): void {
        const { min, max } = chart.scales.x;
        if (min == null || max == null || this.times_s.length === 0) return;
        log_draw({ plot: this.name, x_min_s: min, x_max_s: max, oldest_s: this.times_s[0], points: this.times_s.length });
    }

    private chart_options(): uPlot.Options {
        const fields = [...this.values_by_field.keys()];
        return {
            width: this.container.clientWidth,
            height: PLOT_HEIGHT_PX,
            scales: { x: { time: true } },
            hooks: { draw: [(chart) => this.log_chart_draw(chart)] },
            axes: [
                { stroke: AXIS_COLOR, grid: { stroke: GRID_COLOR } },
                { stroke: AXIS_COLOR, grid: { stroke: GRID_COLOR } },
            ],
            series: [
                {},
                ...fields.map((field, index) => ({
                    label: field,
                    stroke: SERIES_COLORS[index % SERIES_COLORS.length],
                    width: 1.5,
                    spanGaps: false,
                })),
            ],
        };
    }

    private resize_to_container(): void {
        const width = this.container.clientWidth;
        if (this.chart && this.chart.width !== width) this.chart.setSize({ width, height: PLOT_HEIGHT_PX });
    }

    private discard_data(): void {
        this.chart?.destroy();
        this.chart = null;
        this.times_s.length = 0;
        this.has_new_data = false;
    }
}
