// Draw log of the plots (test E-T1): what the renderer and the main process agree on (main side: testLogFile.ts).
// The renderer writes one console line per real uPlot redraw; the main process copies those
// lines into a file. This works without a preload script and the renderer stays sandboxed.

// Environment variable that turns the log on: the path of the file the main process writes.
export const DRAW_LOG_ENV = "ONDOS_DRAW_LOG";

// The main process tells the renderer to log by adding this flag to the page URL.
export const DRAW_LOG_QUERY_FLAG = "draw_log";

// Start of every console line that belongs to the draw log; the rest of the line is one JSON object.
export const DRAW_LOG_PREFIX = "draw_log ";

export interface DrawLogEntry {
  plot: string; // topic of the plot that was redrawn
  x_min_s: number; // left edge of the time axis
  x_max_s: number; // right edge of the time axis
  oldest_s: number; // time of the oldest sample still stored
  points: number; // number of stored samples
}

// One line of the log file: the entry and the wall-clock time of the redraw (epoch seconds).
export interface DrawLogLine extends DrawLogEntry {
  t_s: number;
}
