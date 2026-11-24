// Control variables of the game key (E.7, IF-07): start values, limits, clamping and game/variables_spec.
// Names come from shared/interfaces/variables.json (key "game"); the bus helper rejects any other name.

export interface GameVariables {
  not_moving_time_s: number;
  not_moving_radius_mm: number;
  away_hold_time_s: number;
  warning_cooldown_s: number;
  ball_lost_pause_s: number;
  glove_lost_pause_s: number;
  exit_hold_frames: number;
  /** 0 = no time limit (ASSUMPTION: a spec value cannot be null, so "off" is 0). */
  time_limit_s: number;
}

type VariableName = keyof GameVariables;

interface NumberVariableSpec {
  name: VariableName;
  default: number;
  min: number;
  max: number;
  step: number;
  is_live: boolean;
  is_integer: boolean;
  description: string;
}

// Start values from E.7. ASSUMPTION: E.7 gives no limits or steps; the min / max / step below are ours.
const GAME_VARIABLE_SPECS: readonly NumberVariableSpec[] = [
  { name: "not_moving_time_s", default: 3, min: 0.5, max: 30, step: 0.5, is_live: true, is_integer: false,
    description: "Time the ball must stay still before the not_moving warning" },
  { name: "not_moving_radius_mm", default: 5, min: 1, max: 50, step: 1, is_live: true, is_integer: false,
    description: "Movement inside this radius counts as still" },
  { name: "away_hold_time_s", default: 1.5, min: 0.5, max: 30, step: 0.5, is_live: true, is_integer: false,
    description: "Time the distance must stay larger before away_from_exit" },
  { name: "warning_cooldown_s", default: 3, min: 0.5, max: 60, step: 0.5, is_live: true, is_integer: false,
    description: "Minimum time between repeated warnings of one kind" },
  { name: "ball_lost_pause_s", default: 2, min: 0.5, max: 10, step: 0.5, is_live: true, is_integer: false,
    description: "Time without the ball before paused" },
  { name: "glove_lost_pause_s", default: 1, min: 0.2, max: 10, step: 0.1, is_live: true, is_integer: false,
    description: "Time without the glove before paused (glove mode)" },
  { name: "exit_hold_frames", default: 15, min: 1, max: 120, step: 1, is_live: false, is_integer: true,
    description: "Consecutive is_on_exit frames that finish the game" },
  { name: "time_limit_s", default: 0, min: 0, max: 600, step: 10, is_live: false, is_integer: false,
    description: "Optional game time limit; 0 = off" },
];

export function default_game_variables(): GameVariables {
  const values = {} as GameVariables;
  for (const spec of GAME_VARIABLE_SPECS) values[spec.name] = spec.default;
  return values;
}

function clamp_value(spec: NumberVariableSpec, value: number): number {
  const clamped = Math.min(spec.max, Math.max(spec.min, value));
  return spec.is_integer ? Math.round(clamped) : clamped;
}

/** IF-07: check and clamp every received value; unknown names and non-numbers are skipped. */
export function apply_variable_changes(current: GameVariables, changes: Record<string, unknown>): GameVariables {
  const next = { ...current };
  for (const spec of GAME_VARIABLE_SPECS) {
    const value = changes[spec.name];
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    next[spec.name] = clamp_value(spec, value);
  }
  return next;
}

/** Fields of game/variables_spec (IF-07). */
export function build_variables_spec(values: GameVariables): { variables: object[] } {
  const variables = GAME_VARIABLE_SPECS.map((spec) => ({
    name: spec.name,
    value: values[spec.name],
    default: spec.default,
    min: spec.min,
    max: spec.max,
    step: spec.step,
    choices: null,
    is_live: spec.is_live,
    description: spec.description,
  }));
  return { variables };
}
