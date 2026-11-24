// GameManager background process (E.5, IF-03): connects to the broker, feeds GameManager and runs its 10 Hz tick.
//
//   npx tsx control-station/game-manager/main.ts [broker-url]      (default mqtt://127.0.0.1:1883)

import { Bus, nowS, type Callback, type Payload } from "../../shared/bus/bus";
import {
  CS_COMMAND,
  GAME_STATE,
  GLOVE_STATE,
  PLAN_DISTANCE_MAP,
  PLAN_ROUTE,
  PLATFORM_STATE,
  VISION_BALL,
  VISION_EDIT_STATE,
  VISION_MAZE,
  csVariables,
  sysOnline,
} from "../../shared/topics";
import { HEARTBEAT_PERIOD_MS, RETAINED_STATE_WAIT_MS } from "./game_limits";
import { GameManager } from "./game_manager";
import type { GameStateMsg } from "./game_messages";

const VISION_PROGRAM = "vision";

/** Adapts a typed handler to the bus callback; the bus has already checked the message against its schema. */
function deliver<T>(handler: (msg: T) => void): Callback {
  return (_topic: string, msg: Payload) => handler(msg as unknown as T);
}

function wait_ms(duration_ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, duration_ms));
}

/** Section 5.4: read the retained game/state of a previous run, so its game can be marked aborted. */
async function connect_and_read_previous_state(bus: Bus): Promise<GameStateMsg | null> {
  let previous: GameStateMsg | null = null;
  const on_previous = deliver<GameStateMsg>((msg) => (previous = msg));
  bus.subscribe(GAME_STATE, on_previous);
  await bus.connect();
  await wait_ms(RETAINED_STATE_WAIT_MS);
  bus.unsubscribe(GAME_STATE, on_previous);
  return previous;
}

function subscribe_inputs(bus: Bus, gm: GameManager): void {
  bus.subscribe(CS_COMMAND, deliver(gm.on_command.bind(gm)));
  bus.subscribe(VISION_BALL, deliver(gm.on_ball.bind(gm)));
  bus.subscribe(VISION_MAZE, deliver(gm.on_maze.bind(gm)));
  bus.subscribe(PLAN_DISTANCE_MAP, deliver(gm.on_distance_map.bind(gm)));
  bus.subscribe(PLAN_ROUTE, deliver(gm.on_route.bind(gm)));
  bus.subscribe(VISION_EDIT_STATE, deliver(gm.on_edit_state.bind(gm)));
  bus.subscribe(PLATFORM_STATE, deliver(gm.on_platform_state.bind(gm)));
  bus.subscribe(GLOVE_STATE, deliver(gm.on_glove_state.bind(gm)));
  bus.subscribe(csVariables("game"), deliver(gm.on_variables.bind(gm)));
  bus.subscribe(sysOnline(VISION_PROGRAM), (_topic, is_online) => gm.on_online(VISION_PROGRAM, is_online === true));
}

function stop_on_signal(bus: Bus, timer: NodeJS.Timeout): void {
  const stop = async () => {
    clearInterval(timer);
    await bus.close();
    process.exit(0);
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
}

async function main(): Promise<void> {
  const broker_url = process.argv[2];
  const bus = new Bus("game_manager", broker_url);
  const previous_state = await connect_and_read_previous_state(bus);
  const game_manager = new GameManager(bus, nowS, previous_state);
  subscribe_inputs(bus, game_manager);
  const timer = setInterval(() => game_manager.tick(nowS()), HEARTBEAT_PERIOD_MS);
  stop_on_signal(bus, timer);
}

main().catch((error: Error) => {
  console.error(`game_manager: ${error.message}`);
  process.exit(1);
});
