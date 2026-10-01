import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowUp, Maximize2, Plus, Sparkles, X } from "lucide-react";
import { IconButton } from "@/components/ui";
import { useDialogBehavior } from "@/lib/hooks";
import { tabLabelKey, tabOf } from "@/lib/coachTabs";
import { cn } from "@/lib/utils";
import { useCoach } from "@/stores/coach";
import ChatThreadView, { type ChatThreadHandle } from "./ChatThreadView";

const MOBILE = "(max-width: 639px)";
const subscribeMobile = (cb: () => void) => {
  const mq = matchMedia(MOBILE);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** Bottom-docked AI coach, present on every tab (the Coach hub hosts its own chat). */
export default function CoachDock() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const tab = tabOf(location.pathname);
  const isMobile = useSyncExternalStore(subscribeMobile, () => matchMedia(MOBILE).matches, () => false);

  const threadKey = useCoach((s) => s.activeByTab[tab] ?? null);
  const threadTitle = useCoach((s) => (threadKey ? s.threads[threadKey]?.title : undefined));
  const setActive = useCoach((s) => s.setActive);
  const degraded = useCoach((s) => s.degraded);
  const checkHealth = useCoach((s) => s.checkHealth);

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const queued = useRef<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLInputElement>(null);
  const threadRef = useRef<ChatThreadHandle>(null);
  const titleId = useId();

  const close = () => {
    setOpen(false);
    requestAnimationFrame(() => barRef.current?.focus());
  };
  useDialogBehavior(panelRef, open && isMobile, close);

  useEffect(() => {
    if (degraded === null) void checkHealth();
  }, [degraded, checkHealth]);

  // Ctrl/Cmd+K toggles the coach from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Jump-back from the AI Coach hub (`?coach=<thread>`): reopen the dock on that thread.
  const resumeId = new URLSearchParams(location.search).get("coach");
  useEffect(() => {
    if (!resumeId || tab === "coach") return;
    setActive(tab, resumeId);
    useCoach.getState().loadMessages(resumeId).catch(() => {
      /* unknown or deleted thread: the empty state is shown */
    });
    setOpen(true);
    navigate({ pathname: location.pathname, search: "" }, { replace: true });
  }, [resumeId, tab, setActive, navigate, location.pathname]);

  // On open: send anything typed in the collapsed bar, then focus the composer.
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => {
      if (queued.current) {
        threadRef.current?.sendText(queued.current);
        queued.current = null;
      }
      threadRef.current?.focus();
    });
    return () => cancelAnimationFrame(id);
  }, [open]);

  if (tab === "coach") return null;

  const shortcut = isMac ? "⌘K" : "Ctrl K";
  const tabLabel = t(tabLabelKey(tab));

  return (
    <>
      {!open && (
        <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:start-64">
          <form
            className="pointer-events-auto mx-auto flex max-w-2xl items-center gap-2 rounded-2xl border border-line bg-raised/95 p-1.5 ps-3 shadow-pop backdrop-blur focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/25"
            onSubmit={(e) => {
              e.preventDefault();
              queued.current = draft.trim() || null;
              setDraft("");
              setOpen(true);
            }}
          >
            <Sparkles size={17} className="shrink-0 text-brand" aria-hidden />
            <input
              ref={barRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={t("coach.placeholderTab", { tab: tabLabel })}
              aria-label={t("coach.dockLabel", { tab: tabLabel })}
              className="min-w-0 flex-1 bg-transparent py-2 text-base text-ink outline-none placeholder:text-muted focus-visible:outline-none sm:text-sm"
              data-testid="coach-dock-input"
            />
            <kbd className="hidden rounded-md border border-line bg-sunken px-1.5 py-0.5 font-sans text-xs text-muted sm:inline">{shortcut}</kbd>
            <IconButton
              type="submit"
              variant={draft.trim() ? "primary" : "secondary"}
              label={draft.trim() ? t("coach.send") : t("coach.open")}
              icon={draft.trim() ? <ArrowUp size={17} /> : <Maximize2 size={16} />}
              className="size-9 min-h-9"
              data-testid="coach-dock-open"
            />
          </form>
        </div>
      )}

      {open && isMobile && <div className="fixed inset-0 z-40 bg-ink/40" onClick={close} aria-hidden />}

      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-modal={isMobile || undefined}
          aria-labelledby={titleId}
          tabIndex={-1}
          data-testid="coach-panel"
          onKeyDown={(e) => {
            if (!isMobile && e.key === "Escape") {
              e.preventDefault();
              close();
            }
          }}
          className={cn(
            "fixed z-50 flex animate-fadeUp flex-col border border-line bg-raised shadow-pop",
            isMobile
              ? "inset-x-0 bottom-0 h-[85dvh] rounded-t-2xl pb-safe"
              : "bottom-4 end-4 h-[min(680px,calc(100dvh-5rem))] w-[420px] rounded-2xl",
          )}
        >
          <header className="flex items-center gap-2 border-b border-line py-2 pe-2 ps-4">
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="truncate text-sm font-semibold text-ink">{threadTitle ?? t("coach.title")}</h2>
              <p className="truncate text-xs text-muted">{t("coach.contextOf", { tab: tabLabel })}</p>
            </div>
            <IconButton label={t("coach.newChat")} icon={<Plus size={18} />} onClick={() => setActive(tab, null)} />
            {threadKey && !threadKey.startsWith("pending:") && (
              <IconButton
                label={t("coach.openInHub")}
                icon={<Maximize2 size={16} />}
                onClick={() => {
                  setOpen(false);
                  navigate(`/coach?thread=${threadKey}`);
                }}
              />
            )}
            <IconButton label={t("coach.close")} icon={<X size={18} />} onClick={close} />
          </header>
          <ChatThreadView ref={threadRef} threadKey={threadKey} tab={tab} path={location.pathname} className="flex-1" />
        </div>
      )}
    </>
  );
}
