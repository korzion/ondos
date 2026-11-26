// The 3D Twin: draws the maze, the ball and the plate tilt with Three.js (E.5 "ThreeTwinViewport").
// The scene is built in the board frame (D4: +x right, +y far edge, +z up, mm) and turned once so
// that Three.js's +y points up. The view can be turned with the mouse; the data stay in the board frame.
import type { Message } from "@shared/bus/bus";
import type { WallSide } from "@shared/topics";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

// How the ball is drawn. TwinTab chooses it from vision/ball and the message age.
export type BallLook = "normal" | "predicted" | "lost" | "stale";

// What one drawn frame shows. update(msg) of E.5 receives this: the latest messages, already
// checked for age by TwinTab, so the viewport only draws.
export interface TwinFrame {
    ball: Message | null; // latest vision/ball, or null before the first one
    ball_look: BallLook;
    tilt_x_deg: number; // from platform/state; 0 before the first one
    tilt_y_deg: number;
    target_points_mm: ReadonlyArray<readonly number[]>; // ai/status; empty when it is older than 1 s
}

// Colours of the real parts (mechanical design v4): black plate and outer wall, white inner walls,
// green exit marker. The ball is drawn as a steel ball until its real colour is chosen (C).
const BACKGROUND_COLOUR = 0x2a3038; // a little lighter than the app, so the black plate stands out
const PLATE_COLOUR = 0x161616;
const OUTER_WALL_COLOUR = 0x101010;
const INNER_WALL_COLOUR = 0xf2f2f2;
const EXIT_COLOUR = 0x2ea043;
const BALL_COLOUR = 0xb9c0c8;
const STALE_BALL_COLOUR = 0xe5484d; // red is used only for "the ball data is stale"
const TARGET_COLOUR = 0x3b82f6;
const AXIS_COLOUR = 0xe6e8eb;

// Ball looks, agreed on #82 (not in the design document): see-through while predicted, faint while lost.
const BALL_OPACITY: Record<BallLook, number> = { normal: 1, predicted: 0.45, lost: 0.15, stale: 1 };

// Sizes that are not in vision/maze; they only change the picture (mechanical design v4).
const PLATE_MARGIN_MM = 4; // the plate is 4 mm larger than the maze area on each side
const PLATE_THICKNESS_MM = 4;
const OUTER_WALL_THICKNESS_MM = 4; // its inner face is where an inner wall's face would be
const OUTER_WALL_DEPTH_OFFSET = -1; // see create_wall_materials
const CELL_CENTRE_OFFSET_CELLS = 0.5; // a cell centre is half a cell from the cell's origin corner (IF-04)
const EXIT_MARKER_HEIGHT_MM = 0.3; // just above the plate, so it is not hidden by it
const TARGET_RADIUS_MM = 2.5;
const AXIS_LENGTH_MM = 30;
const AXIS_HEAD_MM = 6;
const AXIS_HEAD_WIDTH_MM = 3;

// Camera: straight in front of one side of the plate and above it, so the tilt is easy to see.
const CAMERA_FOV_DEG = 40;
const CAMERA_NEAR_MM = 1;
const CAMERA_FAR_MM = 10000;
const FRONT_VIEW_DIRECTION = new THREE.Vector3(0, 1.2, 1.0); // world: up, and towards the board's -y side
const WORLD_UP = new THREE.Vector3(0, 1, 0);
// The four sides the camera can stand at, as turns about the vertical axis. The -y side comes first,
// then its neighbours, so on a tie the view stays closest to the -y side.
const VIEW_TURNS_RAD = [0, -Math.PI / 2, Math.PI / 2, Math.PI];
const VIEW_DISTANCE_PER_PLATE = 1.6; // camera distance as a multiple of the plate size
const MIN_ZOOM_PER_PLATE = 0.6;
const MAX_ZOOM_PER_PLATE = 4;
const LOWEST_VIEW_ANGLE_RAD = THREE.MathUtils.degToRad(80); // the camera never goes below the plate
const NO_MAZE_PLATE_MM = 200; // view size before the first vision/maze

const LIGHT_DIRECTION = new THREE.Vector3(-0.6, 1.5, 0.8); // from the left side and above
const LIGHT_COLOUR = 0xffffff;
const LIGHT_INTENSITY = 2;
const LIGHT_DISTANCE_MM = 400; // far enough that the light falls the same way on the whole plate
const SHADOW_REACH_MM = 200; // half the width the shadows cover; more than half of the largest plate
const SHADOW_MAP_SIZE = 1024;

// Surfaces: a shiny steel ball, matte plate and walls.
const BALL_METALNESS = 0.85;
const BALL_ROUGHNESS = 0.25;
const PLATE_ROUGHNESS = 0.9;
const WALL_ROUGHNESS = 0.7;
const BALL_WIDTH_SEGMENTS = 32;
const BALL_HEIGHT_SEGMENTS = 16;
const TARGET_WIDTH_SEGMENTS = 16;
const TARGET_HEIGHT_SEGMENTS = 8;
const EXIT_SEGMENTS = 32;
const MAX_TARGETS = 3; // ai/status: up to 3 points
const POINT_COMPONENTS = 3; // x, y, z of one line point
const WALL_KEY_DECIMALS = 1; // walls closer than 0.1 mm are the same wall
const BUTTON_MARGIN = "8px";
const LABEL_FONT_SIZE = "12px";

const WALL_BITS: ReadonlyArray<{ side: WallSide; bit: number }> = [
    { side: "n", bit: 1 }, { side: "e", bit: 2 }, { side: "s", bit: 4 }, { side: "w", bit: 8 },
]; // walls[row][col] bit flags (IF-04)

interface MazeGeometry {
    rows: number;
    cols: number;
    cell_size_mm: number;
    origin_x_mm: number;
    origin_y_mm: number;
    wall_thickness_mm: number;
    wall_height_mm: number;
    walls: number[][];
    start_cell: { row: number; col: number } | null;
    exit_x_mm: number;
    exit_y_mm: number;
}

export class ThreeTwinViewport {
    private readonly renderer: THREE.WebGLRenderer;
    private readonly label_renderer = new CSS2DRenderer();
    private readonly scene = new THREE.Scene();
    private readonly camera = new THREE.PerspectiveCamera(CAMERA_FOV_DEG, 1, CAMERA_NEAR_MM, CAMERA_FAR_MM);
    private readonly controls: OrbitControls;
    // board_frame turns the board frame (z up) into Three.js's frame (y up). Section A: a fixed outer
    // frame, a middle frame turning about one axis and the plate turning about the other. The document
    // does not say which axis is which; here the middle frame tilts front-back (tilt_y_deg) and carries
    // the plate, which tilts left-right (tilt_x_deg).
    private readonly board_frame = new THREE.Group();
    private readonly middle_frame = new THREE.Group();
    private readonly plate = new THREE.Group();
    private readonly maze_parts = new THREE.Group();
    private readonly axes: THREE.Group;
    // One material per kind of part, shared by every maze, so a maze change only frees geometry.
    private readonly plate_material = new THREE.MeshStandardMaterial({ color: PLATE_COLOUR, roughness: PLATE_ROUGHNESS });
    private readonly exit_material = new THREE.MeshStandardMaterial({ color: EXIT_COLOUR });
    private readonly wall_materials: WallMaterials = create_wall_materials();
    private readonly ball: THREE.Mesh;
    private readonly ball_material: THREE.MeshStandardMaterial;
    private readonly targets: THREE.Group;
    private readonly target_line: THREE.Line;
    private view_size_mm = NO_MAZE_PLATE_MM;
    private readonly view_centre = new THREE.Vector3(); // the maze area's centre, in Three.js's frame
    private view_turn_rad = VIEW_TURNS_RAD[0];
    private has_maze = false;
    private is_stale = false;

    constructor(private readonly container: HTMLElement) {
        this.renderer = this.create_renderer();
        this.add_label_layer();
        this.controls = this.create_controls();
        this.ball_material = new THREE.MeshStandardMaterial({ color: BALL_COLOUR, metalness: BALL_METALNESS, roughness: BALL_ROUGHNESS });
        // Radius 1, scaled to the ball radius in set_maze.
        this.ball = new THREE.Mesh(new THREE.SphereGeometry(1, BALL_WIDTH_SEGMENTS, BALL_HEIGHT_SEGMENTS), this.ball_material);
        this.ball.castShadow = true;
        this.ball.visible = false;
        this.targets = this.create_targets();
        this.target_line = this.create_target_line();
        this.axes = this.create_axes();
        this.build_scene();
        this.add_reset_button();
        new ResizeObserver(() => this.fit_to_container()).observe(container);
        this.reset_view();
    }

    // Builds the plate, the walls and the exit of a new maze (vision/maze), replacing the old ones.
    set_maze(msg: Message): void {
        const maze = msg as unknown as MazeGeometry;
        this.clear_maze();
        const width_mm = maze.cols * maze.cell_size_mm;
        const depth_mm = maze.rows * maze.cell_size_mm;
        this.add_plate(maze, width_mm, depth_mm);
        for (const wall of maze_walls(maze, this.wall_materials)) this.maze_parts.add(wall);
        this.maze_parts.add(this.create_exit_marker(msg));
        this.place_axes(maze);
        this.ball.scale.setScalar((msg.ball_diameter_mm as number) / 2);
        this.has_maze = true;
        this.view_size_mm = Math.max(width_mm, depth_mm) + 2 * PLATE_MARGIN_MM;
        // The camera looks at the maze's centre: D4 puts the board origin there, but the view does not
        // rely on it (the tilt still turns about the board origin).
        this.view_centre.set(maze.origin_x_mm + width_mm / 2, maze.origin_y_mm + depth_mm / 2, 0).applyEuler(this.board_frame.rotation);
        this.view_turn_rad = view_turn_rad(maze);
        this.reset_view();
    }

    // Draws one frame. While stale the view stays frozen; only the ball's look changes (IF-02, IF-04).
    update(msg: TwinFrame): void {
        if (!this.is_stale) this.move(msg);
        this.show_ball_look(msg.ball_look);
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
        this.label_renderer.render(this.scene, this.camera);
    }

    set_stale(is_stale: boolean): void {
        this.is_stale = is_stale;
    }

    // ------------------------------------------------------------------ frame

    private move(frame: TwinFrame): void {
        // D4: tilt_x_deg = positive rotation about +y (the plate), tilt_y_deg = negative rotation
        // about +x (the middle frame). Then tilt_x_deg > 0 rolls the ball to +x, tilt_y_deg > 0 to +y.
        this.middle_frame.rotation.x = -THREE.MathUtils.degToRad(frame.tilt_y_deg);
        this.plate.rotation.y = THREE.MathUtils.degToRad(frame.tilt_x_deg);
        // Without a maze there is no plate to put them on, and the ball's size is not known yet.
        this.move_ball(this.has_maze ? frame.ball : null);
        this.show_targets(this.has_maze ? frame.target_points_mm : []);
    }

    private move_ball(ball: Message | null): void {
        this.ball.visible = ball !== null;
        if (ball === null) return;
        this.ball.position.set(ball.x_mm as number, ball.y_mm as number, this.ball.scale.x);
    }

    private show_ball_look(look: BallLook): void {
        this.ball_material.color.setHex(look === "stale" ? STALE_BALL_COLOUR : BALL_COLOUR);
        this.ball_material.opacity = BALL_OPACITY[look];
        this.ball_material.transparent = BALL_OPACITY[look] < 1;
        this.ball_material.depthWrite = !this.ball_material.transparent;
    }

    private show_targets(points_mm: ReadonlyArray<readonly number[]>): void {
        this.targets.children.forEach((target, i) => {
            target.visible = i < points_mm.length;
            if (target.visible) target.position.set(points_mm[i][0], points_mm[i][1], TARGET_RADIUS_MM);
        });
        // The line has room for MAX_TARGETS points (create_target_line); only the first count are drawn.
        const count = Math.min(points_mm.length, MAX_TARGETS);
        const positions = this.target_line.geometry.getAttribute("position") as THREE.BufferAttribute;
        for (let i = 0; i < count; i++) positions.setXYZ(i, points_mm[i][0], points_mm[i][1], TARGET_RADIUS_MM);
        positions.needsUpdate = true;
        this.target_line.geometry.setDrawRange(0, count);
        this.target_line.visible = count > 1;
    }

    // ------------------------------------------------------------------ scene set-up

    private create_renderer(): THREE.WebGLRenderer {
        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFShadowMap; // PCFSoftShadowMap is deprecated since three r186
        this.container.appendChild(renderer.domElement);
        return renderer;
    }

    // The +x / +y labels lie over the canvas; they must not catch the mouse, or the view cannot be turned.
    private add_label_layer(): void {
        const labels = this.label_renderer.domElement;
        Object.assign(labels.style, { position: "absolute", top: "0", left: "0", pointerEvents: "none" });
        this.container.appendChild(labels);
    }

    private create_controls(): OrbitControls {
        const controls = new OrbitControls(this.camera, this.renderer.domElement);
        controls.enablePan = false; // the plate always stays in the middle
        controls.maxPolarAngle = LOWEST_VIEW_ANGLE_RAD;
        return controls;
    }

    private build_scene(): void {
        this.scene.background = new THREE.Color(BACKGROUND_COLOUR);
        // A soft room light, so the steel ball looks metallic.
        const environment = new THREE.PMREMGenerator(this.renderer);
        this.scene.environment = environment.fromScene(new RoomEnvironment()).texture;
        this.scene.add(this.create_sun());
        this.board_frame.rotation.x = -Math.PI / 2; // board z (up) -> Three.js y (up)
        this.scene.add(this.board_frame);
        this.board_frame.add(this.middle_frame);
        this.middle_frame.add(this.plate);
        this.plate.add(this.maze_parts, this.axes, this.ball, this.targets, this.target_line);
    }

    // Light from the side, so the plate's shade changes with the tilt and the ball casts a shadow.
    private create_sun(): THREE.DirectionalLight {
        const sun = new THREE.DirectionalLight(LIGHT_COLOUR, LIGHT_INTENSITY);
        sun.position.copy(LIGHT_DIRECTION).setLength(LIGHT_DISTANCE_MM);
        sun.castShadow = true;
        sun.shadow.mapSize.set(SHADOW_MAP_SIZE, SHADOW_MAP_SIZE);
        Object.assign(sun.shadow.camera, { left: -SHADOW_REACH_MM, right: SHADOW_REACH_MM, top: SHADOW_REACH_MM, bottom: -SHADOW_REACH_MM });
        return sun;
    }

    private create_targets(): THREE.Group {
        const group = new THREE.Group();
        const material = new THREE.MeshStandardMaterial({ color: TARGET_COLOUR });
        const geometry = new THREE.SphereGeometry(TARGET_RADIUS_MM, TARGET_WIDTH_SEGMENTS, TARGET_HEIGHT_SEGMENTS);
        for (let i = 0; i < MAX_TARGETS; i++) group.add(new THREE.Mesh(geometry, material));
        return group;
    }

    // A line's point count is fixed when its buffer is made (Three.js keeps the first size), so the
    // buffer is made once for MAX_TARGETS points and show_targets sets how many of them are drawn.
    private create_target_line(): THREE.Line {
        const geometry = new THREE.BufferGeometry();
        const positions = new THREE.BufferAttribute(new Float32Array(MAX_TARGETS * POINT_COMPONENTS), POINT_COMPONENTS);
        positions.setUsage(THREE.DynamicDrawUsage); // rewritten on most frames
        geometry.setAttribute("position", positions);
        geometry.setDrawRange(0, 0);
        const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: TARGET_COLOUR }));
        // Its bounding sphere is computed once from the empty buffer; the points then move every frame,
        // so the line must not be skipped as "outside the view".
        line.frustumCulled = false;
        line.visible = false;
        return line;
    }

    private add_reset_button(): void {
        const button = document.createElement("button");
        button.textContent = "Reset view";
        Object.assign(button.style, { position: "absolute", top: BUTTON_MARGIN, right: BUTTON_MARGIN });
        button.addEventListener("click", () => this.reset_view());
        this.container.appendChild(button);
    }

    private reset_view(): void {
        const distance_mm = this.view_size_mm * VIEW_DISTANCE_PER_PLATE;
        this.camera.position.copy(FRONT_VIEW_DIRECTION).setLength(distance_mm).applyAxisAngle(WORLD_UP, this.view_turn_rad).add(this.view_centre);
        this.controls.target.copy(this.view_centre);
        this.controls.minDistance = this.view_size_mm * MIN_ZOOM_PER_PLATE;
        this.controls.maxDistance = this.view_size_mm * MAX_ZOOM_PER_PLATE;
        this.controls.update();
    }

    private fit_to_container(): void {
        const { clientWidth: width, clientHeight: height } = this.container;
        if (width === 0 || height === 0) return; // hidden tab
        this.renderer.setSize(width, height);
        this.label_renderer.setSize(width, height);
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
    }

    // ------------------------------------------------------------------ maze parts

    // The plate, the walls and the exit marker each have their own geometry; the materials are shared.
    private clear_maze(): void {
        for (const part of [...this.maze_parts.children]) {
            this.maze_parts.remove(part);
            if (part instanceof THREE.Mesh) part.geometry.dispose();
        }
    }

    private add_plate(maze: MazeGeometry, width_mm: number, depth_mm: number): void {
        const geometry = new THREE.BoxGeometry(width_mm + 2 * PLATE_MARGIN_MM, depth_mm + 2 * PLATE_MARGIN_MM, PLATE_THICKNESS_MM);
        const plate = new THREE.Mesh(geometry, this.plate_material);
        // Top face at z = 0, centred on the maze area.
        plate.position.set(maze.origin_x_mm + width_mm / 2, maze.origin_y_mm + depth_mm / 2, -PLATE_THICKNESS_MM / 2);
        plate.receiveShadow = true;
        this.maze_parts.add(plate);
    }

    // IF-04 gives the exit marker as a centre and a radius (exit_radius_mm), so it is drawn as a disc.
    private create_exit_marker(msg: Message): THREE.Mesh {
        const geometry = new THREE.CircleGeometry(msg.exit_radius_mm as number, EXIT_SEGMENTS);
        const marker = new THREE.Mesh(geometry, this.exit_material);
        marker.position.set(msg.exit_x_mm as number, msg.exit_y_mm as number, EXIT_MARKER_HEIGHT_MM);
        marker.receiveShadow = true;
        return marker;
    }

    // White "+x" and "+y" arrows, so the directions are clear from any view. Made once; each maze
    // only moves them (place_axes). Hidden until the first maze.
    private create_axes(): THREE.Group {
        const axes = new THREE.Group();
        for (const [name, direction] of [["+x", new THREE.Vector3(1, 0, 0)], ["+y", new THREE.Vector3(0, 1, 0)]] as const) {
            const arrow = new THREE.ArrowHelper(direction, new THREE.Vector3(), AXIS_LENGTH_MM, AXIS_COLOUR, AXIS_HEAD_MM, AXIS_HEAD_WIDTH_MM);
            const label = document.createElement("span");
            label.textContent = name;
            Object.assign(label.style, { color: `#${AXIS_COLOUR.toString(16)}`, fontSize: LABEL_FONT_SIZE });
            const label_object = new CSS2DObject(label);
            label_object.position.set(0, AXIS_LENGTH_MM + AXIS_HEAD_MM, 0); // an ArrowHelper points along its own +y
            arrow.add(label_object);
            axes.add(arrow);
        }
        axes.visible = false;
        return axes;
    }

    // At the front-left corner, on top of the outer wall, so the wall does not hide them.
    private place_axes(maze: MazeGeometry): void {
        this.axes.position.set(maze.origin_x_mm - PLATE_MARGIN_MM, maze.origin_y_mm - PLATE_MARGIN_MM, maze.wall_height_mm);
        this.axes.visible = true;
    }
}

// ------------------------------------------------------------------ first view

// The side of the plate the camera starts at: the one where the exit is far and the start cell near
// (agreed on #82). Without a start cell the plate's centre stands in for it.
function view_turn_rad(maze: MazeGeometry): number {
    const [start_x_mm, start_y_mm] = maze.start_cell === null
        ? [maze.origin_x_mm + maze.cols * maze.cell_size_mm / 2, maze.origin_y_mm + maze.rows * maze.cell_size_mm / 2]
        : cell_centre_mm(maze, maze.start_cell.row, maze.start_cell.col);
    const start_to_exit = new THREE.Vector2(maze.exit_x_mm - start_x_mm, maze.exit_y_mm - start_y_mm);
    let best_turn_rad = VIEW_TURNS_RAD[0];
    let best_depth_mm = -Infinity;
    for (const turn_rad of VIEW_TURNS_RAD) {
        // How far the exit lies behind the start, seen from the camera at this side.
        const depth_mm = -start_to_exit.dot(camera_side(turn_rad));
        if (depth_mm > best_depth_mm) [best_turn_rad, best_depth_mm] = [turn_rad, depth_mm];
    }
    return best_turn_rad;
}

// Board-frame direction from the plate towards the camera after a turn of FRONT_VIEW_DIRECTION.
// Three.js turns world +z (the board's -y side) by turn_rad about +y; world x is board x, world z is board -y.
function camera_side(turn_rad: number): THREE.Vector2 {
    return new THREE.Vector2(Math.sin(turn_rad), -Math.cos(turn_rad));
}

// ------------------------------------------------------------------ walls

interface WallMaterials {
    inner: THREE.MeshStandardMaterial;
    outer: THREE.MeshStandardMaterial;
}

function create_wall_materials(): WallMaterials {
    const outer = new THREE.MeshStandardMaterial({ color: OUTER_WALL_COLOUR, roughness: WALL_ROUGHNESS });
    // An inner wall's end lies inside the outer wall, and their tops are at the same height. Without
    // this offset the two tops flicker into white dots; the outer wall is drawn in front there.
    outer.polygonOffset = true;
    outer.polygonOffsetFactor = OUTER_WALL_DEPTH_OFFSET;
    outer.polygonOffsetUnits = OUTER_WALL_DEPTH_OFFSET;
    return { inner: new THREE.MeshStandardMaterial({ color: INNER_WALL_COLOUR, roughness: WALL_ROUGHNESS }), outer };
}

// Every wall of the maze once; an inner wall is flagged in both neighbouring cells (IF-04).
function maze_walls(maze: MazeGeometry, materials: WallMaterials): THREE.Mesh[] {
    const walls = new Map<string, THREE.Mesh>();
    for (let row = 0; row < maze.rows; row++) {
        for (let col = 0; col < maze.cols; col++) {
            for (const { side, bit } of WALL_BITS) {
                if ((maze.walls[row][col] & bit) === 0) continue;
                const wall = create_wall(maze, row, col, side, materials);
                const key = `${wall.position.x.toFixed(WALL_KEY_DECIMALS)},${wall.position.y.toFixed(WALL_KEY_DECIMALS)}`;
                walls.set(key, wall);
            }
        }
    }
    return [...walls.values()];
}

function create_wall(maze: MazeGeometry, row: number, col: number, side: WallSide, materials: WallMaterials): THREE.Mesh {
    const is_outer = is_outer_wall(maze, row, col, side);
    const thickness_mm = is_outer ? OUTER_WALL_THICKNESS_MM : maze.wall_thickness_mm;
    // A wall is one cell long plus its thickness, so walls meeting at a corner close it.
    const length_mm = maze.cell_size_mm + thickness_mm;
    const is_along_x = side === "n" || side === "s";
    const geometry = new THREE.BoxGeometry(is_along_x ? length_mm : thickness_mm, is_along_x ? thickness_mm : length_mm, maze.wall_height_mm);
    const wall = new THREE.Mesh(geometry, is_outer ? materials.outer : materials.inner);
    const [x_mm, y_mm] = wall_centre_mm(maze, row, col, side, is_outer);
    wall.position.set(x_mm, y_mm, maze.wall_height_mm / 2);
    wall.castShadow = true;
    wall.receiveShadow = true;
    return wall;
}

function is_outer_wall(maze: MazeGeometry, row: number, col: number, side: WallSide): boolean {
    return (side === "n" && row === maze.rows - 1) || (side === "s" && row === 0)
        || (side === "e" && col === maze.cols - 1) || (side === "w" && col === 0);
}

// The centre of a wall on a cell edge. An outer wall is thicker, but its inner face is where an
// inner wall's face would be, so it grows outwards (mechanical design v4).
function wall_centre_mm(maze: MazeGeometry, row: number, col: number, side: WallSide, is_outer: boolean): [number, number] {
    const [centre_x_mm, centre_y_mm] = cell_centre_mm(maze, row, col);
    const outward_shift_mm = is_outer ? (OUTER_WALL_THICKNESS_MM - maze.wall_thickness_mm) / 2 : 0;
    const to_edge_mm = maze.cell_size_mm / 2 + outward_shift_mm;
    const offsets_mm = { n: [0, to_edge_mm], e: [to_edge_mm, 0], s: [0, -to_edge_mm], w: [-to_edge_mm, 0] };
    const [offset_x_mm, offset_y_mm] = offsets_mm[side];
    return [centre_x_mm + offset_x_mm, centre_y_mm + offset_y_mm];
}

// IF-04: "Only the shared helper (shared/mazes/) computes it." That helper (MazeGrid.cell_centre_mm)
// is Python only; this is the same formula in TypeScript. Open question on #82, to add it to shared/.
function cell_centre_mm(maze: MazeGeometry, row: number, col: number): [number, number] {
    return [
        maze.origin_x_mm + (col + CELL_CENTRE_OFFSET_CELLS) * maze.cell_size_mm,
        maze.origin_y_mm + (row + CELL_CENTRE_OFFSET_CELLS) * maze.cell_size_mm,
    ];
}
