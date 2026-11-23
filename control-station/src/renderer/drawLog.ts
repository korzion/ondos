// Renderer side of the draw log (test E-T1). Does nothing unless the main process switched it on.
import { DRAW_LOG_PREFIX, DRAW_LOG_QUERY_FLAG, type DrawLogEntry, type DrawLogLine } from "../common/drawLog";

const MS_PER_S = 1000;

const is_draw_log_on = new URLSearchParams(window.location.search).has(DRAW_LOG_QUERY_FLAG);

// performance.timeOrigin + performance.now() is epoch time with sub-millisecond steps, so the
// test can compare it with the clock of the process that plays the fixture.
function now_epoch_s(): number {
  return (performance.timeOrigin + performance.now()) / MS_PER_S;
}

export function log_draw(entry: DrawLogEntry): void {
  if (!is_draw_log_on) return;
  const line: DrawLogLine = { t_s: now_epoch_s(), ...entry };
  // console.info is the channel to the main process, not a debug print.
  console.info(DRAW_LOG_PREFIX + JSON.stringify(line));
}
