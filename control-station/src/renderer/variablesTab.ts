import { Tab } from "./tab";
import { BusClient } from "./busClient";
import { CONFIG_KEY_VALUES, ConfigKey, csVariables, variablesSpec } from "@shared/topics";
import { Message } from "@shared/bus/bus";

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

export class VariablesTab extends Tab {
    private values: Map<ConfigKey, Map<string, VariableValue>> = new Map();
    private key_elements: Map<ConfigKey, Map<string, ControlElement>> = new Map();
    private key_sections: Map<ConfigKey, HTMLElement> = new Map();
    private slider_readouts: Map<ControlElement, HTMLSpanElement> = new Map(); // the number shown next to each slider
    private pending_timers: Map<ControlElement, number> = new Map(); // sent values waiting for the module to confirm them
    private editing_elements: Set<ControlElement> = new Set(); // controls that the user is currently editing, so we don't overwrite them with a new value

    constructor(title: string, bus_client: BusClient) {
        super(title, bus_client);
        for (const key of CONFIG_KEY_VALUES) {
            this.values.set(key, new Map());
            this.create_section_element(key);
            this.key_elements.set(key, new Map());
            bus_client.subscribe(variablesSpec(key), (_topic, msg) => this.on_spec(key, msg as Message));
        }
    }

    private render(key: ConfigKey, spec: VariableSpec): void {
        const key_elements = this.key_elements.get(key)!;
        this.key_sections.get(key)!.hidden = false;
        if (!key_elements.has(spec.name)) {
            this.create_variable_element(key, spec);
        }

        const elem = key_elements.get(spec.name)!;
        this.clear_pending(elem);
        if (!this.editing_elements.has(elem)) {
            this.set_element_value(key, spec.name, spec.value);
        }

    }

    private apply(key: ConfigKey, name: string, value: VariableValue): void {
        const msg: Message = {};
        msg[name] = value;
        if (this.bus_client.publish(csVariables(key), msg)) {
            this.mark_pending(key, name, this.key_elements.get(key)!.get(name)!);
        }
        else {
            console.warn(`${key}/${name}: failed to publish new value`);
            this.set_element_value(key, name, this.values.get(key)!.get(name)!); // put back the confirmed value
        }
    }

    private mark_pending(key: ConfigKey, name: string, control: ControlElement): void {
        this.clear_pending(control); // a second change restarts the wait
        control.parentElement!.classList.add("variable-pending");
        const id = window.setTimeout(() => {
            this.clear_pending(control);
            this.set_element_value(key, name, this.values.get(key)!.get(name)!); // put back the confirmed value
            console.warn(`${key}/${name}: no answer from the module`);
        }, MODULE_ANSWER_TIMEOUT_MS);
        this.pending_timers.set(control, id);
    }

    private clear_pending(control: ControlElement): void {
        control.parentElement!.classList.remove("variable-pending");
        const id = this.pending_timers.get(control);
        if (id !== undefined) window.clearTimeout(id);
        this.pending_timers.delete(control);
    }

    private control_kind(spec: VariableSpec): ControlKind {
        if (spec.choices !== null) return "choice";
        if (typeof spec.value === "boolean") return "switch";
        if (typeof spec.value === "number") return spec.min !== null && spec.max !== null ? "slider" : "number";
        return "text";
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
        element.addEventListener("change", () => this.apply(key, spec.name, element.valueAsNumber));
        return element;
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
                element.value = String(this.values.get(key)!.get(spec.name));   // put back the confirmed value
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

    private create_variable_element(key: ConfigKey, spec: VariableSpec): void {
        let element: ControlElement | null = null;
        switch (this.control_kind(spec)) {
            case "switch":
                element = this.create_switch(key, spec);
                break;

            case "choice":
                element = this.create_choice(key, spec);
                break;

            case "slider":
                element = this.create_slider(key, spec);
                break;

            case "number":
                element = this.create_number_input(key, spec);
                break;

            case "text":
                element = this.create_text_input(key, spec);
                break;
        }

        this.key_elements.get(key)!.set(spec.name, element);
        this.key_sections.get(key)!.appendChild(this.create_row(key, spec, element));
    }

    private set_element_value(key: ConfigKey, name: string, value: VariableValue): void {
        const control = this.key_elements.get(key)!.get(name)!;
        if (control instanceof HTMLInputElement && control.type === "checkbox") control.checked = value as boolean;
        else control.value = String(value);

        const readout = this.slider_readouts.get(control);
        if (readout) readout.textContent = control.value;
    }

    private end_editing(key: ConfigKey, name: string, control: ControlElement): void {
        this.editing_elements.delete(control);
        if (!this.pending_timers.has(control)) {
            this.set_element_value(key, name, this.values.get(key)!.get(name)!); // nothing sent: show the confirmed value
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

        const description = document.createElement("span");
        description.className = "variable-description";
        description.textContent = spec.description;
        row.appendChild(description);
        return row;
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

    private on_spec(key: ConfigKey, msg: Message): void {
        if (!Array.isArray(msg.variables)) {
            console.error(`Invalid variables spec message for key ${key}: "variables" is not an array:`, msg);
            return;
        }

        for (const spec of msg.variables as VariableSpec[]) {
            this.update(key, spec);
        }
    }

    private update(key: ConfigKey, spec: VariableSpec): void {
        this.values.get(key)!.set(spec.name, spec.value);
        this.render(key, spec);
    }
}