/**
 * The app's single realtime connection (`/ws/notifications`), shared by alerts and AI Coach
 * streaming. Reconnects with backoff while signed in; closes on sign-out.
 */
import { useAuth } from "@/stores/auth";

type Listener = (frame: unknown, raw: string) => void;
type Status = "idle" | "connecting" | "open" | "closed";

const listeners = new Set<Listener>();
const statusListeners = new Set<(s: Status) => void>();
let socket: WebSocket | null = null;
let socketToken: string | null = null;
let status: Status = "idle";
let retry = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
let pingTimer: ReturnType<typeof setInterval> | undefined;

function wsUrl(token: string): string {
  const q = `/ws/notifications?token=${encodeURIComponent(token)}`;
  const envApi = (import.meta as any).env?.VITE_API_URL as string | undefined;
  if (envApi && envApi.startsWith("http")) {
    try {
      const url = new URL(envApi);
      return `${url.protocol === "https:" ? "wss:" : "ws:"}//${url.host}${q}`;
    } catch {
      /* fall through to same-origin */
    }
  }
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}${q}`;
}

function setStatus(next: Status) {
  status = next;
  statusListeners.forEach((l) => l(next));
}

function teardown() {
  clearTimeout(reconnectTimer);
  clearInterval(pingTimer);
  const s = socket;
  socket = null;
  socketToken = null;
  if (s && s.readyState <= WebSocket.OPEN) s.close();
}

function connect() {
  const token = useAuth.getState().accessToken;
  if (!token || typeof WebSocket === "undefined") return;
  if (socket && socketToken === token && socket.readyState <= WebSocket.OPEN) return;
  teardown();
  socketToken = token;
  setStatus("connecting");
  let s: WebSocket;
  try {
    s = new WebSocket(wsUrl(token));
  } catch {
    setStatus("closed");
    return;
  }
  socket = s;
  s.onopen = () => {
    retry = 0;
    setStatus("open");
    pingTimer = setInterval(() => send({ type: "ping" }), 25_000);
  };
  s.onmessage = (e) => {
    const raw = typeof e.data === "string" ? e.data : "";
    let frame: unknown = raw;
    try {
      frame = JSON.parse(raw);
    } catch {
      /* non-JSON frames are passed through raw */
    }
    listeners.forEach((l) => l(frame, raw));
  };
  s.onclose = () => {
    if (socket !== s) return;
    clearInterval(pingTimer);
    socket = null;
    setStatus("closed");
    if (useAuth.getState().accessToken && listeners.size) {
      reconnectTimer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** retry++));
    }
  };
}

function send(frame: object): boolean {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(frame));
    return true;
  }
  return false;
}

export const realtime = {
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    connect();
    return () => {
      listeners.delete(listener);
    };
  },
  onStatus(listener: (s: Status) => void): () => void {
    statusListeners.add(listener);
    return () => {
      statusListeners.delete(listener);
    };
  },
  status: () => status,
  send,
  /** Resolves true once the socket is open, false after `timeoutMs`. */
  whenOpen(timeoutMs = 3000): Promise<boolean> {
    if (socket?.readyState === WebSocket.OPEN) return Promise.resolve(true);
    connect();
    return new Promise((resolve) => {
      const done = (ok: boolean) => {
        clearTimeout(timer);
        off();
        resolve(ok);
      };
      const off = realtime.onStatus((s) => s === "open" && done(true));
      const timer = setTimeout(() => done(false), timeoutMs);
    });
  },
};

// Follow the session: reconnect with a rotated token, close on sign-out.
useAuth.subscribe((state, prev) => {
  if (state.accessToken === prev.accessToken) return;
  if (!state.accessToken) {
    teardown();
    setStatus("idle");
  } else if (listeners.size) {
    connect();
  }
});
