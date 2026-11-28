// Health log of the topic-health monitor (test E-T6): what the renderer and the main process agree on.
// One line each time a topic's missing-data warning turns on or off.

// Environment variable that turns the log on: the path of the file the main process writes.
export const HEALTH_LOG_ENV = "ONDOS_HEALTH_LOG";

// The main process tells the renderer to log by adding this flag to the page URL.
export const HEALTH_LOG_QUERY_FLAG = "health_log";

// Start of every console line that belongs to the health log; the rest of the line is one JSON object.
export const HEALTH_LOG_PREFIX = "health_log ";

// One line of the log file.
export interface HealthLogLine {
  t_s: number; // wall-clock time of the change (epoch seconds)
  topic: string;
  is_missing: boolean;
}
