import dataclasses
import json
from pathlib import Path

import pytest

from shared.interfaces import ValidationError, validate_file
from shared.mazes import MazeGrid

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = ROOT / "shared/interfaces/examples/maze_file.json"


def example_fields():
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def write_fields(tmp_path, fields):
    path = tmp_path / "maze.json"
    path.write_text(json.dumps(fields), encoding="utf-8")
    return str(path)


def wide_maze():
    # 2 rows x 3 columns of 25 mm cells centred on the board origin; the walls do not matter for the cell geometry
    return dataclasses.replace(MazeGrid.load(str(EXAMPLE_PATH)), rows=2, cols=3, cell_size_mm=25.0,
                               origin_x_mm=-37.5, origin_y_mm=-25.0, walls=((0, 0, 0), (0, 0, 0)))


def test_load_example_file_gives_every_field():
    maze = MazeGrid.load(str(EXAMPLE_PATH))
    assert maze.maze_id == "example-2x2"
    assert maze.cell_size_mm == 40.0
    assert maze.rows == 2
    assert maze.cols == 2
    assert maze.origin_x_mm == -40.0
    assert maze.origin_y_mm == -40.0
    assert maze.walls == ((14, 14), (9, 3))
    assert maze.wall_thickness_mm == 4.0
    assert maze.wall_height_mm == 10.0
    assert maze.start_cell == (0, 0)
    assert maze.exit_cell == (0, 1)
    assert maze.exit_x_mm == 20.0
    assert maze.exit_y_mm == -20.0
    assert maze.exit_radius_mm == 8.0
    assert maze.ball_diameter_mm == 12.0


def test_load_without_start_cell_field_gives_none(tmp_path):
    fields = example_fields()
    del fields["start_cell"]
    assert MazeGrid.load(write_fields(tmp_path, fields)).start_cell is None


def test_load_with_null_start_cell_gives_none(tmp_path):
    fields = example_fields()
    fields["start_cell"] = None
    assert MazeGrid.load(write_fields(tmp_path, fields)).start_cell is None


def test_load_rejects_unknown_field(tmp_path):
    fields = example_fields()
    fields["extra"] = 1
    with pytest.raises(ValidationError):
        MazeGrid.load(write_fields(tmp_path, fields))


def test_load_rejects_missing_required_field(tmp_path):
    fields = example_fields()
    del fields["exit_cell"]
    with pytest.raises(ValidationError):
        MazeGrid.load(write_fields(tmp_path, fields))


def test_save_then_load_gives_the_same_maze(tmp_path):
    maze = MazeGrid.load(str(EXAMPLE_PATH))
    path = str(tmp_path / "saved.json")
    maze.save(path)
    assert MazeGrid.load(path) == maze


def test_save_then_load_keeps_a_missing_start_cell(tmp_path):
    fields = example_fields()
    fields["start_cell"] = None
    maze = MazeGrid.load(write_fields(tmp_path, fields))
    path = str(tmp_path / "saved.json")
    maze.save(path)
    assert MazeGrid.load(path) == maze


def test_saved_file_is_valid_and_writes_start_cell_null(tmp_path):
    fields = example_fields()
    fields["start_cell"] = None
    path = str(tmp_path / "saved.json")
    MazeGrid.load(write_fields(tmp_path, fields)).save(path)
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_file("maze_file", saved)
    assert "start_cell" in saved
    assert saved["start_cell"] is None


def test_saved_file_uses_lf_line_endings_and_ends_with_one_newline(tmp_path):
    path = tmp_path / "saved.json"
    MazeGrid.load(str(EXAMPLE_PATH)).save(str(path))
    data = path.read_bytes()
    assert b"\r" not in data
    assert data.endswith(b"}\n")


def test_cell_centre_of_the_example_exit_cell_is_the_exit_marker():
    maze = MazeGrid.load(str(EXAMPLE_PATH))
    assert maze.cell_centre_mm(0, 1) == (20.0, -20.0)


@pytest.mark.parametrize("row,col,centre_mm", [
    (0, 0, (-25.0, -12.5)),
    (0, 2, (25.0, -12.5)),
    (1, 0, (-25.0, 12.5)),
    (1, 1, (0.0, 12.5)),
])
def test_cell_centre_uses_the_column_for_x_and_the_row_for_y(row, col, centre_mm):
    assert wide_maze().cell_centre_mm(row, col) == centre_mm


@pytest.mark.parametrize("x_mm,y_mm,cell", [
    (30.0, -10.0, (0, 2)),
    (-30.0, 10.0, (1, 0)),
    (-37.5, -25.0, (0, 0)),  # the origin corner belongs to cell (0, 0)
    (-12.5, 0.0, (1, 1)),    # a point on a shared edge belongs to the cell on the +x / +y side
])
def test_cell_of_a_point_inside_the_grid(x_mm, y_mm, cell):
    assert wide_maze().cell_of(x_mm, y_mm) == cell


@pytest.mark.parametrize("x_mm,y_mm", [
    (-37.6, 0.0),   # just outside the -x border
    (37.5, 0.0),    # the +x border itself
    (0.0, -25.1),   # just outside the -y border
    (0.0, 25.0),    # the +y border itself
])
def test_cell_of_a_point_outside_the_grid_is_none(x_mm, y_mm):
    assert wide_maze().cell_of(x_mm, y_mm) is None


def test_cell_of_finds_every_cell_from_its_centre():
    maze = wide_maze()
    for row in range(maze.rows):
        for col in range(maze.cols):
            assert maze.cell_of(*maze.cell_centre_mm(row, col)) == (row, col)
