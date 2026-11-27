// Renderer side of the health log (test E-T6). Does nothing unless the main process switched it on.
import { HEALTH_LOG_PREFIX, HEALTH_LOG_QUERY_FLAG, type HealthLogLine } from "../common/healthLog";

const MS_PER_S = 1000;

const is_health_log_on = new URLSearchParams(window.location.search).has(HEALTH_LOG_QUERY_FLAG);

export function log_missing_change(topic: string, is_missing: boolean): void {
  if (!is_health_log_on) return;
  // Date.now() is on the same wall clock as Python's time.time() in the test.
  const line: HealthLogLine = { t_s: Date.now() / MS_PER_S, topic, is_missing };
  // console.info is the channel to the main process, not a debug print.
  console.info(HEALTH_LOG_PREFIX + JSON.stringify(line));
}
