import { Tab } from "./tab";
import { BusClient } from "./busClient";
import { CONFIG_KEY_VALUES, ConfigKey, csVariables, variablesSpec } from "@shared/topics";
import { Message } from "@shared/bus/bus";

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

export class VariablesTab extends Tab {
    private values: Map<ConfigKey, Map<string, VariableValue>> = new Map();
    private key_elements: Map<ConfigKey, Map<string, HTMLElement>> = new Map();
    private key_sections: Map<ConfigKey, HTMLElement> = new Map();

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

        const element = key_elements.get(spec.name)!;
        element.textContent = `${spec.name}: ${this.values.get(key)!.get(spec.name)}`;
    }

    private apply(key: ConfigKey, name: string, value: VariableValue): void {
        const msg: Message = {};
        msg[name] = value;
        this.bus_client.publish(csVariables(key), msg);
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

    private create_variable_element(key: ConfigKey, spec: VariableSpec): void {
        const element = document.createElement("div");
        this.key_sections.get(key)!.appendChild(element);
        this.key_elements.get(key)!.set(spec.name, element);
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