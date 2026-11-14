// npm test  (needs mosquitto on PATH; skipped otherwise)
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { Bus, ValidationError, validate, type Message, type Payload } from "./bus";
import { GAME_STATE, VISION_BALL } from "../topics";

const hasMosquitto = spawnSync("mosquitto", ["-h"]).error === undefined;

function freePort(): Promise<number> {
  return new Promise((res) => {
    const s = createServer().listen(0, "127.0.0.1", () => {
      const p = (s.address() as { port: number }).port;
      s.close(() => res(p));
    });
  });
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const BALL = { x_mm: 1, y_mm: 2, vx_mm_s: 0, vy_mm_s: 0, is_visible: true, is_predicted: false,
  is_on_exit: false, frame_age_ms: 20, meas_x_mm: null, meas_y_mm: null };

test("validate accepts a good message and rejects a bad one", () => {
  validate(VISION_BALL, { timestamp_s: 1, seq: 0, version: 1, writer: "vision", ...BALL });
  assert.throws(() => validate(VISION_BALL, { timestamp_s: 1, seq: 0, version: 1, writer: "vision", x_mm: 1 }), ValidationError);
  assert.throws(() => validate("cs/variables/platform", { timestamp_s: 1, seq: 0, version: 1, writer: "cs_app", max_tilt: 3 }), ValidationError);
});

test("connect fails cleanly when there is no broker", async () => {
  const bus = new Bus("vision", "mqtt://127.0.0.1:1");
  await assert.rejects(bus.connect(1000), /no broker/); // and the process can exit (no reconnect loop left)
});

test("publish / subscribe through mosquitto", { skip: !hasMosquitto }, async () => {
  const port = await freePort();
  // No config file: Ubuntu's AppArmor profile lets mosquitto read configs only from /etc/mosquitto.
  // Without one, mosquitto 2 runs in local-only mode (127.0.0.1, anonymous).
  const broker = spawn("mosquitto", ["-p", String(port)], { stdio: "ignore" });
  await sleep(500);
  try {
    const got: [string, Payload][] = [];
    const obs = new Bus("cs_app", `mqtt://127.0.0.1:${port}`);
    obs.subscribe("vision/ball", (t, m) => got.push([t, m]));
    obs.subscribe("sys/online/+", (t, m) => got.push([t, m]));
    await obs.connect();
    const gm = new Bus("game_manager", `mqtt://127.0.0.1:${port}`);
    await gm.connect();
    assert.throws(() => gm.publish(GAME_STATE, { state: "nope" }), ValidationError);
    const vision = new Bus("vision", `mqtt://127.0.0.1:${port}`, { validate: false });
    await vision.connect();
    vision.publish(VISION_BALL, BALL);
    vision.publishRaw(VISION_BALL, { ...vision.envelope(VISION_BALL), ...BALL, writer: "replay" });
    await sleep(300);
    await vision.close();
    await gm.close();
    await sleep(200);
    await obs.close();
    const balls = got.filter(([t]) => t === "vision/ball").map(([, m]) => m as Message);
    assert.equal(balls.length, 1); // the replay message is dropped
    assert.equal(balls[0].writer, "vision");
    assert.equal(balls[0].seq, 0);
    const online = got.filter(([t]) => t === "sys/online/vision").map(([, m]) => m);
    assert.deepEqual([online[0], online.at(-1)], [true, false]);
  } finally {
    broker.kill();
  }
});
