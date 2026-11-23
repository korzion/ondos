import { Bus, nowS, Payload, topicMatches, Callback } from "@shared/bus/bus";
import { topicInfo } from "@shared/topics";

// Pause between first-connect attempts. Bus.connect() already waits up to 5 s for the broker
// before it gives up, so a short pause is enough to avoid hammering a broker that is starting.
const CONNECT_RETRY_DELAY_MS = 2000;

function wait_ms(duration_ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, duration_ms));
}

export class BusClient {
    private bus: Bus;
    private callbacks: Map<string, Set<Callback>> = new Map(); // pattern -> callbacks
    private latest_messages: Map<string, Payload> = new Map(); // topic -> message

    // A handler calls all callbacks for a pattern.
    // It is the callback passed to Bus.subscribe() and is the one that is unsubscribed from the bus when the last callback for a pattern is removed.
    private handlers: Map<string, Callback> = new Map(); // pattern -> handler

    constructor(bus: Bus) {
        this.bus = bus;
    }

    publish(topic: string, data: Payload): boolean {
        if (!this.is_connected()) {
            console.warn(`publish ${topic} failed: bus is not connected`);
            return false;
        }

        try {
            this.bus.publish(topic, data);
            return true;
        } catch (e) {
            console.warn(`publish ${topic} failed: ${(e as Error).message}`);
            return false;
        }
    }

    subscribe(pattern: string, callback: Callback): void {
        if (!this.callbacks.has(pattern)) {
            this.callbacks.set(pattern, new Set());
            const handler: Callback = (msg_topic, msg, t_recv_s) => this.dispatch(pattern, msg_topic, msg, t_recv_s);
            this.handlers.set(pattern, handler);
            this.bus.subscribe(pattern, handler, { acceptReplay: true });
        }

        this.callbacks.get(pattern)!.add(callback);

        // give the new subscriber what we already have, so it doesn't start empty
        for (const [topic, msg] of this.latest_messages) {
            if (topicMatches(pattern, topic) && topicInfo(topic).retained) {
                this.call_safely(callback, topic, msg, nowS()); // t_recv_s is now, since we don't know when the message was originally received
            }
        }
    }

    unsubscribe(pattern: string, callback: Callback): void {
        const callbacks = this.callbacks.get(pattern);
        if (!callbacks) return;
        callbacks.delete(callback);

        // If there are no more callbacks for this pattern, unsubscribe from the bus and remove the handler.
        if (callbacks.size === 0) {
            this.callbacks.delete(pattern);
            const handler = this.handlers.get(pattern);

            if (handler) {
                this.bus.unsubscribe(pattern, handler);
                this.handlers.delete(pattern);
            }

            this.forget_unreceived_topics(pattern);
        }
    }

    private forget_unreceived_topics(pattern: string): void {
        for (const topic of this.latest_messages.keys()) {
            const is_still_received = [...this.callbacks.keys()].some((p) => topicMatches(p, topic));
            if (topicMatches(pattern, topic) && !is_still_received) this.latest_messages.delete(topic);
        }
    }

    get_latest(topic: string): Payload | null {
        return this.latest_messages.get(topic) ?? null;
    }

    async connect(): Promise<void> {
        while (!this.is_connected()) {
            try {
                await this.bus.connect();
            } catch (e) {
                console.warn(`${(e as Error).message}, retrying in ${CONNECT_RETRY_DELAY_MS} ms`);
                await wait_ms(CONNECT_RETRY_DELAY_MS);
            }
        }
    }

    is_connected(): boolean {
        return this.bus.isConnected();
    }

    private call_safely(callback: Callback, topic: string, msg: Payload, t_recv_s: number): void {
        try {
            callback(topic, msg, t_recv_s);
        } catch (e) {
            console.warn(`callback for ${topic} failed: ${(e as Error).message}`);
        }
    }

    private dispatch(pattern: string, topic: string, msg: Payload, t_recv_s: number): void {
        this.latest_messages.set(topic, msg);
        const callbacks = this.callbacks.get(pattern);
        if (callbacks) {
            for (const cb of callbacks) {
                this.call_safely(cb, topic, msg, t_recv_s);
            }
        }
    }
}