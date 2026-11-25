"""MazeGrid (C.5): the maze file (IF-04) as an immutable object, with load and save."""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from shared.interfaces import validate_file

log = logging.getLogger(__name__)

JSON_INDENT_SPACES = 2
CELL_CENTRE_OFFSET_CELLS = 0.5  # a cell centre is half a cell from the cell's origin corner (IF-04)

# wall bit flags of a cell (IF-04)
WALL_N = 1  # +y side
WALL_E = 2  # +x side
WALL_S = 4  # -y side
WALL_W = 8  # -x side
ALL_WALLS = WALL_N | WALL_E | WALL_S | WALL_W

# (wall flag, row step, col step) to the neighbour on that side, in the order N, E, S, W.
# The route breaks ties in this order, so every maze and ball cell has exactly one route (IF-04).
NEIGHBOUR_STEPS = ((WALL_N, 1, 0), (WALL_E, 0, 1), (WALL_S, -1, 0), (WALL_W, 0, -1))

# to_ascii(): every cell is one character, with one character for the wall between two cells
ASCII_CELL_STEP = 2
ASCII_BORDER = 1              # the outer border takes one character before the first cell
ASCII_WALL_SPAN = (-1, 0, 1)  # a wall fills its own character and the corner at each of its two ends
ASCII_WALL = "#"
ASCII_OPEN = "."
ASCII_START = "x"
ASCII_EXIT = "E"

Cell = tuple[int, int]  # (row, col)


@dataclass(frozen=True)
class MazeGrid:
    """A maze as stored in shared/mazes/<maze_id>.json; walls[row][col] holds the wall bit flags of a cell."""

    maze_id: str
    cell_size_mm: float
    rows: int
    cols: int
    origin_x_mm: float
    origin_y_mm: float
    walls: tuple[tuple[int, ...], ...]
    wall_thickness_mm: float
    wall_height_mm: float
    start_cell: Cell | None
    exit_cell: Cell
    exit_x_mm: float
    exit_y_mm: float
    exit_radius_mm: float
    ball_diameter_mm: float

    @classmethod
    def load(cls, path: str) -> MazeGrid:
        fields = json.loads(Path(path).read_text(encoding="utf-8"))
        validate_file("maze_file", fields)
        return cls(
            maze_id=fields["maze_id"],
            cell_size_mm=float(fields["cell_size_mm"]),
            rows=int(fields["rows"]),
            cols=int(fields["cols"]),
            origin_x_mm=float(fields["origin_x_mm"]),
            origin_y_mm=float(fields["origin_y_mm"]),
            walls=tuple(tuple(int(w) for w in row) for row in fields["walls"]),
            wall_thickness_mm=float(fields["wall_thickness_mm"]),
            wall_height_mm=float(fields["wall_height_mm"]),
            start_cell=_cell_from_json(fields.get("start_cell")),
            exit_cell=_cell_from_json(fields["exit_cell"]),
            exit_x_mm=float(fields["exit_x_mm"]),
            exit_y_mm=float(fields["exit_y_mm"]),
            exit_radius_mm=float(fields["exit_radius_mm"]),
            ball_diameter_mm=float(fields["ball_diameter_mm"]),
        )

    def save(self, path: str) -> None:
        text = json.dumps(self._to_json(), indent=JSON_INDENT_SPACES) + "\n"
        # newline="\n" keeps LF on Windows too, so the file is byte-identical on every machine
        Path(path).write_text(text, encoding="utf-8", newline="\n")

    def validate(self) -> bool:
        """True when the maze is consistent: closed outer borders, agreeing neighbour flags, start and exit in place."""
        checks = (
            (self._has_grid_shape, "walls is not a rows x cols grid of wall flags"),
            (self._has_closed_borders, "an outer border is open"),
            (self._has_agreeing_neighbours, "two neighbour cells disagree about the wall between them"),
            (self._has_start_and_exit_in_place, "start_cell or exit_cell is outside the grid, or they are equal"),
            (self._has_exit_marker_in_exit_cell, "the centre of the exit marker is not inside exit_cell"),
        )
        for is_ok, problem in checks:
            if not is_ok():
                log.warning("maze %s is not valid: %s", self.maze_id, problem)
                return False  # the later checks index walls and need the earlier ones to hold
        return True

    def cell_centre_mm(self, row: int, col: int) -> tuple[float, float]:
        """Centre of a cell in the board frame: columns run along +x, rows along +y."""
        x_mm = self.origin_x_mm + (col + CELL_CENTRE_OFFSET_CELLS) * self.cell_size_mm
        y_mm = self.origin_y_mm + (row + CELL_CENTRE_OFFSET_CELLS) * self.cell_size_mm
        return (x_mm, y_mm)

    def cell_of(self, x_mm: float, y_mm: float) -> Cell | None:
        """Cell that contains a board-frame point, or None outside the grid."""
        # ASSUMPTION: C.5 gives the result as (row, col) and does not say what a point outside the grid gives.
        # None is returned there, so that a caller cannot plan from a wrong cell.
        # floor, not int(): a point just outside the -x or -y border must not round into row or column 0
        row = math.floor((y_mm - self.origin_y_mm) / self.cell_size_mm)
        col = math.floor((x_mm - self.origin_x_mm) / self.cell_size_mm)
        if not self._is_in_grid((row, col)):
            return None
        return (row, col)

    def to_ascii(self) -> str:
        """Text drawing of the maze, far (+y) row on top: # wall, . open, x start cell, E exit cell."""
        text_rows = ASCII_CELL_STEP * self.rows + ASCII_BORDER
        text_cols = ASCII_CELL_STEP * self.cols + ASCII_BORDER
        text = [[ASCII_OPEN] * text_cols for _ in range(text_rows)]
        for row in range(self.rows):
            for col in range(self.cols):
                self._draw_cell_walls(text, (row, col))
        if self.start_cell is not None:
            self._draw_mark(text, self.start_cell, ASCII_START)
        self._draw_mark(text, self.exit_cell, ASCII_EXIT)
        return "\n".join("".join(line) for line in text)

    def _is_in_grid(self, cell: Cell) -> bool:
        row, col = cell
        return 0 <= row < self.rows and 0 <= col < self.cols

    def _has_grid_shape(self) -> bool:
        if len(self.walls) != self.rows:
            return False
        for row_flags in self.walls:
            if len(row_flags) != self.cols:
                return False
            if any(not 0 <= flags <= ALL_WALLS for flags in row_flags):
                return False
        return True

    def _has_closed_borders(self) -> bool:
        last_row, last_col = self.rows - 1, self.cols - 1
        for col in range(self.cols):
            if not self.walls[0][col] & WALL_S or not self.walls[last_row][col] & WALL_N:
                return False
        for row in range(self.rows):
            if not self.walls[row][0] & WALL_W or not self.walls[row][last_col] & WALL_E:
                return False
        return True

    def _has_agreeing_neighbours(self) -> bool:
        for row in range(self.rows):
            for col in range(self.cols):
                flags = self.walls[row][col]
                if col + 1 < self.cols and bool(flags & WALL_E) != bool(self.walls[row][col + 1] & WALL_W):
                    return False
                if row + 1 < self.rows and bool(flags & WALL_N) != bool(self.walls[row + 1][col] & WALL_S):
                    return False
        return True

    def _has_start_and_exit_in_place(self) -> bool:
        if not self._is_in_grid(self.exit_cell):
            return False
        if self.start_cell is None:  # the start cell may be unknown until the game starts (IF-04)
            return True
        return self._is_in_grid(self.start_cell) and self.start_cell != self.exit_cell

    def _has_exit_marker_in_exit_cell(self) -> bool:
        return self.cell_of(self.exit_x_mm, self.exit_y_mm) == self.exit_cell

    def _text_position(self, cell: Cell) -> tuple[int, int]:
        row, col = cell
        # the far row is the first line of the text, so a higher row is a lower text row
        return (ASCII_CELL_STEP * (self.rows - 1 - row) + ASCII_BORDER, ASCII_CELL_STEP * col + ASCII_BORDER)

    def _draw_cell_walls(self, text: list[list[str]], cell: Cell) -> None:
        row, col = cell
        text_row, text_col = self._text_position(cell)
        for flag, row_step, col_step in NEIGHBOUR_STEPS:
            if not self.walls[row][col] & flag:
                continue
            for along in ASCII_WALL_SPAN:
                wall_row = text_row - row_step + along * abs(col_step)
                wall_col = text_col + col_step + along * abs(row_step)
                text[wall_row][wall_col] = ASCII_WALL

    def _draw_mark(self, text: list[list[str]], cell: Cell, mark: str) -> None:
        text_row, text_col = self._text_position(cell)
        text[text_row][text_col] = mark

    def _to_json(self) -> dict:
        return {
            "maze_id": self.maze_id,
            "cell_size_mm": self.cell_size_mm,
            "rows": self.rows,
            "cols": self.cols,
            "origin_x_mm": self.origin_x_mm,
            "origin_y_mm": self.origin_y_mm,
            "walls": [list(row) for row in self.walls],
            "wall_thickness_mm": self.wall_thickness_mm,
            "wall_height_mm": self.wall_height_mm,
            "start_cell": _cell_to_json(self.start_cell),
            "exit_cell": _cell_to_json(self.exit_cell),
            "exit_x_mm": self.exit_x_mm,
            "exit_y_mm": self.exit_y_mm,
            "exit_radius_mm": self.exit_radius_mm,
            "ball_diameter_mm": self.ball_diameter_mm,
        }


def _cell_from_json(cell: dict | None) -> Cell | None:
    if cell is None:
        return None
    return (int(cell["row"]), int(cell["col"]))


def _cell_to_json(cell: Cell | None) -> dict | None:
    if cell is None:
        return None
    return {"row": cell[0], "col": cell[1]}
