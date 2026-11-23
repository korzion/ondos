// Placeholder tab for testing the switcher; remove once the real tabs exist.
import { Tab } from "./tab";
import { BusClient } from "./busClient";

export class ExampleTab extends Tab {
    constructor(title: string, bus_client: BusClient) {
        super(title, bus_client);
        this.root.textContent = `This is the ${title} tab.`;
    }
}