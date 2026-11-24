/** IF-09 game recorder. Runs independently from the Control Station UI. */
import { spawnSync } from "node:child_process";
import { mkdir, open, type FileHandle } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Bus, nowS, type Message, type Payload } from "../shared/bus/bus";
import * as T from "../shared/topics";

const DEFAULT_RECORDING_FOLDER = "recordings";
const DEFAULT_RECORDING_TAIL_S = 2;
const IMAGE_TOPIC = T.VISION_IMAGE;
const HEADER_FORMAT_VERSION = 1;
const TAIL_CHECK_MS = 50;

type GameStateMessage = Message & {
  game_id: string | null;
  maze_id: string | null;
  mode: string;
  state: string;
};

interface RecordingHeader {
  type: "header";
  format_version: number;
  game_id: string;
  maze_id: string;
  mode: string;
  start_time_s: number;
  git_commit: string | null;
}

interface RecordingLine {
  t_recv_s: number;
  topic: string;
  msg: Payload;
}

interface RecorderOptions {
  recordingFolder: string;
  recordingTailS: number;
  busUrl: string;
  recordingFolderOverride: boolean;
  recordingTailOverride: boolean;
}

function recordingPatterns(): string[] {
  const fixedTopics: string[] = [];
  for (const value of Object.values(T)) {
    if (typeof value !== "string") continue;
    try {
      T.topicInfo(value);
      if (value !== IMAGE_TOPIC) fixedTopics.push(value);
    } catch {
      continue;
    }
  }
  const variableTopics = T.CONFIG_KEY_VALUES.flatMap((key) => [T.variablesSpec(key), T.csVariables(key)]);
  const onlineTopics = T.WRITER_VALUES.map(T.sysOnline);
  return [...new Set([...fixedTopics, ...variableTopics, ...onlineTopics])];
}

function currentGitCommit(): string | null {
  const result = spawnSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" });
  return result.status === 0 ? result.stdout.trim() || null : null;
}

function parseArgs(argv: string[]): RecorderOptions {
  const folderFromEnvironment = process.env.ONDOS_RECORDING_FOLDER;
  const tailFromEnvironment = process.env.ONDOS_RECORDING_TAIL_S;
  const options: RecorderOptions = {
    recordingFolder: folderFromEnvironment ?? DEFAULT_RECORDING_FOLDER,
    recordingTailS: Number(tailFromEnvironment ?? DEFAULT_RECORDING_TAIL_S),
    busUrl: process.env.ONDOS_MQTT_URL ?? `mqtt://${T.BROKER_HOST}:${T.BROKER_TCP_PORT}`,
    recordingFolderOverride: folderFromEnvironment !== undefined,
    recordingTailOverride: tailFromEnvironment !== undefined,
  };
  for (let index = 0; index < argv.length; index++) {
    const value = argv[index + 1];
    switch (argv[index]) {
      case "--recordings":
        if (!value) throw new Error("--recordings requires a folder path");
        options.recordingFolder = value;
        options.recordingFolderOverride = true;
        index++;
        break;
      case "--tail-s":
        if (!value || !Number.isFinite(Number(value)) || Number(value) < 0) {
          throw new Error("--tail-s requires a non-negative number");
        }
        options.recordingTailS = Number(value);
        options.recordingTailOverride = true;
        index++;
        break;
      case "--url":
        if (!value) throw new Error("--url requires a broker URL");
        options.busUrl = value;
        index++;
        break;
      default:
        throw new Error(`unknown argument ${argv[index]}`);
    }
  }
  if (!Number.isFinite(options.recordingTailS) || options.recordingTailS < 0) {
    throw new Error("recording tail must be a non-negative number");
  }
  return options;
}

export class Recorder {
  private readonly bus: Bus;
  private recordingFolder: string;
  private recordingTailS: number;
  private readonly recordingFolderOverride: boolean;
  private readonly recordingTailOverride: boolean;
  private readonly retainedMessages = new Map<string, RecordingLine>();
  private readonly writtenRetainedMessageKeys = new Map<string, string>();
  private file: FileHandle | null = null;
  private activeGameId: string | null = null;
  private gameState: GameStateMessage | null = null;
  private hasPlayed = false;
  private activeRecordingTailS = DEFAULT_RECORDING_TAIL_S;
  private tailStartedAtS: number | null = null;
  private tailTimer: NodeJS.Timeout | null = null;
  private operation = Promise.resolve();
  private stopping = false;

  constructor(options: RecorderOptions) {
    this.bus = new Bus("recorder", options.busUrl);
    this.recordingFolder = options.recordingFolder;
    this.recordingTailS = options.recordingTailS;
    this.recordingFolderOverride = options.recordingFolderOverride;
    this.recordingTailOverride = options.recordingTailOverride;
  }

  async start(): Promise<void> {
    for (const topic of recordingPatterns()) {
      this.bus.subscribe(topic, (receivedTopic, msg, tRecvS) => this.on_message(receivedTopic, msg, tRecvS),
        { acceptReplay: true });
    }
    await this.bus.connect();
    console.info(`recorder online; recordings: ${path.resolve(this.recordingFolder)}`);
  }

  async stop(): Promise<void> {
    if (this.stopping) return;
    this.stopping = true;
    if (this.tailTimer) clearInterval(this.tailTimer);
    await this.operation;
    await this.close_file();
    await this.bus.close();
  }

  on_message(topic: string, msg: Payload, t_recv_s: number): void {
    if (process.env.ONDOS_RECORDER_DEBUG === "1" && topic === T.GAME_STATE && isMessage(msg)) {
      console.info(`game state ${String(msg.state)} ${String(msg.game_id)}`);
    }
    if (process.env.ONDOS_RECORDER_DEBUG === "1" && isReplayMessage(msg)) {
      console.info(`ignored replay message ${topic}`);
    }
    this.enqueue(() => this.processMessage(topic, msg, t_recv_s));
  }

  private enqueue(operation: () => Promise<void>): void {
    this.operation = this.operation.then(operation).catch((error: unknown) => this.fail(error));
  }

  private async processMessage(topic: string, msg: Payload, tRecvS: number): Promise<void> {
    this.updateRecordingSettings(topic, msg);
    if (topic !== IMAGE_TOPIC && !isReplayMessage(msg) && T.topicInfo(topic).retained) {
      this.retainedMessages.set(topic, { t_recv_s: tRecvS, topic, msg });
    }
    if (topic === T.GAME_STATE && isMessage(msg)) {
      await this.onGameState(msg as GameStateMessage, tRecvS);
    }
    if (!this.file || topic === IMAGE_TOPIC || isReplayMessage(msg)) return;
    const line: RecordingLine = { t_recv_s: tRecvS, topic, msg };
    await this.writeLine(line);
  }

  private updateRecordingSettings(topic: string, msg: Payload): void {
    if (!isMessage(msg)) return;
    if (topic === T.variablesSpec("cs") && Array.isArray(msg.variables)) {
      for (const variable of msg.variables) {
        if (!isMessage(variable) || typeof variable.name !== "string") continue;
        this.applyRecordingSetting(variable.name, variable.value);
      }
      return;
    }
    if (topic === T.csVariables("cs")) {
      this.applyRecordingSetting("recording_folder", msg.recording_folder);
      this.applyRecordingSetting("recording_tail_s", msg.recording_tail_s);
    }
  }

  private applyRecordingSetting(name: string, value: unknown): void {
    if (name === "recording_folder" && !this.recordingFolderOverride && typeof value === "string" && value.length > 0) {
      this.recordingFolder = value;
    }
    if (name === "recording_tail_s" && !this.recordingTailOverride && typeof value === "number" && value >= 0) {
      this.recordingTailS = value;
    }
  }

  private async onGameState(msg: GameStateMessage, tRecvS: number): Promise<void> {
    if (msg.state === "ready" && msg.game_id && msg.game_id !== this.activeGameId) {
      await this.close_file();
      this.gameState = msg;
      await this.open_file(msg.game_id);
    }
    if (msg.game_id !== this.activeGameId || !this.file) return;

    if (msg.state === "playing") {
      this.hasPlayed = true;
      this.cancelTail();
    } else if (msg.state === "setup") {
      if (!this.hasPlayed) await this.close_file();
      return;
    } else if (msg.state === "finished" || msg.state === "e_stop") {
      this.startTail(tRecvS);
    } else {
      this.cancelTail();
    }
  }

  async open_file(game_id: string): Promise<void> {
    const recordingFolder = path.resolve(this.recordingFolder);
    await mkdir(recordingFolder, { recursive: true });
    const state = this.gameState;
    if (!state || state.game_id !== game_id) return;
    let suffix = 1;
    while (true) {
      const base = suffix === 1 ? game_id : `${game_id}-${suffix}`;
      const filename = path.join(recordingFolder, `${base}.jsonl`);
      try {
        this.file = await open(filename, "wx");
        this.activeGameId = game_id;
        this.hasPlayed = false;
        this.activeRecordingTailS = this.recordingTailS;
        this.tailStartedAtS = null;
        const header: RecordingHeader = {
          type: "header",
          format_version: HEADER_FORMAT_VERSION,
          game_id,
          maze_id: state.maze_id ?? "",
          mode: state.mode,
          start_time_s: nowS(),
          git_commit: currentGitCommit(),
        };
        await this.writeJson(header);
        await this.writeInitialSnapshot(state.maze_id);
        this.bus.resubscribe();
        console.info(`recording ${filename}`);
        return;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
        suffix++;
      }
    }
  }

  private async writeInitialSnapshot(mazeId: string | null): Promise<void> {
    const snapshots = [...this.retainedMessages.values()].filter((line) => {
      if (line.topic !== T.VISION_MAZE && line.topic !== T.PLAN_DISTANCE_MAP) return true;
      return isMessage(line.msg) && line.msg.maze_id === mazeId;
    });
    snapshots.sort((left, right) => {
      const rank = (topic: string) => topic === T.VISION_MAZE ? 0 : topic === T.PLAN_DISTANCE_MAP ? 1 : 2;
      return rank(left.topic) - rank(right.topic) || left.t_recv_s - right.t_recv_s;
    });
    for (const line of snapshots) {
      if (line.topic !== T.GAME_STATE) await this.writeLine(line);
    }
  }

  private startTail(tRecvS: number): void {
    if (this.tailStartedAtS !== null) return;
    this.tailStartedAtS = tRecvS;
    this.tailTimer = setInterval(() => {
      if (this.tailStartedAtS === null || nowS() - this.tailStartedAtS < this.activeRecordingTailS) return;
      this.enqueue(() => this.close_file());
    }, TAIL_CHECK_MS);
  }

  private cancelTail(): void {
    this.tailStartedAtS = null;
    if (this.tailTimer) clearInterval(this.tailTimer);
    this.tailTimer = null;
  }

  private async writeLine(line: RecordingLine): Promise<void> {
    if (T.topicInfo(line.topic).retained) {
      const key = JSON.stringify(line.msg);
      if (this.writtenRetainedMessageKeys.get(line.topic) === key) return;
      this.writtenRetainedMessageKeys.set(line.topic, key);
    }
    await this.writeJson(line);
  }

  private async writeJson(value: RecordingHeader | RecordingLine): Promise<void> {
    if (!this.file) return;
    await this.file.writeFile(`${JSON.stringify(value)}\n`);
  }

  async close_file(): Promise<void> {
    this.cancelTail();
    const file = this.file;
    this.file = null;
    this.activeGameId = null;
    this.hasPlayed = false;
    this.activeRecordingTailS = this.recordingTailS;
    this.gameState = null;
    this.writtenRetainedMessageKeys.clear();
    if (file) await file.close();
  }

  private async fail(error: unknown): Promise<void> {
    if (this.stopping) return;
    console.error("recorder stopped after a write or runtime error", error);
    this.stopping = true;
    try {
      await this.close_file();
    } catch (closeError) {
      console.error("recorder could not close its file", closeError);
    }
    await this.bus.close().catch(() => undefined);
    process.exitCode = 1;
    process.exit(1);
  }
}

function isMessage(msg: Payload): msg is Message {
  return typeof msg === "object" && !(msg instanceof Uint8Array) && msg !== null;
}

function isReplayMessage(msg: Payload): boolean {
  return isMessage(msg) && msg.writer === "replay";
}

async function main(): Promise<void> {
  const recorder = new Recorder(parseArgs(process.argv.slice(2)));
  await recorder.start();
  const shutdown = () => {
    void recorder.stop().catch((error: unknown) => {
      console.error("recorder shutdown failed", error);
      process.exitCode = 1;
    });
  };
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
  process.once("SIGBREAK", shutdown);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error: unknown) => {
    console.error("recorder failed to start", error);
    process.exitCode = 1;
  });
}
