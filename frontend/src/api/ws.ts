import type { WSEvent, WSEventType } from '@/types';

type EventHandler = (event: WSEvent) => void;

const BASE_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30_000;
const MAX_RECONNECT_ATTEMPTS = 20;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private handlers = new Map<WSEventType, Set<EventHandler>>();
  private globalHandlers = new Set<EventHandler>();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private token: string | null = null;
  private intentionalClose = false;

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get reconnecting(): boolean {
    return this.reconnectTimer !== null;
  }

  connect(token: string): void {
    this.token = token;
    this.intentionalClose = false;
    this.reconnectAttempts = 0;
    this._connect();
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
  }

  on(eventType: WSEventType | '*', handler: EventHandler): void {
    if (eventType === '*') {
      this.globalHandlers.add(handler);
      return;
    }
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);
  }

  off(eventType: WSEventType | '*', handler: EventHandler): void {
    if (eventType === '*') {
      this.globalHandlers.delete(handler);
      return;
    }
    this.handlers.get(eventType)?.delete(handler);
  }

  send(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  private _connect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    const wsBase =
      import.meta.env.VITE_WS_URL ||
      `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
    const url = `${wsBase}/ws?token=${encodeURIComponent(this.token || '')}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as WSEvent;
        this._dispatch(parsed);
      } catch {
        // ignore non-JSON messages
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      if (!this.intentionalClose) {
        this._scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
    };
  }

  private _dispatch(event: WSEvent): void {
    this.globalHandlers.forEach((h) => h(event));
    const typed = this.handlers.get(event.type);
    if (typed) {
      typed.forEach((h) => h(event));
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      return;
    }
    const delay = Math.min(
      BASE_RECONNECT_DELAY * Math.pow(2, this.reconnectAttempts),
      MAX_RECONNECT_DELAY,
    );
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this._connect();
    }, delay);
  }
}

export const wsManager = new WebSocketManager();
export default wsManager;
