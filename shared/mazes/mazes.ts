// The maze helper for TypeScript readers of vision/maze and plan/distance_map (IF-04): the same rules as
// maze_grid.py (cell centre, wall flags) and planning.py (next cell towards the exit), so the Control
// Station's 2D maze view and 3D Twin draw what C computes. Owner: C (shared/mazes/).
// Only what a reader needs; loading, checking and the distance map itself stay in Python.

const CELL_CENTRE_OFFSET_CELLS = 0.5; // a cell centre is half a cell from the cell's origin corner (IF-04)

// wall bit flags of a cell (IF-04)
export const WALL_N = 1; // +y side
export const WALL_E = 2; // +x side
export const WALL_S = 4; // -y side
export const WALL_W = 8; // -x side

// plan/distance_map: no path from this cell to the exit
export const UNREACHABLE_STEPS = -1;

export interface Cell {
    row: number;
    col: number;
}

// The fields of vision/maze (or a maze file) these functions read.
export interface MazeGeometry {
    rows: number;
    cols: number;
    cell_size_mm: number;
    origin_x_mm: number;
    origin_y_mm: number;
    walls: number[][];
}

// The neighbour on each side, in the order N, E, S, W. The route breaks ties in this order, so every
// maze and ball cell has exactly one route (IF-04; NEIGHBOUR_STEPS in maze_grid.py).
export const NEIGHBOUR_STEPS: ReadonlyArray<{ wall: number; row_step: number; col_step: number }> = [
    { wall: WALL_N, row_step: 1, col_step: 0 },
    { wall: WALL_E, row_step: 0, col_step: 1 },
    { wall: WALL_S, row_step: -1, col_step: 0 },
    { wall: WALL_W, row_step: 0, col_step: -1 },
];

/** Centre of a cell in the board frame: columns run along +x, rows along +y (MazeGrid.cell_centre_mm). */
export function cellCentreMm(maze: MazeGeometry, cell: Cell): [number, number] {
    return [
        maze.origin_x_mm + (cell.col + CELL_CENTRE_OFFSET_CELLS) * maze.cell_size_mm,
        maze.origin_y_mm + (cell.row + CELL_CENTRE_OFFSET_CELLS) * maze.cell_size_mm,
    ];
}

export function hasWall(maze: MazeGeometry, cell: Cell, wall: number): boolean {
    return (maze.walls[cell.row][cell.col] & wall) !== 0;
}

export function isInGrid(maze: MazeGeometry, cell: Cell): boolean {
    return cell.row >= 0 && cell.row < maze.rows && cell.col >= 0 && cell.col < maze.cols;
}

function openNeighbours(maze: MazeGeometry, cell: Cell): Cell[] {
    return NEIGHBOUR_STEPS
        .filter(({ wall }) => !hasWall(maze, cell, wall))
        .map(({ row_step, col_step }) => ({ row: cell.row + row_step, col: cell.col + col_step }));
}

/**
 * The open neighbour with the smallest distance; equal distances are decided in the order N, E, S, W
 * (planning._next_cell). null when no open neighbour has a path to the exit.
 */
export function nextCell(maze: MazeGeometry, steps: number[][], cell: Cell): Cell | null {
    let next: Cell | null = null;
    for (const neighbour of openNeighbours(maze, cell)) {
        const neighbour_steps = steps[neighbour.row][neighbour.col];
        if (neighbour_steps === UNREACHABLE_STEPS) continue;
        // strictly smaller only: with equal distances the earlier side in N, E, S, W keeps its place
        if (next === null || neighbour_steps < steps[next.row][next.col]) next = neighbour;
    }
    return next;
}

/**
 * The cells from `start` to the exit, both included, following the distance map with the route's rule.
 * Empty when `start` is outside the grid or has no path, or when the map does not lead to the exit
 * (e.g. a map of another maze), so a reader never draws a wrong path.
 */
export function pathToExit(maze: MazeGeometry, steps: number[][], start: Cell): Cell[] {
    if (!isInGrid(maze, start) || steps[start.row][start.col] === UNREACHABLE_STEPS) return [];
    const path = [start];
    let cell = start;
    while (steps[cell.row][cell.col] > 0) {
        const next = nextCell(maze, steps, cell);
        // Every step must come one closer to the exit, which also ends the loop on a broken map.
        if (next === null || steps[next.row][next.col] !== steps[cell.row][cell.col] - 1) return [];
        path.push(next);
        cell = next;
    }
    return path;
}
