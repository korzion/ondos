import { Bus, nowS, Payload, topicMatches, Callback } from "@shared/bus/bus";
import { topicInfo } from "@shared/topics";

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
                callback(topic, msg, nowS()); // t_recv_s is now, since we don't know when the message was originally received
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

    // Connects to the broker and returns true if successful, false otherwise.
    connect(url: string): Promise<boolean> {
        return new Promise((resolve, reject) => {
            resolve(true);
            reject(false);
        });
    }

    on_connection_change(callback: (is_connected: boolean) => void): void {

    }

    is_connected(): boolean {
        return false;
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