import { Tab } from "./tab";
import { BusClient } from "./busClient";
import { CONFIG_KEY_VALUES, ConfigKey, VARIABLES, csVariables, variablesSpec } from "@shared/topics";
import { Message } from "@shared/bus/bus";
import "./variablesTab.css";

type ControlKind = "switch" | "choice" | "slider" | "number" | "text";
type ControlElement = HTMLInputElement | HTMLSelectElement;
type VariableValue = number | boolean | string;
type VariableSpec = {
    name: string;
    value: VariableValue;
    default: VariableValue;
    min: number | null;
    max: number | null;
    step?: number | null;
    choices: (number | string)[] | null;
    is_live: boolean;
    description: string;
};

const DEFAULT_STEP = 1;
// How long a sent value waits for the module to republish its spec before the control goes back
// to the confirmed value. Not in the design document: chosen here, noted on #78.
const MODULE_ANSWER_TIMEOUT_MS = 1000;
const LIVE_SEND_INTERVAL_MS = 1000 / 10; // IF-07 (cs/variables/<key>): live variables, max 10 per second while sliding

export class VariablesTab extends Tab {
    private specs: Map<ConfigKey, Map<string, VariableSpec>> = new Map(); // the latest spec of each variable; its value is the confirmed value
    private user_values: Map<ConfigKey, Map<string, VariableValue>> = new Map(); // values the user set, sent together on every change
    private key_elements: Map<ConfigKey, Map<string, ControlElement>> = new Map();
    private key_sections: Map<ConfigKey, HTMLElement> = new Map();
    private slider_readouts: Map<ControlElement, HTMLSpanElement> = new Map(); // the number shown next to each slider
    private pending_timers: Map<ControlElement, number> = new Map(); // sent values waiting for the module to confirm them
    private pending_values: Map<ControlElement, VariableValue> = new Map(); // what each pending control sent
    private editing_elements: Set<ControlElement> = new Set(); // controls that the user is currently editing, so we don't overwrite them with a new value
    private needs_rebuild: Set<ControlElement> = new Set(); // rows whose spec changed while the user was editing them
    private last_sent_ms: Map<ControlElement, number> = new Map(); // when each slider last sent, for the live rate limit
    private last_sent_value: Map<ControlElement, number> = new Map(); // what each slider last sent, to skip an immediate repeat

    constructor(title: string, bus_client: BusClient) {
        super(title, bus_client);
        for (const key of CONFIG_KEY_VALUES) {
            this.specs.set(key, new Map());
            this.user_values.set(key, new Map());
            this.key_elements.set(key, new Map());
            this.create_section_element(key);
            bus_client.subscribe(variablesSpec(key), (_topic, msg) => this.on_spec(key, msg as Message));
            bus_client.subscribe(csVariables(key), (_topic, msg) => this.on_sent_values(key, msg as Message));
        }
    }

    private update(key: ConfigKey, spec: VariableSpec): void {
        const old_spec = this.specs.get(key)!.get(spec.name);
        this.specs.get(key)!.set(spec.name, spec);

        let control = this.key_elements.get(key)!.get(spec.name);
        if (control === undefined) control = this.add_variable(key, spec);
        else if (old_spec !== undefined && !this.same_layout(old_spec, spec)) this.needs_rebuild.add(control);

        // A row whose spec changed is rebuilt now, or when the user stops editing it (end_editing).
        if (this.needs_rebuild.has(control) && !this.editing_elements.has(control)) control = this.rebuild_variable(key, spec);
        this.render(control, old_spec, spec);
    }

    // Shows the module's value, unless the user is editing the control or it still waits for an answer.
    private render(control: ControlElement, old_spec: VariableSpec | undefined, spec: VariableSpec): void {
        if (this.pending_values.has(control)) {
            if (!this.module_answered(control, old_spec, spec)) return;
            this.clear_pending(control);
        }
        if (!this.editing_elements.has(control)) this.show_value(control, spec.value);
    }

    // A module republishes its whole spec when any of its variables changes. The spec answers a pending
    // control only if this variable's value changed (applied or clamped) or equals what was sent;
    // otherwise it is the answer to another variable, and the control keeps showing what it sent.
    private module_answered(control: ControlElement, old_spec: VariableSpec | undefined, spec: VariableSpec): boolean {
        return old_spec === undefined || spec.value !== old_spec.value || spec.value === this.pending_values.get(control);
    }

    // cs/variables/<key> is retained, so every send carries all the values the user set for that key,
    // not only the one that changed (IF-07: "a module that restarts gets the values again").
    private apply(key: ConfigKey, name: string, value: VariableValue): void {
        const control = this.key_elements.get(key)!.get(name)!;
        const msg: Message = { ...this.values_to_send(key), [name]: value };
        if (this.bus_client.publish(csVariables(key), msg)) {
            this.user_values.get(key)!.set(name, value);
            this.mark_pending(key, name, control, value);
        }
        else {
            console.warn(`${key}/${name}: failed to publish new value`);
            this.show_value(control, this.confirmed_value(key, name)); // put back the confirmed value
        }
    }

    // The values the user set, for the variables that are still in the module's spec.
    private values_to_send(key: ConfigKey): Message {
        const specs = this.specs.get(key)!;
        return Object.fromEntries([...this.user_values.get(key)!].filter(([name]) => specs.has(name)));
    }

    // The retained cs/variables/<key> holds what the user set before the app (re)started, so the next
    // send does not drop those values. Values set since then are kept; the app's own sends come back
    // here too and change nothing.
    private on_sent_values(key: ConfigKey, msg: Message): void {
        const user_values = this.user_values.get(key)!;
        for (const name of VARIABLES[key]) {
            const value = msg[name];
            if (user_values.has(name)) continue;
            if (typeof value === "number" || typeof value === "boolean" || typeof value === "string") user_values.set(name, value);
        }
    }

    private confirmed_value(key: ConfigKey, name: string): VariableValue {
        return this.specs.get(key)!.get(name)!.value;
    }

    private mark_pending(key: ConfigKey, name: string, control: ControlElement, value: VariableValue): void {
        this.clear_pending(control); // a second change restarts the wait
        this.pending_values.set(control, value);
        control.parentElement!.classList.add("variable-pending");
        const id = window.setTimeout(() => {
            this.clear_pending(control);
            this.show_value(control, this.confirmed_value(key, name)); // put back the confirmed value
            console.warn(`${key}/${name}: no answer from the module`);
        }, MODULE_ANSWER_TIMEOUT_MS);
        this.pending_timers.set(control, id);
    }

    private clear_pending(control: ControlElement): void {
        control.parentElement?.classList.remove("variable-pending");
        const id = this.pending_timers.get(control);
        if (id !== undefined) window.clearTimeout(id);
        this.pending_timers.delete(control);
        this.pending_values.delete(control);
    }

    private control_kind(spec: VariableSpec): ControlKind {
        if (spec.choices !== null) return "choice";
        if (typeof spec.value === "boolean") return "switch";
        if (typeof spec.value === "number") return spec.min !== null && spec.max !== null ? "slider" : "number";
        return "text";
    }

    // Everything but the value decides how a row looks and what it can send.
    private same_layout(a: VariableSpec, b: VariableSpec): boolean {
        return this.control_kind(a) === this.control_kind(b)
            && a.min === b.min
            && a.max === b.max
            && (a.step ?? null) === (b.step ?? null)
            && JSON.stringify(a.choices) === JSON.stringify(b.choices)
            && a.is_live === b.is_live
            && a.description === b.description;
    }

    private create_section_element(key: ConfigKey): void {
        const section = document.createElement("div");
        const header = document.createElement("h2");
        header.textContent = `Variables for ${key}`;
        section.appendChild(header);
        section.hidden = true;

        this.key_sections.set(key, section);
        this.root.appendChild(section);
    }

    private create_switch(key: ConfigKey, spec: VariableSpec): HTMLInputElement {
        const element = document.createElement("input");
        element.type = "checkbox";
        element.addEventListener("change", () => this.apply(key, spec.name, element.checked));
        return element;
    }

    // spec.choices is the list this dropdown was built from, so selectedIndex always matches it;
    // when the module changes the list, the row is rebuilt (update).
    private create_choice(key: ConfigKey, spec: VariableSpec): HTMLSelectElement {
        const element = document.createElement("select");
        if (spec.choices) {
            for (const choice of spec.choices) {
                const option = document.createElement("option");
                option.value = choice.toString();
                option.textContent = choice.toString();
                element.appendChild(option);
            }
        }
        element.addEventListener("change", () => this.apply(key, spec.name, spec.choices![element.selectedIndex]));
        return element;
    }

    private create_slider(key: ConfigKey, spec: VariableSpec): HTMLInputElement {
        const element = document.createElement("input");
        element.type = "range";
        element.min = String(spec.min);
        element.max = String(spec.max);
        element.step = spec.step?.toString() ?? DEFAULT_STEP.toString();
        // On release, always send the final position, unless "input" sent that same value just now
        // (a key press or a click on the track fires "input" and "change" together).
        element.addEventListener("change", () => {
            const is_repeat = element.valueAsNumber === this.last_sent_value.get(element)
                && this.ms_since_sent(element) < LIVE_SEND_INTERVAL_MS;
            if (!is_repeat) this.send_slider(key, spec.name, element);
        });

        if (spec.is_live) {
            element.addEventListener("input", () => {
                if (this.ms_since_sent(element) >= LIVE_SEND_INTERVAL_MS) this.send_slider(key, spec.name, element);
            });
        }

        return element;
    }

    private send_slider(key: ConfigKey, name: string, slider: HTMLInputElement): void {
        this.apply(key, name, slider.valueAsNumber);
        this.last_sent_ms.set(slider, performance.now());
        this.last_sent_value.set(slider, slider.valueAsNumber);
    }

    private ms_since_sent(slider: HTMLInputElement): number {
        return performance.now() - (this.last_sent_ms.get(slider) ?? -Infinity);
    }

    private create_number_input(key: ConfigKey, spec: VariableSpec): HTMLInputElement {
        const element = document.createElement("input");
        element.type = "number";
        element.min = spec.min?.toString() ?? "";
        element.max = spec.max?.toString() ?? "";
        element.step = spec.step?.toString() ?? DEFAULT_STEP.toString();
        element.addEventListener("change", () => {
            const value = element.valueAsNumber;
            if (Number.isNaN(value)) {
                this.show_value(element, this.confirmed_value(key, spec.name)); // put back the confirmed value
                return;
            }
            this.apply(key, spec.name, value);
        });
        return element;
    }

    private create_text_input(key: ConfigKey, spec: VariableSpec): HTMLInputElement {
        const element = document.createElement("input");
        element.type = "text";
        element.addEventListener("change", () => this.apply(key, spec.name, element.value));
        return element;
    }

    private create_control(key: ConfigKey, spec: VariableSpec): ControlElement {
        switch (this.control_kind(spec)) {
            case "switch": return this.create_switch(key, spec);
            case "choice": return this.create_choice(key, spec);
            case "slider": return this.create_slider(key, spec);
            case "number": return this.create_number_input(key, spec);
            case "text": return this.create_text_input(key, spec);
        }
    }

    private add_variable(key: ConfigKey, spec: VariableSpec): ControlElement {
        const control = this.create_control(key, spec);
        this.key_elements.get(key)!.set(spec.name, control);
        this.key_sections.get(key)!.appendChild(this.create_row(key, spec, control));
        return control;
    }

    // Builds the row again from the new spec, in the same place, showing the confirmed value.
    private rebuild_variable(key: ConfigKey, spec: VariableSpec): ControlElement {
        const old_control = this.key_elements.get(key)!.get(spec.name)!;
        const control = this.create_control(key, spec);
        this.key_elements.get(key)!.set(spec.name, control);
        old_control.parentElement!.replaceWith(this.create_row(key, spec, control));
        this.forget_control(old_control);
        this.show_value(control, spec.value);
        return control;
    }

    // A variable that is no longer in the module's spec.
    private remove_variable(key: ConfigKey, name: string): void {
        const control = this.key_elements.get(key)!.get(name)!;
        control.parentElement!.remove();
        this.forget_control(control);
        this.key_elements.get(key)!.delete(name);
        this.specs.get(key)!.delete(name);
        this.user_values.get(key)!.delete(name);
    }

    // Drops everything kept for a control that was rebuilt or removed.
    private forget_control(control: ControlElement): void {
        this.clear_pending(control);
        this.editing_elements.delete(control);
        this.needs_rebuild.delete(control);
        this.slider_readouts.delete(control);
        this.last_sent_ms.delete(control);
        this.last_sent_value.delete(control);
    }

    private show_value(control: ControlElement, value: VariableValue): void {
        if (control instanceof HTMLInputElement && control.type === "checkbox") control.checked = value as boolean;
        else control.value = String(value);

        const readout = this.slider_readouts.get(control);
        if (readout) readout.textContent = control.value;
    }

    private end_editing(key: ConfigKey, name: string, control: ControlElement): void {
        this.editing_elements.delete(control);
        if (this.key_elements.get(key)!.get(name) !== control) return; // the row was rebuilt or removed meanwhile
        if (this.needs_rebuild.has(control)) {
            this.rebuild_variable(key, this.specs.get(key)!.get(name)!);
            return;
        }
        if (!this.pending_timers.has(control)) {
            this.show_value(control, this.confirmed_value(key, name)); // nothing sent: show the confirmed value
        }
    }

    // One row: name, control, the slider's number (sliders only) and the description (IF-07: "shown next to the slider").
    private create_row(key: ConfigKey, spec: VariableSpec, control: ControlElement): HTMLElement {
        const row = document.createElement("div");
        row.className = "variable-row";

        control.id = `variable-${key}-${spec.name}`;
        const label = document.createElement("label");
        label.htmlFor = control.id;
        label.textContent = spec.name;
        row.append(label, control);

        if (control instanceof HTMLInputElement && control.type === "range") {
            row.appendChild(this.create_slider_readout(control));
        }

        control.addEventListener("input", () => this.editing_elements.add(control));
        control.addEventListener("change", () => this.editing_elements.delete(control));
        control.addEventListener("blur", () => this.end_editing(key, spec.name, control));

        if (!spec.is_live) row.appendChild(this.create_not_live_tag());

        const description = document.createElement("span");
        description.className = "variable-description";
        description.textContent = spec.description;
        row.appendChild(description);
        return row;
    }

    // Section 6.3: "next" variables take effect at the next start, maze read or game, not at once.
    private create_not_live_tag(): HTMLSpanElement {
        const tag = document.createElement("span");
        tag.className = "variable-not-live";
        tag.textContent = "not live";
        tag.title = "Takes effect at the next start, maze read or game";
        return tag;
    }

    // Follows the thumb while dragging; render() sets it to the confirmed value.
    private create_slider_readout(slider: HTMLInputElement): HTMLSpanElement {
        const readout = document.createElement("span");
        readout.className = "variable-readout";
        slider.addEventListener("input", () => {
            readout.textContent = slider.value;
        });
        this.slider_readouts.set(slider, readout);
        return readout;
    }

    // ASSUMPTION (#78): the shared bus already drops a whole spec that fails the schema (that is a bug in
    // the module, and the bus logs it), so E.8's "skip that variable" covers only what the schema can't check.
    private is_valid_variable(spec: unknown): spec is VariableSpec {
        if (typeof spec !== "object" || spec === null) return false;
        const s = spec as VariableSpec;
        if (typeof s.name !== "string") return false;
        if (typeof s.value !== "number" && typeof s.value !== "boolean" && typeof s.value !== "string") return false;
        if (typeof s.default !== "number" && typeof s.default !== "boolean" && typeof s.default !== "string") return false;
        if (s.min !== null && typeof s.min !== "number") return false;
        if (s.max !== null && typeof s.max !== "number") return false;
        if (s.step !== undefined && s.step !== null && typeof s.step !== "number") return false;
        if (s.choices !== null && !Array.isArray(s.choices)) return false;
        if (s.choices !== null && !s.choices.includes(s.value as number | string)) return false; // not checked by the schema
        if (typeof s.is_live !== "boolean") return false;
        if (typeof s.description !== "string") return false;
        return true;
    }

    private on_spec(key: ConfigKey, msg: Message): void {
        if (!Array.isArray(msg.variables)) {
            // Console only: there is no app-wide log this tab can write to yet (E.8: "writes it to the log").
            console.error(`Invalid variables spec message for key ${key}: "variables" is not an array:`, msg);
            return;
        }

        const valid_specs: VariableSpec[] = [];
        for (const spec of msg.variables) {
            if (this.is_valid_variable(spec)) valid_specs.push(spec);
            // Console only: there is no app-wide log this tab can write to yet (E.8: "writes it to the log").
            else console.error(`Invalid variable spec for key ${key}:`, spec);
        }

        const names = new Set(valid_specs.map((spec) => spec.name));
        for (const name of [...this.specs.get(key)!.keys()]) {
            if (!names.has(name)) this.remove_variable(key, name);
        }
        for (const spec of valid_specs) this.update(key, spec);
        this.key_sections.get(key)!.hidden = valid_specs.length === 0;
    }
}
