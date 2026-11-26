// Renderer side of the draw log (test E-T1). Does nothing unless the main process switched it on.
import { DRAW_LOG_PREFIX, DRAW_LOG_QUERY_FLAG, type DrawLogEntry, type DrawLogLine } from "../common/drawLog";

const MS_PER_S = 1000;

const is_draw_log_on = new URLSearchParams(window.location.search).has(DRAW_LOG_QUERY_FLAG);

export function log_draw(entry: DrawLogEntry): void {
  if (!is_draw_log_on) return;
  // Date.now() is on the same wall clock as Python's time.time() in the test. performance.timeOrigin
  // can drift from it (for example after the laptop sleeps).
  const line: DrawLogLine = { t_s: Date.now() / MS_PER_S, ...entry };
  // console.info is the channel to the main process, not a debug print.
  console.info(DRAW_LOG_PREFIX + JSON.stringify(line));
}
