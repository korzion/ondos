// npm test: the TypeScript maze helper against the IF-04 examples and small hand-made mazes.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cellCentreMm, nextCell, pathToExit, type Cell, type MazeGeometry } from "./mazes";

const INTERFACES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "interfaces", "examples");
const EXAMPLES = JSON.parse(readFileSync(join(INTERFACES_DIR, "messages.json"), "utf8")).examples as
    { topic: string; msg: Record<string, unknown> }[];
const MAZE_FILE = JSON.parse(readFileSync(join(INTERFACES_DIR, "maze_file.json"), "utf8")) as MazeGeometry;

function example(topic: string): Record<string, unknown> {
    return EXAMPLES.find((e) => e.topic === topic)!.msg;
}

const EXAMPLE_MAZE = example("vision/maze") as unknown as MazeGeometry;
const EXAMPLE_STEPS = example("plan/distance_map").steps as number[][];

// 3 x 3 cells without inner walls (as open_room() in test_maze_planning.py), exit in cell (0, 2).
const OPEN_ROOM: MazeGeometry = {
    rows: 3, cols: 3, cell_size_mm: 40, origin_x_mm: -60, origin_y_mm: -60,
    walls: [[12, 4, 6], [8, 0, 2], [9, 1, 3]],
};
const OPEN_ROOM_EXIT: Cell = { row: 0, col: 2 };
// Without inner walls the distance to the exit is the number of rows plus the number of columns between.
const OPEN_ROOM_STEPS = [0, 1, 2].map((row) => [0, 1, 2].map((col) =>
    Math.abs(row - OPEN_ROOM_EXIT.row) + Math.abs(col - OPEN_ROOM_EXIT.col)));

test("cell centre is half a cell from the cell's origin corner", () => {
    // maze_file.json: origin (-40, -40), 40 mm cells; its exit cell (0, 1) holds the exit marker at (20, -20).
    assert.deepEqual(cellCentreMm(MAZE_FILE, { row: 0, col: 1 }), [20, -20]);
    assert.deepEqual(cellCentreMm(MAZE_FILE, { row: 1, col: 0 }), [-20, 20]);
});

test("path from the start of the example maze gives the points of the example route", () => {
    const route = example("plan/route");
    const path = pathToExit(EXAMPLE_MAZE, EXAMPLE_STEPS, route.ball_cell as Cell);
    // The route's points are the centres of the next cells (up to 3) after the ball cell.
    const points = path.slice(1, 4).map((cell) => cellCentreMm(EXAMPLE_MAZE, cell));
    assert.deepEqual(points, route.target_points_mm);
});

test("equal distances are decided in the order N, E, S, W", () => {
    // From the far left cell (2, 0) east and south are both 3 steps from the exit; east comes first.
    assert.deepEqual(nextCell(OPEN_ROOM, OPEN_ROOM_STEPS, { row: 2, col: 0 }), { row: 2, col: 1 });
    assert.deepEqual(pathToExit(OPEN_ROOM, OPEN_ROOM_STEPS, { row: 2, col: 0 }), [
        { row: 2, col: 0 }, { row: 2, col: 1 }, { row: 2, col: 2 }, { row: 1, col: 2 }, { row: 0, col: 2 },
    ]);
});

test("path from the exit cell is only the exit cell", () => {
    assert.deepEqual(pathToExit(OPEN_ROOM, OPEN_ROOM_STEPS, OPEN_ROOM_EXIT), [OPEN_ROOM_EXIT]);
});

test("no path from a cell without a path, outside the grid or on a map of another maze", () => {
    // Column 0 closed on all sides (as maze_with_closed_cells() in test_maze_planning.py).
    const closed: MazeGeometry = { ...EXAMPLE_MAZE, walls: [[15, 14], [15, 11]] };
    assert.deepEqual(pathToExit(closed, [[-1, 0], [-1, 1]], { row: 0, col: 0 }), []);
    assert.deepEqual(pathToExit(OPEN_ROOM, OPEN_ROOM_STEPS, { row: 3, col: 0 }), []);
    // A map that does not fit the example maze: from (1, 0) with 3 steps the next cell (1, 1) has 1, not 2.
    assert.deepEqual(pathToExit(EXAMPLE_MAZE, [[3, 0], [3, 1]], { row: 1, col: 0 }), []);
});

test("no path, and no error, on a map of another size or a maze with an open outer border", () => {
    // The 2 x 2 example map on the 3 x 3 open room, and the other way round.
    assert.deepEqual(pathToExit(OPEN_ROOM, EXAMPLE_STEPS, { row: 0, col: 0 }), []);
    assert.deepEqual(pathToExit(EXAMPLE_MAZE, OPEN_ROOM_STEPS, { row: 0, col: 0 }), []);
    // Cell (0, 0) of the example maze without its south wall: the step south would leave the grid.
    const open_border: MazeGeometry = { ...EXAMPLE_MAZE, walls: [[10, 14], [9, 3]] };
    assert.deepEqual(pathToExit(open_border, [[3, 0], [2, 1]], { row: 0, col: 0 }),
        pathToExit(EXAMPLE_MAZE, EXAMPLE_STEPS, { row: 0, col: 0 }));
});
