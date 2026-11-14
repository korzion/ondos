// Shared bus helper for the TypeScript programs: GameManager, Recorder (Node.js, mqtt://127.0.0.1:1883)
// and the Control Station app UI (ws://127.0.0.1:9001). Same rules as shared/bus/bus.py (IF-03):
// - envelope: timestamp_s (wall clock at start + performance.now()), seq per topic, version, writer
// - QoS and retained flag from shared/interfaces/topics.json
// - schema check on publish and on receive; repeated QoS 1 deliveries dropped
// - writer = replay dropped unless subscribe(..., { acceptReplay: true })
// - sys/online/<program>: true on connect, false via MQTT Last Will
//
//   const bus = new Bus("game_manager");
//   bus.subscribe(VISION_BALL, (topic, msg, tRecv) => { ... });
//   await bus.connect();
//   bus.publish(GAME_STATE, { state: "setup", ... });

import mqtt, { type MqttClient } from "mqtt";
import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";
import bundle from "../interfaces/schemas.bundle.json";
import {
  BROKER_HOST,
  BROKER_TCP_PORT,
  VARIABLES,
  WRITER_VALUES,
  sysOnline,
  topicInfo,
  type ConfigKey,
  type Writer,
} from "../topics";

export type Message = Record<string, unknown>;
export type Payload = Message | Uint8Array | boolean;
export type Callback = (topic: string, msg: Payload, tRecvS: number) => void;

// ------------------------------------------------------------------ clock
const T0_WALL_S = Date.now() / 1000;
const T0_PERF_MS = performance.now();
/** Laptop clock (IF-03). */
export function nowS(): number {
  return T0_WALL_S + (performance.now() - T0_PERF_MS) / 1000;
}
/** Age of a message from its envelope timestamp_s. */
export function ageS(msg: Message, now = nowS()): number {
  return now - (msg.timestamp_s as number);
}

// ------------------------------------------------------------------ validation
const ENVELOPE_FIELDS = ["timestamp_s", "seq", "version", "writer"];
const ajv = new Ajv2020({ allErrors: false, allowUnionTypes: true });
ajv.addKeyword("x-interface");
for (const schema of Object.values((bundle as { schemas: Record<string, object> }).schemas)) ajv.addSchema(schema);
const validators = new Map<string, ValidateFunction>();

export class ValidationError extends Error {}

/** Throws ValidationError if msg is not a valid message for topic. */
export function validate(topic: string, msg: unknown): void {
  const info = topicInfo(topic);
  if (info.payload === "jpeg") {
    if (!(msg instanceof Uint8Array)) throw new ValidationError(`${topic}: payload must be JPEG bytes`);
    return;
  }
  if (info.payload === "bool") {
    if (typeof msg !== "boolean") throw new ValidationError(`${topic}: payload must be a bool`);
    return;
  }
  const id = `https://ondos.local/schemas/${info.schema}`;
  let v = validators.get(id);
  if (!v) {
    v = ajv.getSchema(id);
    if (!v) throw new ValidationError(`${topic}: schema ${info.schema} not found`);
    validators.set(id, v);
  }
  if (!v(msg)) {
    const e = v.errors?.[0];
    throw new ValidationError(`${topic}: ${e?.instancePath || "(root)"} ${e?.message ?? "invalid"}`);
  }
  const key = info.params.key as ConfigKey | undefined;
  if (key !== undefined) {
    const allowed = new Set(VARIABLES[key]);
    const m = msg as Message;
    const names = topic.startsWith("cs/variables/")
      ? Object.keys(m).filter((k) => !ENVELOPE_FIELDS.includes(k))
      : (m.variables as { name: string }[]).map((v) => v.name);
    const unknown = names.filter((n) => !allowed.has(n));
    if (unknown.length) throw new ValidationError(`${topic}: unknown variable(s) ${unknown.join(", ")} for key ${key}`);
  }
}

/** MQTT topic filter match with + and #. */
export function topicMatches(filter: string, topic: string): boolean {
  const f = filter.split("/");
  const t = topic.split("/");
  for (let i = 0; i < f.length; i++) {
    if (f[i] === "#") return true;
    if (i >= t.length || (f[i] !== "+" && f[i] !== t[i])) return false;
  }
  return f.length === t.length;
}

// ------------------------------------------------------------------ bus
interface Sub {
  pattern: string;
  cb: Callback;
  acceptReplay: boolean;
}

export class Bus {
  readonly program: Writer;
  readonly url: string;
  validateMessages: boolean;
  rejected = 0;
  private client: MqttClient | null = null;
  private seq = new Map<string, number>();
  private subs: Sub[] = [];
  private seen = new Map<string, string[]>();

  constructor(program: Writer, url = `mqtt://${BROKER_HOST}:${BROKER_TCP_PORT}`, opts: { validate?: boolean } = {}) {
    if (!(WRITER_VALUES as readonly string[]).includes(program)) throw new Error(`unknown program ${program}`);
    this.program = program;
    this.url = url;
    this.validateMessages = opts.validate ?? true;
  }

  connect(timeoutMs = 5000): Promise<void> {
    return new Promise((resolve, reject) => {
      const client = mqtt.connect(this.url, {
        clientId: `ondos-${this.program}-${Math.random().toString(16).slice(2, 10)}`,
        keepalive: 10,
        reconnectPeriod: 1000,
        will: { topic: sysOnline(this.program), payload: "false", qos: 1, retain: true },
      });
      this.client = client;
      const timer = setTimeout(() => {
        // Stop the reconnect loop, otherwise the process never exits (E.8 reconnects only after a first connect).
        client.end(true);
        this.client = null;
        reject(new Error(`no broker at ${this.url}`));
      }, timeoutMs);
      client.on("connect", () => {
        client.publish(sysOnline(this.program), "true", { qos: 1, retain: true });
        for (const s of this.subs) client.subscribe(s.pattern, { qos: 1 });
        clearTimeout(timer);
        resolve();
      });
      client.on("message", (topic, payload, packet) => this.onMessage(topic, payload, packet.retain));
    });
  }

  /** Clean shutdown: sys/online/<program> = false, then disconnect. */
  async close(): Promise<void> {
    const c = this.client;
    if (!c) return;
    await c.publishAsync(sysOnline(this.program), "false", { qos: 1, retain: true });
    await c.endAsync();
    this.client = null;
  }

  envelope(topic: string): Message {
    const info = topicInfo(topic);
    const seq = this.seq.get(topic) ?? 0;
    this.seq.set(topic, seq + 1);
    return { timestamp_s: nowS(), seq, version: info.version, writer: this.program };
  }

  /** Publish the topic's own fields; the envelope is added here. Returns what was sent. */
  publish(topic: string, fields: Payload): Payload {
    const info = topicInfo(topic);
    let msg: Payload = fields;
    if (info.payload === "json") {
      const overlap = ENVELOPE_FIELDS.filter((k) => k in (fields as Message));
      if (overlap.length) throw new Error(`${topic}: envelope fields ${overlap.join(", ")} are filled in by the bus helper`);
      msg = { ...this.envelope(topic), ...(fields as Message) };
    }
    this.publishRaw(topic, msg);
    return msg;
  }

  /** Publish a complete message as is. */
  publishRaw(topic: string, msg: Payload, retain?: boolean): void {
    if (!this.client) throw new Error("not connected");
    const info = topicInfo(topic);
    if (this.validateMessages) validate(topic, msg);
    const data = info.payload === "jpeg" ? (msg as Uint8Array) : JSON.stringify(msg);
    this.client.publish(topic, data as string, { qos: info.qos, retain: retain ?? info.retained });
  }

  /** callback(topic, msg, tRecvS). pattern may use MQTT wildcards. */
  subscribe(pattern: string, cb: Callback, opts: { acceptReplay?: boolean } = {}): void {
    this.subs.push({ pattern, cb, acceptReplay: opts.acceptReplay ?? false });
    this.client?.subscribe(pattern, { qos: 1 });
  }

  /** Remove the retained message of a topic. */
  clearRetained(topic: string): void {
    this.client?.publish(topic, "", { qos: 1, retain: true });
  }

  /** Subscribe again to every pattern, so retained messages are delivered again (Recorder, IF-09). */
  resubscribe(): void {
    for (const s of this.subs) {
      this.client?.unsubscribe(s.pattern);
      this.client?.subscribe(s.pattern, { qos: 1 });
    }
  }

  private onMessage(topic: string, payload: Uint8Array, retained: boolean): void {
    const tRecv = nowS();
    if (payload.length === 0) return; // a cleared retained topic
    let msg: Payload;
    try {
      const info = topicInfo(topic);
      msg = info.payload === "jpeg" ? payload : JSON.parse(new TextDecoder().decode(payload));
      if (this.validateMessages) validate(topic, msg);
    } catch (e) {
      this.rejected++;
      console.warn(`ondos bus: message on ${topic} dropped: ${(e as Error).message}`);
      return;
    }
    const isObj = typeof msg === "object" && !(msg instanceof Uint8Array);
    const isReplay = isObj && (msg as Message).writer === "replay";
    if (isObj && !retained && this.isRepeat(topic, msg as Message)) return;
    for (const s of this.subs) {
      if (isReplay && !s.acceptReplay) continue;
      if (!topicMatches(s.pattern, topic)) continue;
      try {
        s.cb(topic, msg, tRecv);
      } catch (e) {
        console.error(`ondos bus: callback for ${topic} failed`, e);
      }
    }
  }

  private isRepeat(topic: string, m: Message): boolean {
    const key = `${m.writer}|${m.seq}|${m.timestamp_s}`;
    const seen = this.seen.get(topic) ?? [];
    if (seen.includes(key)) return true;
    seen.push(key);
    if (seen.length > 32) seen.shift();
    this.seen.set(topic, seen);
    return false;
  }
}
