// Build config for the Control Station app (electron-vite).
// Two separate bundles:
//   main      src/main/main.ts         -> out/main/main.js      Electron main process (Node): window only
//   renderer  src/renderer/index.html  -> out/renderer/         the app UI (browser): BusClient, tabs
// The renderer imports shared/ from the repository root (topics.ts, bus/bus.ts), so the
// "@shared" alias points there and the dev server is allowed to read files outside this folder.
import { resolve } from "node:path";
import { defineConfig } from "electron-vite";

const REPO_ROOT = resolve(__dirname, "..");
const SHARED_DIR = resolve(REPO_ROOT, "shared");

export default defineConfig({
  main: {
    build: {
      rolldownOptions: {
        input: { main: resolve(__dirname, "src/main/main.ts") },
      },
    },
  },
  renderer: {
    root: resolve(__dirname, "src/renderer"),
    resolve: {
      alias: { "@shared": SHARED_DIR },
    },
    server: {
      fs: { allow: [REPO_ROOT] },
    },
    build: {
      rolldownOptions: {
        input: { index: resolve(__dirname, "src/renderer/index.html") },
      },
    },
  },
});
