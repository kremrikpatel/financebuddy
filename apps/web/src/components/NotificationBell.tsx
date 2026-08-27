import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { http } from "@/lib/api";

interface Alert {
  id: string;
  type: string;
  severity: string;
  title: string;
  body: string | null;
  read_at: string | null;
}

export default function NotificationBell() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [open, setOpen] = useState(false);

  async function load() {
    try {
      const { data } = await http.get("/alerts", { params: { limit: 20 } });
      setAlerts(data);
    } catch {
      /* offline */
    }
  }

  useEffect(() => {
    load();
    // live updates over WebSocket
    let ws: WebSocket | null = null;
    const token = sessionStorage.getItem("fb.access");
    if (token) {
      const envApi = (import.meta as any).env?.VITE_API_URL;
      let wsUrl = "";
      if (envApi && envApi.startsWith("http")) {
        try {
          const url = new URL(envApi);
          const wsProto = url.protocol === "https:" ? "wss:" : "ws:";
          wsUrl = `${wsProto}//${url.host}/ws/notifications?token=${encodeURIComponent(token)}`;
        } catch {
          const proto = location.protocol === "https:" ? "wss:" : "ws:";
          wsUrl = `${proto}://${location.host}/ws/notifications?token=${encodeURIComponent(token)}`;
        }
      } else {
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        wsUrl = `${proto}://${location.host}/ws/notifications?token=${encodeURIComponent(token)}`;
      }
      try {
        ws = new WebSocket(wsUrl);
        ws.onmessage = (e) => {
          if (e.data.includes("alert")) load();
        };
      } catch {
        /* noop */
      }
    }
    return () => ws?.close();
  }, []);

  const unread = alerts.filter((a) => !a.read_at);

  async function markRead(id: string) {
    await http.post(`/alerts/${id}/read`).catch(() => {});
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, read_at: new Date().toISOString() } : a)));
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="btn-ghost relative size-10 rounded-xl"
        aria-label="notifications"
      >
        <Bell size={17} />
        {unread.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid size-4.5 min-w-[18px] place-items-center rounded-full bg-neg px-1 text-[10px] font-bold text-white">
            {unread.length}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 w-80 card p-2 max-h-96 overflow-auto">
            <p className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Alerts
            </p>
            {unread.length === 0 && alerts.length === 0 && (
              <p className="px-3 py-6 text-center text-sm text-muted">No alerts — all clear.</p>
            )}
            {[...unread, ...alerts.filter((a) => a.read_at)].slice(0, 15).map((a) => (
              <button
                key={a.id}
                onClick={() => markRead(a.id)}
                className={`block w-full rounded-xl px-3 py-2.5 text-left transition hover:bg-surface ${
                  a.severity === "critical" ? "border-l-2 border-neg" : a.severity === "warning" ? "border-l-2 border-amber-500" : ""
                } ${!a.read_at ? "bg-brand/5" : ""}`}
              >
                <p className="text-sm font-medium">{a.title}</p>
                {a.body && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{a.body}</p>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
