// Electron main process: creates the app window and nothing else.
// The bus, the tabs and all app logic live in the renderer (src/renderer/app.ts),
// which connects to the broker over WebSocket (IF-03).
import { app, BrowserWindow, Menu } from "electron";
import { join } from "node:path";
import { DRAW_LOG_ENV, DRAW_LOG_PREFIX, DRAW_LOG_QUERY_FLAG } from "../common/drawLog";
import { HEALTH_LOG_ENV, HEALTH_LOG_PREFIX, HEALTH_LOG_QUERY_FLAG } from "../common/healthLog";
import { type TestLog, test_log_path, write_test_log } from "./testLogFile";

const WINDOW_WIDTH = 1280;
const WINDOW_HEIGHT = 800;

// E-T1: the plots log their draw times. E-T6: the topic-health monitor logs its missing-data warnings.
const TEST_LOGS: readonly TestLog[] = [
  { env: DRAW_LOG_ENV, query_flag: DRAW_LOG_QUERY_FLAG, prefix: DRAW_LOG_PREFIX },
  { env: HEALTH_LOG_ENV, query_flag: HEALTH_LOG_QUERY_FLAG, prefix: HEALTH_LOG_PREFIX },
];

// Starts every test log whose environment variable is set; returns the URL flags that turn them on in the renderer.
function start_test_logs(window: BrowserWindow): Record<string, string> {
  const query: Record<string, string> = {};
  for (const log of TEST_LOGS) {
    const log_path = test_log_path(log);
    if (!log_path) continue;
    query[log.query_flag] = "1";
    write_test_log(window, log, log_path);
  }
  return query;
}

function create_window(): void {
  const window = new BrowserWindow({
    width: WINDOW_WIDTH,
    height: WINDOW_HEIGHT,
    minWidth: 960,
    minHeight: 600,
    title: "Ondos Control Station",
    show: false,
    webPreferences: {
      // The renderer is a plain web page: no Node APIs in it.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  window.once("ready-to-show", () => window.show());

  // Tests E-T1 and E-T6: the renderer logs only when the page URL carries the flag.
  const query = start_test_logs(window);

  // npm run dev: electron-vite serves the renderer and sets this URL (hot reload).
  // npm run build / packaged app: load the built file next to this one.
  const dev_server_url = process.env.ELECTRON_RENDERER_URL;
  if (dev_server_url) {
    const url = new URL(dev_server_url);
    Object.entries(query).forEach(([name, value]) => url.searchParams.set(name, value));
    void window.loadURL(url.toString());
  } else {
    void window.loadFile(join(__dirname, "../renderer/index.html"), { query });
  }
}

app.whenReady().then(() => {
  // The app has no use for Electron's default File/Edit/View menu. It stays in development
  // only, because its View menu gives reload (Ctrl+R) and the developer tools (Ctrl+Shift+I).
  if (app.isPackaged) {
    Menu.setApplicationMenu(null);
  }
  create_window();

  // macOS keeps the app running with no window; clicking the dock icon opens one again.
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) create_window();
  });
});

// Windows and Linux: closing the last window quits the app.
// GameManager and the Recorder are separate processes and keep running (E-R5).
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
