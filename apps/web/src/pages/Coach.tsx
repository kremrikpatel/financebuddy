import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ArrowUpRight, MessageSquare, Pencil, Pin, PinOff, Plus, Search, Trash2 } from "lucide-react";
import { Badge, Button, Card, EmptyState, IconButton, Input, Modal, Notice, PageHeader, Select } from "@/components/ui";
import ActionCard from "@/components/coach/ActionCard";
import ChatThreadView from "@/components/coach/ChatThreadView";
import { tabLabelKey, tabPath } from "@/lib/coachTabs";
import { cn } from "@/lib/utils";
import { useCoach, type CoachThread } from "@/stores/coach";

const TAB = "coach";
const SOURCE_TABS = ["dashboard", "transactions", "budgets", "goals", "debts", "tax", "family", "connections", "settings", "ai-eval", "coach"];
const RANGES = { all: 0, today: 1, week: 7, month: 30 } as const;
type Range = keyof typeof RANGES;
type Dialog = { kind: "rename" | "delete"; thread: CoachThread } | null;

function rangeStart(range: Range) {
  if (range === "all") return 0;
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - (RANGES[range] - 1));
  return d.getTime();
}

/** Link back to the tab a thread came from; the dock there reopens on the same thread. */
const jumpBackHref = (thread: CoachThread) =>
  `${thread.context?.path || tabPath(thread.sourceTab ?? "dashboard")}?coach=${thread.id}`;

export default function CoachPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const threadParam = params.get("thread");
  const threadKey = useCoach((s) => s.activeByTab[TAB] ?? null);
  const threadsById = useCoach((s) => s.threads);
  const pending = useCoach((s) => s.pending);
  const { setActive, loadMessages, loadThreads, loadPending, renameThread, pinThread, deleteThread } = useCoach.getState();

  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Set<string> | null>(null);
  const [source, setSource] = useState("");
  const [range, setRange] = useState<Range>("all");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const active = threadKey ? threadsById[threadKey] : undefined;

  useEffect(() => {
    loadThreads().catch(() => undefined);
    loadPending().catch(() => undefined);
  }, [loadThreads, loadPending]);

  // Resume a thread chosen in the list or opened from a tab dock ("Open in AI Coach").
  useEffect(() => {
    if (!threadParam) return;
    setActive(TAB, threadParam);
    loadMessages(threadParam).catch(() => {
      /* unknown or deleted thread: the empty state is shown */
    });
  }, [threadParam, setActive, loadMessages]);

  // Text search runs on the server (it also matches message content); debounce keystrokes.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setMatches(null);
      return;
    }
    const id = setTimeout(() => {
      loadThreads({ q })
        .then((list) => setMatches(new Set(list.map((x) => x.id))))
        .catch(() => setMatches(new Set()));
    }, 250);
    return () => clearTimeout(id);
  }, [query, loadThreads]);

  // Tab and date filters run on the shared store, so threads started in any dock show up instantly.
  const threads = useMemo(() => {
    const since = rangeStart(range);
    return Object.values(threadsById)
      .filter((x) => !matches || matches.has(x.id))
      .filter((x) => !source || x.sourceTab === source)
      .filter((x) => !since || new Date(x.updatedAt ?? x.createdAt ?? 0).getTime() >= since)
      .sort((a, b) => Number(b.pinned) - Number(a.pinned) || (b.updatedAt ?? "").localeCompare(a.updatedAt ?? ""));
  }, [threadsById, matches, source, range]);

  const open = (id: string | null) => {
    if (id) {
      setParams({ thread: id });
      return;
    }
    setParams({});
    setActive(TAB, null);
  };

  async function submitDialog() {
    if (!dialog) return;
    setBusy(true);
    setFailed(false);
    try {
      if (dialog.kind === "rename") await renameThread(dialog.thread.id, title.trim());
      else {
        await deleteThread(dialog.thread.id);
        if (threadKey === dialog.thread.id) open(null);
      }
      setDialog(null);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  const fmtDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleDateString(i18n.language, { month: "short", day: "numeric" }) : "";
  const tabName = (tab: string | null) => t(tabLabelKey(tab));

  return (
    <div className="flex h-[calc(100dvh-8rem)] min-h-[28rem] flex-col gap-4">
      <PageHeader
        title={t("coach.title")}
        actions={
          <Button variant="secondary" onClick={() => open(null)}>
            <Plus size={16} aria-hidden /> {t("coach.newChat")}
          </Button>
        }
      />
      <div className="flex min-h-0 flex-1 gap-4">
        {/* Thread list: full width on mobile until a thread is open; fixed column from lg. */}
        <aside
          aria-label={t("coach.hub.conversations")}
          className={cn("min-h-0 w-full flex-col gap-3 overflow-y-auto lg:flex lg:w-80 lg:shrink-0", threadKey ? "hidden" : "flex")}
          data-testid="coach-hub-list"
        >
          {pending.length > 0 && (
            <section aria-labelledby="pending-heading" className="space-y-2" data-testid="coach-hub-pending">
              <h2 id="pending-heading" className="text-sm font-semibold text-ink">
                {t("coach.hub.pending", { count: pending.length })}
              </h2>
              {pending.map((a) => (
                <div key={a.id} className="space-y-1">
                  <button
                    type="button"
                    onClick={() => open(a.thread_id)}
                    className="block max-w-full truncate text-xs text-muted hover:text-brand"
                  >
                    {t("coach.hub.fromThread", { title: a.thread_title || t("coach.title"), tab: tabName(a.source_tab) })}
                  </button>
                  <ActionCard action={a} messageId={a.message_id} />
                </div>
              ))}
            </section>
          )}

          <div className="space-y-2">
            <label className="relative block">
              <span className="sr-only">{t("coach.hub.search")}</span>
              <Search size={16} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
              <Input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("coach.hub.search")}
                className="ps-9"
                data-testid="coach-hub-search"
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <Select value={source} onChange={(e) => setSource(e.target.value)} aria-label={t("coach.hub.filterTab")}>
                <option value="">{t("coach.hub.allTabs")}</option>
                {SOURCE_TABS.map((tab) => (
                  <option key={tab} value={tab}>{tabName(tab)}</option>
                ))}
              </Select>
              <Select value={range} onChange={(e) => setRange(e.target.value as Range)} aria-label={t("coach.hub.filterDate")}>
                {(Object.keys(RANGES) as Range[]).map((r) => (
                  <option key={r} value={r}>{t(`coach.hub.range.${r}`)}</option>
                ))}
              </Select>
            </div>
          </div>

          {threads.length === 0 ? (
            <EmptyState icon={<MessageSquare size={20} />} title={t("coach.hub.emptyTitle")} body={t("coach.hub.emptyBody")} />
          ) : (
            <ul className="space-y-1.5">
              {threads.map((x) => (
                <li
                  key={x.id}
                  data-testid="coach-hub-thread"
                  className={cn(
                    "rounded-lg border bg-raised p-2.5 transition-colors",
                    x.id === threadKey ? "border-brand bg-brand/5" : "border-line hover:border-brand/40",
                  )}
                >
                  <div className="flex items-start gap-1">
                    <button
                      type="button"
                      onClick={() => open(x.id)}
                      aria-current={x.id === threadKey || undefined}
                      className="min-w-0 flex-1 rounded text-start"
                    >
                      <span className="flex items-center gap-1.5">
                        {x.pinned && <Pin size={12} className="shrink-0 text-brand" aria-label={t("coach.hub.pinned")} />}
                        <span className="truncate text-sm font-medium text-ink">{x.title || t("coach.title")}</span>
                      </span>
                      {x.preview && <span className="mt-0.5 line-clamp-2 block text-xs text-muted">{x.preview}</span>}
                    </button>
                    <IconButton
                      label={x.pinned ? t("coach.hub.unpin") : t("coach.hub.pin")}
                      icon={x.pinned ? <PinOff size={15} /> : <Pin size={15} />}
                      onClick={() => void pinThread(x.id, !x.pinned)}
                      className="size-8 min-h-8"
                    />
                    <IconButton
                      label={t("coach.hub.rename")}
                      icon={<Pencil size={15} />}
                      onClick={() => {
                        setTitle(x.title);
                        setDialog({ kind: "rename", thread: x });
                      }}
                      className="size-8 min-h-8"
                    />
                    <IconButton
                      label={t("common.delete")}
                      icon={<Trash2 size={15} />}
                      onClick={() => setDialog({ kind: "delete", thread: x })}
                      className="size-8 min-h-8"
                    />
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                    <Link
                      to={jumpBackHref(x)}
                      className="inline-flex items-center gap-0.5 text-brand hover:underline"
                      aria-label={t("coach.hub.jumpBack", { tab: tabName(x.sourceTab) })}
                    >
                      {tabName(x.sourceTab)} <ArrowUpRight size={12} className="rtl:-scale-x-100" aria-hidden />
                    </Link>
                    <span className="num">{fmtDate(x.updatedAt ?? x.createdAt)}</span>
                    {x.pendingActions > 0 && <Badge tone="warn">{t("coach.hub.pendingBadge", { count: x.pendingActions })}</Badge>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <Card className={cn("min-h-0 flex-1 flex-col overflow-hidden p-0 lg:flex", threadKey ? "flex" : "hidden")}>
          <header className="flex items-center gap-2 border-b border-line py-2 pe-2 ps-2 lg:ps-4">
            <IconButton
              label={t("coach.hub.back")}
              icon={<ArrowLeft size={18} className="rtl:-scale-x-100" />}
              onClick={() => open(null)}
              className="lg:hidden"
            />
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-sm font-semibold text-ink">{active?.title || t("coach.newChat")}</h2>
              {active?.sourceTab && (
                <p className="truncate text-xs text-muted">{t("coach.hub.startedOn", { tab: tabName(active.sourceTab) })}</p>
              )}
            </div>
            {active && active.sourceTab !== TAB && (
              <Link to={jumpBackHref(active)} className="btn-ghost min-h-9 shrink-0 px-3 py-1.5 text-sm" data-testid="coach-hub-jump">
                <span className="hidden sm:inline">{t("coach.hub.jumpBack", { tab: tabName(active.sourceTab) })}</span>
                <span className="sm:hidden">{tabName(active.sourceTab)}</span>
                <ArrowUpRight size={14} className="rtl:-scale-x-100" aria-hidden />
              </Link>
            )}
          </header>
          <ChatThreadView threadKey={threadKey} tab={active?.sourceTab ?? TAB} path={active?.context?.path ?? "/coach"} className="flex-1" />
        </Card>
      </div>

      <Modal
        open={dialog !== null}
        onClose={() => {
          setDialog(null);
          setFailed(false);
        }}
        title={dialog?.kind === "delete" ? t("coach.hub.deleteTitle") : t("coach.hub.rename")}
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submitDialog();
          }}
        >
          {dialog?.kind === "rename" ? (
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} aria-label={t("coach.hub.rename")} autoFocus />
          ) : (
            <p className="text-sm text-ink">{t("coach.hub.deleteBody", { title: dialog?.thread.title })}</p>
          )}
          {failed && <Notice tone="neg">{t("common.errorBody")}</Notice>}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDialog(null)}>{t("common.cancel")}</Button>
            <Button
              type="submit"
              variant={dialog?.kind === "delete" ? "danger" : "primary"}
              disabled={busy || (dialog?.kind === "rename" && !title.trim())}
              data-testid="coach-hub-dialog-submit"
            >
              {dialog?.kind === "delete" ? t("common.delete") : t("common.save")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
