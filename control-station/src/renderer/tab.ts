import { BusClient } from "./busClient";

export abstract class Tab {
    readonly title: string;
    readonly root: HTMLElement;
    protected readonly bus_client: BusClient;
    private is_active: boolean = false;

    constructor(title: string, bus_client: BusClient) {
        this.title = title;
        this.bus_client = bus_client;
        this.root = document.createElement("section");
        this.root.hidden = true;
    }

    is_tab_active(): boolean {
        return this.is_active;
    }

    // Called only by the tab switcher. Subclasses that override on_open/on_close must call super first.
    on_open(): void {
        this.is_active = true;
        this.root.hidden = false;
    }

    on_close(): void {
        this.is_active = false;
        this.root.hidden = true;
    }
}