// Electron main process: creates the app window and nothing else.
// The bus, the tabs and all app logic live in the renderer (src/renderer/app.ts),
// which connects to the broker over WebSocket (IF-03).
import { app, BrowserWindow } from "electron";
import { join } from "node:path";

const WINDOW_WIDTH = 1280;
const WINDOW_HEIGHT = 800;

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

  // npm run dev: electron-vite serves the renderer and sets this URL (hot reload).
  // npm run build / packaged app: load the built file next to this one.
  const dev_server_url = process.env.ELECTRON_RENDERER_URL;
  if (dev_server_url) {
    void window.loadURL(dev_server_url);
  } else {
    void window.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

app.whenReady().then(() => {
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
