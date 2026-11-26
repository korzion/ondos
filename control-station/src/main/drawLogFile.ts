// Main side of the draw log (test E-T1): copies the renderer's draw log lines into a file.
// Off unless the environment variable ONDOS_DRAW_LOG names the file; nothing is written normally.
import type { BrowserWindow } from "electron";
import { appendFileSync, writeFileSync } from "node:fs";
import { DRAW_LOG_ENV, DRAW_LOG_PREFIX } from "../common/drawLog";

export function draw_log_path(): string | null {
  return process.env[DRAW_LOG_ENV] || null;
}

export function write_draw_log(window: BrowserWindow, path: string): void {
  writeFileSync(path, ""); // every run starts with an empty log
  window.webContents.on("console-message", (event) => {
    if (!event.message.startsWith(DRAW_LOG_PREFIX)) return;
    appendFileSync(path, event.message.slice(DRAW_LOG_PREFIX.length) + "\n");
  });
}
