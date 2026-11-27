// Main side of the test logs (E-T1 draw log, E-T6 health log): copies the renderer's log lines into a file.
// The renderer writes each line to the console with a prefix; this works without a preload script and the
// renderer stays sandboxed. A log is off unless its environment variable names the file.
import type { BrowserWindow } from "electron";
import { appendFileSync, writeFileSync } from "node:fs";

export interface TestLog {
  env: string; // environment variable with the path of the log file
  query_flag: string; // added to the page URL to tell the renderer to log
  prefix: string; // start of every console line that belongs to this log
}

export function test_log_path(log: TestLog): string | null {
  return process.env[log.env] || null;
}

export function write_test_log(window: BrowserWindow, log: TestLog, path: string): void {
  writeFileSync(path, ""); // every run starts with an empty log
  window.webContents.on("console-message", (event) => {
    if (!event.message.startsWith(log.prefix)) return;
    appendFileSync(path, event.message.slice(log.prefix.length) + "\n");
  });
}
