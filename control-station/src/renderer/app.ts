// Renderer entry: creates the app's objects, connects the bus and wires the subscriptions (E.5 "On start").
// Naming follows D4: snake_case functions and variables, UPPER_SNAKE_CASE constants, PascalCase classes.
import { Bus } from "@shared/bus/bus";
import { BROKER_HOST, BROKER_WS_PORT, GAME_STATE } from "@shared/topics";
import { BusClient } from "./busClient";
import { Tab } from "./tab";
import { ExampleTab } from "./exampleTab";

const BROKER_WS_URL = `ws://${BROKER_HOST}:${BROKER_WS_PORT}`; // the app UI uses the WebSocket listener (IF-03)

// How often the status bar asks whether the bus is connected. The connection can drop at any
// time and the shared Bus reports it only when asked, so the bar checks on a timer.
const BUS_STATUS_CHECK_INTERVAL_MS = 250;

const status_element = document.getElementById("bus-status") as HTMLDivElement;

function show_bus_status(is_connected: boolean): void {
  status_element.dataset.connected = String(is_connected);
  status_element.textContent = is_connected ? "Bus connected" : "Bus not connected";
}

const bus = new Bus("cs_app", BROKER_WS_URL);
const bus_client = new BusClient(bus);

// Subscribing before connect() is fine: the Bus subscribes every pattern once it connects,
// and the broker then sends the retained messages.
bus_client.subscribe(GAME_STATE, (_topic, msg) => {
  console.log("game/state", msg);
});

window.addEventListener("beforeunload", () => {
  void bus.close(); // publishes sys/online/cs_app = false; the broker's Last Will covers a crash
});

show_bus_status(false);
setInterval(() => show_bus_status(bus_client.is_connected()), BUS_STATUS_CHECK_INTERVAL_MS);
void bus_client.connect();

// -- Tabs -------

const tabs: Tab[] = [new ExampleTab("Start", bus_client), new ExampleTab("Plots", bus_client)];
const tab_buttons = new Map<Tab, HTMLButtonElement>();
let current_tab: Tab | null = null;

const tab_area = document.getElementById("app") as HTMLElement;
const tab_bar = document.getElementById("tab-bar") as HTMLElement;

function add_tab(tab: Tab): void {
  const button = document.createElement("button");
  button.textContent = tab.title;
  button.addEventListener("click", () => switch_tab(tab));
  button.classList.add("tab-button");
  
  tab_bar.appendChild(button);
  tab_buttons.set(tab, button);
  tab_area.appendChild(tab.root);
}

function switch_tab(tab: Tab): void {
  if (current_tab === tab) return;
  if (current_tab) {
    current_tab.on_close();
    tab_buttons.get(current_tab)!.classList.remove("active");
  }

  current_tab = tab;
  tab.on_open();
  tab_buttons.get(current_tab)!.classList.add("active");
}

tabs.forEach(add_tab);
switch_tab(tabs[0]);

