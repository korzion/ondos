// Formulas of the game/warning rules (IF-05).

const START_INTENSITY_PCT = 50;
const RAMP_INTENSITY_PCT = 50;

/** intensity_pct = 50 + 50 × min(1, time over the threshold / threshold time). */
export function warning_intensity_pct(time_over_s: number, threshold_s: number): number {
  const ramp = Math.min(1, Math.max(0, time_over_s) / threshold_s);
  return START_INTENSITY_PCT + RAMP_INTENSITY_PCT * ramp;
}

export interface PointMm {
  x_mm: number;
  y_mm: number;
}

export function distance_mm(a: PointMm, b: PointMm): number {
  return Math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm);
}
