// Message shapes GameManager reads and writes. Field names follow shared/interfaces/schemas/*.schema.json;
// the bus helper validates every message against those schemas, so these types only describe them.

import type {
  Command,
  EditReason,
  EditState,
  Fault,
  MazeSource,
  Mode,
  PlatformSource,
  ReplaySpeed,
  Result,
  RouteStatus,
  State,
  WarningKind,
  Writer,
} from "../../shared/topics";

export interface Envelope {
  timestamp_s: number;
  seq: number;
  version: number;
  writer: Writer;
}

export interface Cell {
  row: number;
  col: number;
}

/** vision/ball (IF-04) */
export interface BallMsg extends Envelope {
  x_mm: number;
  y_mm: number;
  vx_mm_s: number;
  vy_mm_s: number;
  is_visible: boolean;
  is_predicted: boolean;
  is_on_exit: boolean;
  frame_age_ms: number;
  meas_x_mm: number | null;
  meas_y_mm: number | null;
}

/** vision/maze (IF-04) */
export interface MazeMsg extends Envelope {
  maze_id: string;
  source: MazeSource;
  cell_size_mm: number;
  rows: number;
  cols: number;
  origin_x_mm: number;
  origin_y_mm: number;
  walls: number[][];
  wall_thickness_mm: number;
  wall_height_mm: number;
  start_cell: Cell | null;
  exit_cell: Cell;
  exit_x_mm: number;
  exit_y_mm: number;
  exit_radius_mm: number;
  ball_diameter_mm: number;
}

/** plan/distance_map (IF-04) */
export interface DistanceMapMsg extends Envelope {
  maze_id: string;
  rows: number;
  cols: number;
  steps: number[][];
}

/** plan/route (IF-04) */
export interface RouteMsg extends Envelope {
  maze_id: string;
  ball_seq: number;
  status: RouteStatus;
  ball_cell: Cell | null;
  target_points_mm: number[][];
  distance_to_exit_cells: number | null;
}

/** vision/edit_state (IF-04) */
export interface EditStateMsg extends Envelope {
  state: EditState;
  maze_id: string | null;
  game_id: string | null;
  reason: EditReason | null;
}

/** platform/state (IF-02) */
export interface PlatformStateMsg extends Envelope {
  tilt_x_deg: number;
  tilt_y_deg: number;
  applied_tilt_x_deg: number;
  applied_tilt_y_deg: number;
  source: PlatformSource;
  mode: Mode;
  mode_button_presses: number;
  is_e_stop: boolean;
  is_laptop_connected: boolean;
  is_glove_connected: boolean;
  fault: Fault;
}

/** glove/state (IF-02) */
export interface GloveStateMsg extends Envelope {
  hand_tilt_x_deg: number;
  hand_tilt_y_deg: number;
  ax_m_s2: number;
  ay_m_s2: number;
  az_m_s2: number;
  gx_deg_s: number;
  gy_deg_s: number;
  gz_deg_s: number;
  battery_pct: number;
  rssi_dbm: number;
  is_calibrated: boolean;
  is_connected: boolean;
  firmware_version: number;
}

/** cs/command (IF-07) */
export interface CommandMsg extends Envelope {
  cmd: Command;
  mode: Mode | null;
  file: string | null;
  speed: ReplaySpeed | null;
}

/** cs/variables/game (IF-07): one entry per changed variable. */
export type VariablesMsg = Envelope & Record<string, unknown>;

/** game/state fields without the envelope (IF-05). */
export interface GameStateFields {
  state: State;
  mode: Mode;
  game_id: string | null;
  maze_id: string | null;
  elapsed_s: number;
  cell: Cell | null;
  distance_to_exit_cells: number | null;
  progress_pct: number;
  result: Result;
}

/** game/state as received, e.g. the retained message of a previous run. */
export type GameStateMsg = Envelope & GameStateFields;

/** game/warning fields without the envelope (IF-05). */
export interface GameWarningFields {
  kind: WarningKind;
  intensity_pct: number;
}
