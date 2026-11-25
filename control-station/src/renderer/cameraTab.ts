// The Camera tab: shows the camera image from vision/image, subscribed only while the tab is open
// (E.5 "CameraTab", E-R6, IF-04 vision/image).
import type { Callback } from "@shared/bus/bus";
import { VISION_IMAGE } from "@shared/topics";
import { BusClient } from "./busClient";
import { Tab } from "./tab";

// IF-04: the payload of vision/image is raw JPEG bytes, without the JSON envelope.
const JPEG_MIME_TYPE = "image/jpeg";
const NO_IMAGE_TEXT = "No camera image yet";
const IMAGE_ALT_TEXT = "Camera image";
const IMAGE_MAX_WIDTH = "100%"; // the 640 px image shrinks with a narrow window

export class CameraTab extends Tab {
    private readonly image_element: HTMLImageElement;
    private readonly no_image_element: HTMLElement;
    private image_url: string | null = null;
    // One function object, so unsubscribe finds the same callback again.
    private readonly handle_image: Callback = (_topic, msg) => this.on_image(msg as Uint8Array);

    constructor(title: string, bus_client: BusClient) {
        super(title, bus_client);
        this.no_image_element = this.create_no_image_element();
        this.image_element = this.create_image_element();
    }

    // E.5: the image is received only while the tab is open, so a hidden tab costs the laptop nothing.
    on_open(): void {
        super.on_open();
        this.bus_client.subscribe(VISION_IMAGE, this.handle_image);
    }

    // The last image stays on screen; IF-04: "Image panel shows the last frame".
    on_close(): void {
        super.on_close();
        this.bus_client.unsubscribe(VISION_IMAGE, this.handle_image);
    }

    on_image(jpeg: Uint8Array): void {
        const previous_url = this.image_url;
        // slice() copies the bytes into a plain ArrayBuffer, which Blob accepts.
        this.image_url = URL.createObjectURL(new Blob([jpeg.slice()], { type: JPEG_MIME_TYPE }));
        this.image_element.src = this.image_url;
        this.image_element.hidden = false;
        this.no_image_element.hidden = true;
        // Every frame gets its own URL; the old one is freed, or 10 frames a second would fill the memory.
        if (previous_url !== null) URL.revokeObjectURL(previous_url);
    }

    private create_no_image_element(): HTMLElement {
        const element = document.createElement("p");
        element.textContent = NO_IMAGE_TEXT;
        this.root.appendChild(element);
        return element;
    }

    private create_image_element(): HTMLImageElement {
        const element = document.createElement("img");
        element.alt = IMAGE_ALT_TEXT;
        element.style.maxWidth = IMAGE_MAX_WIDTH;
        element.hidden = true;
        this.root.appendChild(element);
        return element;
    }
}
