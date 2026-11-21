// Renderer entry: creates the app's objects, connects the bus and wires the subscriptions (E.5 "On start").
// For now it only connects to the broker and shows whether the bus is connected.
// Naming follows D4: snake_case functions and variables, UPPER_SNAKE_CASE constants, PascalCase classes.
import { Bus } from "@shared/bus/bus";
import { GAME_STATE } from "@shared/topics";

const BROKER_WS_URL = "ws://127.0.0.1:9001"; // app UI uses the WebSocket listener (IF-03)
const RETRY_DELAY_MS = 2000;

const status_element = document.getElementById("bus-status") as HTMLDivElement;

function show_bus_status(is_connected: boolean): void {
  status_element.dataset.connected = String(is_connected);
  status_element.textContent = is_connected ? "Bus connected" : "Bus not connected";
}

const bus = new Bus("cs_app", BROKER_WS_URL);

// Subscriptions can be added before connect(); the bus subscribes once it is connected.
bus.subscribe(GAME_STATE, (_topic, msg) => {
  console.log("game/state", msg);
});

// Bus.connect() gives up after its timeout if no broker answers, so keep trying until one does.
async function connect_bus(): Promise<void> {
  try {
    await bus.connect();
    show_bus_status(true);
  } catch (error) {
    show_bus_status(false);
    console.warn(`${(error as Error).message}, retrying in ${RETRY_DELAY_MS} ms`);
    setTimeout(connect_bus, RETRY_DELAY_MS);
  }
}

window.addEventListener("beforeunload", () => {
  void bus.close(); // publishes sys/online/cs_app = false; the broker's Last Will covers a crash
});

show_bus_status(false);
void connect_bus();
