import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { useTranslation } from "react-i18next";
import { http } from "@/lib/api";
import { realtime } from "@/lib/ws";
import { cn } from "@/lib/utils";

interface Alert {
  id: string;
  type: string;
  severity: string;
  title: string;
  body: string | null;
  read_at: string | null;
}

export default function NotificationBell() {
  const { t } = useTranslation();
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
    void load();
    // live updates over the shared realtime socket
    return realtime.subscribe((_frame, raw) => {
      if (raw.includes("alert")) void load();
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const unread = alerts.filter((a) => !a.read_at);

  async function markRead(id: string) {
    await http.post(`/alerts/${id}/read`).catch(() => {});
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, read_at: new Date().toISOString() } : a)));
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="btn-ghost relative size-10 min-h-10 p-0"
        aria-label={unread.length ? t("alerts.labelUnread", { count: unread.length }) : t("alerts.label")}
        aria-expanded={open}
      >
        <Bell size={18} aria-hidden />
        {unread.length > 0 && (
          <span className="num absolute -end-0.5 -top-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-neg px-1 text-xs font-semibold text-white dark:text-surface" aria-hidden>
            {unread.length}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} aria-hidden />
          <div className="card absolute end-0 z-50 mt-2 max-h-96 w-80 max-w-[calc(100vw-2rem)] overflow-auto p-2 shadow-pop">
            <p className="px-3 py-2 text-sm font-semibold text-ink">{t("dash.alerts")}</p>
            {alerts.length === 0 && <p className="px-3 py-6 text-center text-sm text-muted">{t("alerts.empty")}</p>}
            {[...unread, ...alerts.filter((a) => a.read_at)].slice(0, 15).map((a) => (
              <button
                type="button"
                key={a.id}
                onClick={() => markRead(a.id)}
                className={cn(
                  "block w-full rounded-lg border-s-2 px-3 py-2.5 text-start transition-colors hover:bg-sunken",
                  a.severity === "critical" ? "border-neg" : a.severity === "warning" ? "border-warn" : "border-transparent",
                  !a.read_at && "bg-brand/5",
                )}
              >
                <p className="text-sm font-medium text-ink">{a.title}</p>
                {a.body && <p className="mt-0.5 line-clamp-2 text-sm text-muted">{a.body}</p>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
