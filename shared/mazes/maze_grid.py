"""MazeGrid (C.5): the maze file (IF-04) as an immutable object, with load and save."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from shared.interfaces import validate_file

JSON_INDENT_SPACES = 2
CELL_CENTRE_OFFSET_CELLS = 0.5  # a cell centre is half a cell from the cell's origin corner (IF-04)

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

    def cell_centre_mm(self, row: int, col: int) -> tuple[float, float]:
        """Centre of a cell in the board frame: columns run along +x, rows along +y."""
        x_mm = self.origin_x_mm + (col + CELL_CENTRE_OFFSET_CELLS) * self.cell_size_mm
        y_mm = self.origin_y_mm + (row + CELL_CENTRE_OFFSET_CELLS) * self.cell_size_mm
        return (x_mm, y_mm)

    def cell_of(self, x_mm: float, y_mm: float) -> Cell | None:
        """Cell that contains a board-frame point, or None outside the grid."""
        # floor, not int(): a point just outside the -x or -y border must not round into row or column 0
        row = math.floor((y_mm - self.origin_y_mm) / self.cell_size_mm)
        col = math.floor((x_mm - self.origin_x_mm) / self.cell_size_mm)
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return None
        return (row, col)

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
