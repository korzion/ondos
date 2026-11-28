// The 2D maze view on the Start tab (E.5 "MazeView"): the maze, the path to the exit, the ball and
// the latest wall hits, north (+y) up. Cell centres and the path come from the shared maze helper
// (shared/mazes/, IF-04), so the view draws what C computes. Live and replayed messages are drawn
// alike, as in the 3D Twin; the replay tool sends only topics whose real writer is offline.
import type { Callback, Message } from "@shared/bus/bus";
import { nowS } from "@shared/bus/bus";
import { EditState, PLAN_DISTANCE_MAP, PLAN_ROUTE, VISION_BALL, VISION_EDIT_STATE, VISION_EVENT, VISION_MAZE, WallSide } from "@shared/topics";
import { cellCentreMm, hasWall, isInGrid, pathToExit, WALL_E, WALL_N, WALL_S, WALL_W, type Cell, type MazeGeometry } from "@shared/mazes/mazes";
import { BusClient } from "./busClient";
import { Tab } from "./tab";

// TODO(#142): maze_view_rate_hz (E.7) comes from the cs variables; until then the E-R1 rate.
const MAZE_VIEW_RATE_HZ = 20;
const MS_PER_S = 1000;
const BALL_MAX_AGE_MS = 200; // IF-04 vision/ball: older than this, the ball is drawn as stale
// The route is drawn only while it is fresh and the playfield is clear ("What the app reads": a missing
// vision/edit_state or plan/route is treated as not clear, no route drawn). Same limits as GameManager.
const ROUTE_MAX_AGE_MS = 300; // IF-04 plan/route, reader E
const EDIT_STATE_MAX_AGE_MS = 2000; // IF-04 vision/edit_state (1 Hz + on change), reader E
// ASSUMPTION: the design does not say how long a wall hit is shown; 1 s is our choice.
const WALL_HIT_SHOWN_MS = 1000; // how long a hit wall stays red
const MAX_WALL_HITS = 64; // hits kept at once, so a hidden tab cannot collect them without end

const MARGIN_PX = 12;
const PATH_WIDTH_PX = 3;
const MIN_WALL_WIDTH_PX = 2;
const COLOURS = {
    background: "#14181d",
    start_cell: "#24303c",
    wall: "#e6e6e6",
    wall_hit: "#ff5252",
    exit: "#4caf50",
    path: "#ffca28",
    ball: "#4fc3f7",
    ball_lost: "#7a828c",
    text: "#b0b8c0",
} as const;
const TEXT_FONT = "13px sans-serif";
const NO_MAZE_TEXT = "No maze";
const NO_PATH_TEXT = "No path to the exit";

const SIDE_WALLS: Record<WallSide, number> = { n: WALL_N, e: WALL_E, s: WALL_S, w: WALL_W };

// The fields of vision/maze the view draws (IF-04).
interface MazeMsg extends MazeGeometry {
    maze_id: string;
    wall_thickness_mm: number;
    start_cell: Cell | null;
    exit_x_mm: number;
    exit_y_mm: number;
    exit_radius_mm: number;
    ball_diameter_mm: number;
}

interface DistanceMapMsg { maze_id: string; steps: number[][]; }
interface RouteMsg { maze_id: string; status: string; ball_cell: Cell | null; }
interface BallMsg { x_mm: number; y_mm: number; is_visible: boolean; }
interface WallHit { cell: Cell; wall: number; until_s: number; }
interface Received<T> { msg: T; t_recv_s: number; }

// Board millimetres to canvas pixels, +y up.
interface ViewScale { px_per_mm: number; left_px: number; top_px: number; left_mm: number; top_mm: number; }

export class MazeView {
    readonly root: HTMLElement = document.createElement("div");
    private readonly canvas: HTMLCanvasElement = document.createElement("canvas");
    private readonly start_tab: Tab;
    private maze: MazeMsg | null = null;
    private distance_map: DistanceMapMsg | null = null;
    private route: Received<RouteMsg> | null = null;
    private edit_state: Received<EditState> | null = null;
    private ball: Received<BallMsg> | null = null;
    private wall_hits: WallHit[] = [];
    private has_reported_draw_error = false;

    constructor(bus_client: BusClient, start_tab: Tab) {
        this.start_tab = start_tab;
        this.root.className = "maze-view";
        this.root.appendChild(this.canvas);
        // Subscribed for the whole life of the app, so the retained maze and map are there when the tab opens.
        const subscriptions: ReadonlyArray<[string, Callback]> = [
            [VISION_MAZE, (_topic, msg) => this.on_maze(msg as Message)],
            [PLAN_DISTANCE_MAP, (_topic, msg) => this.on_distance_map(msg as Message)],
            [PLAN_ROUTE, (_topic, msg, t_recv_s) => { this.route = { msg: msg as unknown as RouteMsg, t_recv_s }; }],
            [VISION_EDIT_STATE, (_topic, msg, t_recv_s) => {
                this.edit_state = { msg: (msg as Message).state as EditState, t_recv_s };
            }],
            [VISION_BALL, (_topic, msg, t_recv_s) => this.on_ball(msg as Message, t_recv_s)],
            [VISION_EVENT, (_topic, msg) => this.on_event(msg as Message)],
        ];
        for (const [topic, callback] of subscriptions) bus_client.subscribe(topic, callback);
        // E.5 "On each timer tick": redraw only while the Start tab is open.
        setInterval(() => this.on_tick(), MS_PER_S / MAZE_VIEW_RATE_HZ);
    }

    // A message that slips past the checks must not throw on every tick: report it once, keep drawing.
    private on_tick(): void {
        if (!this.start_tab.is_tab_active()) return;
        try {
            this.draw();
        } catch (e) {
            if (!this.has_reported_draw_error) console.warn(`maze view draw failed: ${(e as Error).message}`);
            this.has_reported_draw_error = true;
        }
    }

    // A maze that cannot be drawn (no cells, walls of another size) shows "No maze".
    on_maze(msg: Message): void {
        const maze = msg as unknown as MazeMsg;
        if (!is_drawable_maze(maze)) {
            this.maze = null;
        } else {
            const start_cell = is_cell_of(maze, maze.start_cell) ? maze.start_cell : null;
            this.maze = { ...maze, start_cell };
        }
        this.wall_hits = [];
    }

    on_distance_map(msg: Message): void {
        this.distance_map = msg as unknown as DistanceMapMsg;
    }

    on_ball(msg: Message, t_recv_s: number = nowS()): void {
        this.ball = { msg: msg as unknown as BallMsg, t_recv_s };
    }

    private on_event(msg: Message): void {
        const side = msg.wall_side as string;
        if (msg.kind !== "wall_hit" || this.maze === null || !Object.hasOwn(SIDE_WALLS, side)) return;
        if (!is_cell_of(this.maze, msg.cell)) return;
        const now_s = nowS();
        const hit = { cell: msg.cell, wall: SIDE_WALLS[side as WallSide], until_s: now_s + WALL_HIT_SHOWN_MS / MS_PER_S };
        this.wall_hits = [...this.wall_hits.filter((old) => old.until_s > now_s), hit].slice(-MAX_WALL_HITS);
    }

    draw(): void {
        const context = this.prepare_canvas();
        if (context === null) return;
        const { width_px, height_px } = this.view_size_px();
        context.fillStyle = COLOURS.background;
        context.fillRect(0, 0, width_px, height_px);
        const maze = this.maze;
        if (maze === null) {
            draw_text(context, NO_MAZE_TEXT);
            return;
        }
        const scale = fit_scale(maze, width_px, height_px);
        const now_s = nowS();
        this.wall_hits = this.wall_hits.filter((hit) => hit.until_s > now_s);
        draw_start_cell(context, scale, maze);
        draw_walls(context, scale, maze, this.wall_hits);
        draw_exit(context, scale, maze);
        const route = this.current_route(maze, now_s);
        const path = route === null ? [] : this.path_points_mm(maze, route, now_s);
        if (path.length > 0) draw_path(context, scale, path);
        else if (route?.status === "no_path") draw_text(context, NO_PATH_TEXT);
        this.draw_ball(context, scale, maze, now_s);
    }

    private view_size_px(): { width_px: number; height_px: number } {
        return { width_px: this.root.clientWidth, height_px: this.root.clientHeight };
    }

    // The canvas follows the size of its box in screen pixels, so it stays sharp with Windows display
    // scaling; drawing is in CSS pixels. null while the box has no size (e.g. a hidden tab).
    private prepare_canvas(): CanvasRenderingContext2D | null {
        const { width_px, height_px } = this.view_size_px();
        if (width_px === 0 || height_px === 0) return null;
        const pixel_ratio = window.devicePixelRatio || 1;
        const canvas_width = Math.round(width_px * pixel_ratio);
        const canvas_height = Math.round(height_px * pixel_ratio);
        if (this.canvas.width !== canvas_width || this.canvas.height !== canvas_height) {
            this.canvas.width = canvas_width;
            this.canvas.height = canvas_height;
            this.canvas.style.width = `${width_px}px`;
            this.canvas.style.height = `${height_px}px`;
        }
        const context = this.canvas.getContext("2d");
        context?.setTransform(pixel_ratio, 0, 0, pixel_ratio, 0, 0);
        return context;
    }

    // The latest route of this maze, while it is fresh and the playfield is clear; null otherwise, so a
    // hand in the playfield, a stopped Vision or a new maze never leaves an old path on the screen.
    private current_route(maze: MazeMsg, now_s: number): RouteMsg | null {
        const route = this.route;
        const edit_state = this.edit_state;
        if (route === null || is_older_than(route, now_s, ROUTE_MAX_AGE_MS)) return null;
        if (edit_state === null || is_older_than(edit_state, now_s, EDIT_STATE_MAX_AGE_MS)) return null;
        if (edit_state.msg !== "clear" || route.msg.maze_id !== maze.maze_id) return null;
        return route.msg;
    }

    // From the ball (or its cell's centre) through the cell centres to the exit marker. Empty while the
    // map is not of this maze.
    private path_points_mm(maze: MazeMsg, route: RouteMsg, now_s: number): [number, number][] {
        const map = this.distance_map;
        if (map === null || route.status !== "valid" || !is_cell_of(maze, route.ball_cell)) return [];
        if (map.maze_id !== maze.maze_id) return [];
        if (!has_grid_shape(map.steps, maze)) return [];
        const cells = pathToExit(maze, map.steps, route.ball_cell);
        if (cells.length === 0) return [];
        const ball = this.fresh_visible_ball(now_s);
        const first: [number, number] = ball !== null ? [ball.x_mm, ball.y_mm] : cellCentreMm(maze, cells[0]);
        // In the exit cell the route aims at the exit marker, not the cell centre (IF-04).
        const middle = cells.slice(1, -1).map((cell) => cellCentreMm(maze, cell));
        return [first, ...middle, [maze.exit_x_mm, maze.exit_y_mm]];
    }

    private fresh_visible_ball(now_s: number): BallMsg | null {
        const ball = this.ball;
        if (ball === null || !ball.msg.is_visible) return null;
        return is_older_than(ball, now_s, BALL_MAX_AGE_MS) ? null : ball.msg;
    }

    // A lost or stale ball stays at its last place as a grey ring.
    private draw_ball(context: CanvasRenderingContext2D, scale: ViewScale, maze: MazeMsg, now_s: number): void {
        if (this.ball === null) return;
        const is_shown_live = this.fresh_visible_ball(now_s) !== null;
        const [x_px, y_px] = to_px(scale, this.ball.msg.x_mm, this.ball.msg.y_mm);
        context.beginPath();
        context.arc(x_px, y_px, (maze.ball_diameter_mm / 2) * scale.px_per_mm, 0, 2 * Math.PI);
        if (is_shown_live) {
            context.fillStyle = COLOURS.ball;
            context.fill();
        } else {
            context.strokeStyle = COLOURS.ball_lost;
            context.lineWidth = MIN_WALL_WIDTH_PX;
            context.stroke();
        }
    }
}

// ------------------------------------------------------------------ message checks

function is_older_than(received: Received<unknown>, now_s: number, max_age_ms: number): boolean {
    return (now_s - received.t_recv_s) * MS_PER_S > max_age_ms;
}

// IF-04 fields the drawing needs: cells, a wall flag per cell, sizes a circle can have.
function is_drawable_maze(maze: MazeMsg): boolean {
    return maze.rows > 0 && maze.cols > 0 && maze.cell_size_mm > 0 && has_grid_shape(maze.walls, maze)
        && maze.exit_radius_mm >= 0 && maze.ball_diameter_mm >= 0 && maze.wall_thickness_mm >= 0;
}

function has_grid_shape(grid: unknown, maze: MazeGeometry): boolean {
    return Array.isArray(grid) && grid.length === maze.rows
        && grid.every((row) => Array.isArray(row) && row.length === maze.cols);
}

function is_cell_of(maze: MazeGeometry, cell: unknown): cell is Cell {
    const candidate = cell as Partial<Cell> | null | undefined;
    if (candidate === null || candidate === undefined) return false;
    if (!Number.isInteger(candidate.row) || !Number.isInteger(candidate.col)) return false;
    return isInGrid(maze, candidate as Cell);
}

// ------------------------------------------------------------------ drawing helpers

// The largest scale that fits the whole board, centred in the canvas.
function fit_scale(maze: MazeMsg, width_px: number, height_px: number): ViewScale {
    const width_mm = maze.cols * maze.cell_size_mm;
    const height_mm = maze.rows * maze.cell_size_mm;
    const px_per_mm = Math.max(0, Math.min((width_px - 2 * MARGIN_PX) / width_mm, (height_px - 2 * MARGIN_PX) / height_mm));
    return {
        px_per_mm,
        left_px: (width_px - width_mm * px_per_mm) / 2,
        top_px: (height_px - height_mm * px_per_mm) / 2,
        left_mm: maze.origin_x_mm,
        top_mm: maze.origin_y_mm + height_mm,
    };
}

function to_px(scale: ViewScale, x_mm: number, y_mm: number): [number, number] {
    return [scale.left_px + (x_mm - scale.left_mm) * scale.px_per_mm, scale.top_px + (scale.top_mm - y_mm) * scale.px_per_mm];
}

// The corners of a cell in mm: columns run along +x, rows along +y (IF-04).
function cell_box_mm(maze: MazeMsg, cell: Cell): { x0: number; y0: number; x1: number; y1: number } {
    const x0 = maze.origin_x_mm + cell.col * maze.cell_size_mm;
    const y0 = maze.origin_y_mm + cell.row * maze.cell_size_mm;
    return { x0, y0, x1: x0 + maze.cell_size_mm, y1: y0 + maze.cell_size_mm };
}

// The two ends of one wall of a cell, in mm: N is the +y side, E the +x side (IF-04).
function wall_ends_mm(maze: MazeMsg, cell: Cell, wall: number): [number, number][] {
    const { x0, y0, x1, y1 } = cell_box_mm(maze, cell);
    if (wall === WALL_N) return [[x0, y1], [x1, y1]];
    if (wall === WALL_E) return [[x1, y0], [x1, y1]];
    if (wall === WALL_S) return [[x0, y0], [x1, y0]];
    return [[x0, y0], [x0, y1]];
}

function draw_start_cell(context: CanvasRenderingContext2D, scale: ViewScale, maze: MazeMsg): void {
    if (maze.start_cell === null) return;
    const { x0, y0, x1, y1 } = cell_box_mm(maze, maze.start_cell);
    const [left_px, top_px] = to_px(scale, x0, y1); // north up: the +y side is at the top
    const [right_px, bottom_px] = to_px(scale, x1, y0);
    context.fillStyle = COLOURS.start_cell;
    context.fillRect(left_px, top_px, right_px - left_px, bottom_px - top_px);
}

// Every wall flag of every cell; a wall shared by two cells is simply drawn twice.
function draw_walls(context: CanvasRenderingContext2D, scale: ViewScale, maze: MazeMsg, hits: WallHit[]): void {
    context.lineWidth = Math.max(MIN_WALL_WIDTH_PX, maze.wall_thickness_mm * scale.px_per_mm);
    context.lineCap = "square";
    for (let row = 0; row < maze.rows; row++) {
        for (let col = 0; col < maze.cols; col++) {
            for (const wall of [WALL_N, WALL_E, WALL_S, WALL_W]) {
                if (hasWall(maze, { row, col }, wall)) draw_wall(context, scale, maze, { row, col }, wall, COLOURS.wall);
            }
        }
    }
    // Hit walls on top, so the neighbour cell's copy of the same wall does not cover them.
    for (const hit of hits) draw_wall(context, scale, maze, hit.cell, hit.wall, COLOURS.wall_hit);
}

function draw_wall(context: CanvasRenderingContext2D, scale: ViewScale, maze: MazeMsg, cell: Cell, wall: number, colour: string): void {
    const [start, end] = wall_ends_mm(maze, cell, wall).map(([x_mm, y_mm]) => to_px(scale, x_mm, y_mm));
    context.strokeStyle = colour;
    context.beginPath();
    context.moveTo(...start);
    context.lineTo(...end);
    context.stroke();
}

function draw_exit(context: CanvasRenderingContext2D, scale: ViewScale, maze: MazeMsg): void {
    const [x_px, y_px] = to_px(scale, maze.exit_x_mm, maze.exit_y_mm);
    context.beginPath();
    context.arc(x_px, y_px, maze.exit_radius_mm * scale.px_per_mm, 0, 2 * Math.PI);
    context.fillStyle = COLOURS.exit;
    context.fill();
}

function draw_path(context: CanvasRenderingContext2D, scale: ViewScale, points_mm: [number, number][]): void {
    context.strokeStyle = COLOURS.path;
    context.lineWidth = PATH_WIDTH_PX;
    context.lineJoin = "round";
    context.beginPath();
    points_mm.forEach(([x_mm, y_mm], index) => {
        const [x_px, y_px] = to_px(scale, x_mm, y_mm);
        if (index === 0) context.moveTo(x_px, y_px);
        else context.lineTo(x_px, y_px);
    });
    context.stroke();
}

function draw_text(context: CanvasRenderingContext2D, text: string): void {
    context.fillStyle = COLOURS.text;
    context.font = TEXT_FONT;
    context.textBaseline = "top";
    context.fillText(text, MARGIN_PX, MARGIN_PX);
}
