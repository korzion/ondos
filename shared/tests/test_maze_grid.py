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
