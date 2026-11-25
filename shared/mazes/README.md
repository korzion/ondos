# shared/mazes

Maze files `<maze_id>.json` and the MazeGrid helper: format, consistency check, cell centres, distance map and route function (IF-04). Owner: C. Used by C at runtime and by D in training.

## Maze files

A maze file has exactly the fields of `shared/interfaces/schemas/maze_file.schema.json`; `shared/interfaces/examples/maze_file.json` is a small valid one. `start_cell` may be left out or null.

## Python

```python
from shared.mazes import MazeGrid, build_distance_map, plan_route

maze = MazeGrid.load("shared/interfaces/examples/maze_file.json")
maze.validate()                               # True: closed borders, agreeing neighbour flags, start and exit in place
print(maze.to_ascii())                        # far row on top: # wall, . open, x start cell, E exit cell
steps = build_distance_map(maze)              # once per maze: steps[row][col] to the exit, -1 = no path
route = plan_route(maze, steps, -20.0, -20.0) # for every ball sample (x_mm, y_mm in the board frame)
route.status, route.ball_cell, route.target_points_mm, route.distance_to_exit_cells
```

Rules of the route (IF-04):

- From each cell the route steps to the open neighbour with the smallest distance; equal distances are decided in the order N, E, S, W.
- `target_points_mm` holds the next cell centres, up to 3. In the exit cell the only point is the centre of the exit marker.
- A ball cell without a path to the exit gives `no_path`, with no points and no distance.
- `maze_id` and `ball_seq` are not in `Route`; the publisher of `plan/route` adds them.

Starting decisions, where the design document leaves a detail open:

- Cells are `(row, col)` tuples in the code and `{row, col}` objects in the maze file and in the messages.
- A point on the edge between two cells belongs to the cell on the +x / +y side. `cell_of` gives `None` for a point outside the grid or on the outer +x / +y border, and the route is then `invalid`.
- Near the exit `target_points_mm` has fewer than 3 points; it is not padded.
- `validate()` writes the first problem it finds to the log as a warning.
- `build_distance_map` refuses a maze that is not valid (`ValueError`); `plan_route` expects the distance map of the same maze.
- `to_ascii()` draws 2 x rows + 1 lines of 2 x cols + 1 characters; a corner that no wall touches stays open.

Tests: `python -m pytest shared/tests/test_maze_grid.py shared/tests/test_maze_planning.py`
