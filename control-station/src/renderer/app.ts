// Renderer entry: creates the app's objects, connects the bus and wires the subscriptions (E.5 "On start").
// Naming follows D4: snake_case functions and variables, UPPER_SNAKE_CASE constants, PascalCase classes.
import { Bus, nowS } from "@shared/bus/bus";
import { BROKER_HOST, BROKER_WS_PORT, GAME_STATE, PLATFORM_STATE } from "@shared/topics";
import { BusClient } from "./busClient";
import { Tab } from "./tab";
import { PlotsTab } from "./plotsTab";
import { CameraTab } from "./cameraTab";
import { TwinTab } from "./twinTab";
import { TopBar } from "./topBar";
import { VariablesTab } from "./variablesTab";
import { StartTab } from "./startTab";
import { TopicHealthMonitor } from "./topicHealthMonitor";

const BROKER_WS_URL = `ws://${BROKER_HOST}:${BROKER_WS_PORT}`; // the app UI uses the WebSocket listener (IF-03)

// How often the top bar asks whether the bus is connected. The connection can drop at any
// time and the shared Bus reports it only when asked, so it is checked on a timer.
const BUS_STATUS_CHECK_INTERVAL_MS = 250;

// E.7: how often topic ages are checked. 10 Hz keeps E-R4 (warning within 1 s after the max delay).
// TODO(#78): a live variable of the cs key. Connect it to cs/variables_spec when VariablesTab exists.
const health_check_rate_hz = 10;
const MS_PER_S = 1000;

const bus = new Bus("cs_app", BROKER_WS_URL);
const bus_client = new BusClient(bus);
const top_bar = new TopBar(bus_client, document.getElementById("top-bar") as HTMLElement);
// Created here because it needs to exist before show_bus_status() is called
const start_tab = new StartTab(bus_client);

function show_bus_status(): void {
  const is_connected = bus_client.is_connected();
  top_bar.set_banner("bus_not_connected", !is_connected);
  if (!is_connected) start_tab.update_buttons(null);
}

window.addEventListener("beforeunload", () => {
  void bus.close(); // publishes sys/online/cs_app = false; the broker's Last Will covers a crash
});

// What a missing topic turns on outside the health panel (E.8, IF-07 "What the app reads").
function show_missing_data(topic: string, is_missing: boolean): void {
  if (topic === GAME_STATE) {
    top_bar.set_banner("no_game_manager", is_missing);
    // Only the game buttons: the E-stop is in the top bar and stays enabled.
    if (is_missing) start_tab.update_buttons(null);
    return;
  }
  if (topic === PLATFORM_STATE) {
    top_bar.set_banner("platform_not_connected", is_missing);
    return;
  }
  // StatusPanel ignores topics it does not show, and clears the missing state itself on the next message.
  if (is_missing) start_tab.status_panel.set_missing(topic);
}

const topic_health = new TopicHealthMonitor(bus_client, start_tab.health_panel_root, show_missing_data);

show_bus_status();
setInterval(show_bus_status, BUS_STATUS_CHECK_INTERVAL_MS);
setInterval(() => topic_health.check_topics(nowS()), MS_PER_S / health_check_rate_hz);
// TopBar subscribed before this, which is fine: the Bus subscribes every pattern once it
// connects, and the broker then sends the retained messages.
void bus_client.connect();

// -- Tabs -------
const tabs: Tab[] = [
  start_tab,
  new VariablesTab("Variables", bus_client),
  new PlotsTab("Plots", bus_client),
  new TwinTab("Twin", bus_client),
  new CameraTab("Camera", bus_client),
];

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

