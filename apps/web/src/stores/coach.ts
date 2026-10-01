/**
 * One conversation store for the per-tab coach dock and the AI Coach hub.
 * Streaming arrives over the shared realtime socket; if it cannot open, the existing
 * POST /chat/send endpoint is used instead (no streaming, same persistence).
 */
import { create } from "zustand";
import { http } from "@/lib/api";
import { realtime } from "@/lib/ws";

export type ChartBlock = { type: "chart"; kind: "bar" | "line"; title: string; series: { label: string; value: number }[] };
export type TxnBlock = {
  type: "transactions";
  items: { id: string; date: string; merchant: string; amount_minor: number; currency: string }[];
};
export type BudgetBlock = {
  type: "budget_delta";
  budget: string;
  currency: string;
  month: string;
  envelopes: { name: string; allocated_minor: number; spent_minor: number; remaining_minor: number; pct_used: number; overspent: boolean }[];
};
export type Block = ChartBlock | TxnBlock | BudgetBlock;

export interface CoachAction {
  id: string;
  type: "create_goal" | "create_budget" | "recategorize" | string;
  status: "pending" | "confirmed" | "cancelled";
  summary: Record<string, any>;
  result?: Record<string, unknown>;
}

export interface PendingAction extends CoachAction {
  message_id: string;
  thread_id: string;
  thread_title: string;
  source_tab: string | null;
  created_at: string | null;
}

export interface CoachMessage {
  key: string;
  id?: string;
  role: "user" | "assistant";
  content: string;
  state: "streaming" | "done" | "error" | "stopped";
  blocks: Block[];
  actions: CoachAction[];
  provider?: string | null;
  createdAt: string;
  requestId?: string;
  tool?: string | null;
  error?: string;
  prompt?: string;
}

export interface CoachThread {
  id: string;
  title: string;
  sourceTab: string | null;
  context: { path?: string; summary?: unknown } | null;
  pinned: boolean;
  createdAt: string | null;
  updatedAt: string | null;
  preview?: string | null;
  pendingActions: number;
}

export interface SendArgs {
  threadKey: string | null;
  text: string;
  tab: string;
  path: string;
  summary?: Record<string, unknown> | null;
}

interface ServerMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  created_at?: string | null;
  blocks?: Block[];
  actions?: CoachAction[];
}

interface CoachState {
  threads: Record<string, CoachThread>;
  messages: Record<string, CoachMessage[]>;
  activeByTab: Record<string, string | null>;
  summaries: Record<string, Record<string, unknown> | null>;
  pending: PendingAction[];
  inflight: Record<string, { key: string; args: SendArgs }>;
  degraded: boolean | null;
  threadsLoaded: boolean;

  setSummary: (tab: string, summary: Record<string, unknown> | null) => void;
  setActive: (tab: string, key: string | null) => void;
  loadThreads: (params?: Record<string, string>) => Promise<CoachThread[]>;
  loadMessages: (threadId: string) => Promise<void>;
  loadPending: () => Promise<void>;
  checkHealth: () => Promise<void>;
  send: (args: SendArgs) => Promise<void>;
  stop: (requestId: string) => void;
  retry: (key: string, messageKey: string) => void;
  decideAction: (messageId: string, actionId: string, decision: "confirm" | "cancel") => Promise<CoachAction>;
  renameThread: (id: string, title: string) => Promise<void>;
  pinThread: (id: string, pinned: boolean) => Promise<void>;
  deleteThread: (id: string) => Promise<void>;
  handleFrame: (frame: any) => void;
}

const isReal = (key: string | null | undefined): key is string => Boolean(key) && !key!.startsWith("pending:");
const nowIso = () => new Date().toISOString();
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
const MAX_SUMMARY_CHARS = 3500;

/** Keep the page summary under the server's 4 KB limit by trimming arrays first. */
function boundSummary(summary: Record<string, unknown> | null | undefined) {
  if (!summary) return undefined;
  let s: Record<string, unknown> = summary;
  for (let cap = 12; JSON.stringify(s).length > MAX_SUMMARY_CHARS && cap >= 0; cap -= 4) {
    s = Object.fromEntries(Object.entries(summary).map(([k, v]) => [k, Array.isArray(v) ? v.slice(0, cap) : v]));
  }
  return JSON.stringify(s).length > MAX_SUMMARY_CHARS ? undefined : s;
}

function toThread(t: any): CoachThread {
  return {
    id: t.id,
    title: t.title,
    sourceTab: t.source_tab ?? null,
    context: t.context ?? null,
    pinned: Boolean(t.pinned),
    createdAt: t.created_at ?? null,
    updatedAt: t.updated_at ?? null,
    preview: t.preview ?? null,
    pendingActions: t.pending_actions ?? 0,
  };
}

function toMessage(m: ServerMessage): CoachMessage {
  return {
    key: m.id,
    id: m.id,
    role: m.role,
    content: m.content,
    state: "done",
    blocks: m.blocks ?? [],
    actions: m.actions ?? [],
    provider: m.provider ?? null,
    createdAt: m.created_at ?? nowIso(),
  };
}

export const useCoach = create<CoachState>((set, get) => {
  /** Apply `fn` to the placeholder assistant message for `requestId`. */
  const patchReply = (requestId: string, fn: (m: CoachMessage) => CoachMessage) => {
    const flight = get().inflight[requestId];
    if (!flight) return;
    set((s) => ({
      messages: {
        ...s.messages,
        [flight.key]: (s.messages[flight.key] ?? []).map((m) => (m.requestId === requestId && m.role === "assistant" ? fn(m) : m)),
      },
    }));
  };

  /** Move an optimistic conversation from its pending key to the real thread id. */
  const adopt = (requestId: string, threadId: string) => {
    const flight = get().inflight[requestId];
    if (!flight || flight.key === threadId) return;
    const from = flight.key;
    set((s) => {
      const messages = { ...s.messages, [threadId]: [...(s.messages[threadId] ?? []), ...(s.messages[from] ?? [])] };
      delete messages[from];
      const activeByTab = Object.fromEntries(Object.entries(s.activeByTab).map(([tab, k]) => [tab, k === from ? threadId : k]));
      const threads = s.threads[threadId]
        ? s.threads
        : {
            ...s.threads,
            [threadId]: {
              id: threadId,
              title: flight.args.text.slice(0, 60),
              sourceTab: flight.args.tab,
              context: { path: flight.args.path, summary: flight.args.summary ?? null },
              pinned: false,
              createdAt: nowIso(),
              updatedAt: nowIso(),
              preview: flight.args.text,
              pendingActions: 0,
            },
          };
      return { messages, activeByTab, threads, inflight: { ...s.inflight, [requestId]: { ...flight, key: threadId } } };
    });
  };

  const finish = (requestId: string, threadId: string, reply: ServerMessage) => {
    adopt(requestId, threadId);
    patchReply(requestId, (m) => ({
      ...m,
      id: reply.id,
      content: reply.content,
      blocks: reply.blocks ?? [],
      actions: reply.actions ?? [],
      provider: reply.provider ?? null,
      state: "done",
      tool: null,
    }));
    const newPending = (reply.actions ?? []).filter((a) => a.status === "pending");
    set((s) => {
      const thread = s.threads[threadId];
      const { [requestId]: _done, ...inflight } = s.inflight;
      return {
        inflight,
        threads: thread
          ? {
              ...s.threads,
              [threadId]: { ...thread, updatedAt: nowIso(), preview: reply.content.slice(0, 140), pendingActions: thread.pendingActions + newPending.length },
            }
          : s.threads,
        pending: [
          ...newPending.map((a) => ({
            ...a,
            message_id: reply.id,
            thread_id: threadId,
            thread_title: thread?.title ?? "",
            source_tab: thread?.sourceTab ?? null,
            created_at: nowIso(),
          })),
          ...s.pending,
        ],
      };
    });
  };

  const fail = (requestId: string, detail: string, stateName: "error" | "stopped" = "error") => {
    patchReply(requestId, (m) => ({ ...m, state: stateName, error: detail, tool: null }));
    set((s) => {
      const { [requestId]: _gone, ...inflight } = s.inflight;
      return { inflight };
    });
  };

  const sendOverHttp = async (requestId: string, frame: Record<string, unknown>) => {
    try {
      const { data } = await http.post("/chat/send", frame);
      if (get().inflight[requestId]) finish(requestId, data.thread_id, data.reply);
    } catch (err: any) {
      if (!get().inflight[requestId]) return;
      const detail = err?.response?.data?.detail;
      fail(requestId, typeof detail === "string" ? detail : "");
    }
  };

  return {
    threads: {},
    messages: {},
    activeByTab: {},
    summaries: {},
    pending: [],
    inflight: {},
    degraded: null,
    threadsLoaded: false,

    setSummary: (tab, summary) => set((s) => ({ summaries: { ...s.summaries, [tab]: summary } })),
    setActive: (tab, key) => set((s) => ({ activeByTab: { ...s.activeByTab, [tab]: key } })),

    async loadThreads(params) {
      const { data } = await http.get("/chat/threads", { params });
      const list = (data as any[]).map(toThread);
      if (!params || Object.keys(params).length === 0) {
        set({ threads: Object.fromEntries(list.map((t) => [t.id, t])), threadsLoaded: true });
      } else {
        set((s) => ({ threads: { ...s.threads, ...Object.fromEntries(list.map((t) => [t.id, t])) } }));
      }
      return list;
    },

    async loadMessages(threadId) {
      const { data } = await http.get(`/chat/threads/${threadId}/messages`);
      const streaming = (get().messages[threadId] ?? []).filter((m) => m.state === "streaming");
      set((s) => ({ messages: { ...s.messages, [threadId]: [...(data as ServerMessage[]).map(toMessage), ...streaming] } }));
    },

    async loadPending() {
      const { data } = await http.get("/chat/actions", { params: { status: "pending" } });
      set({ pending: data as PendingAction[] });
    },

    async checkHealth() {
      try {
        const { data } = await http.get("/health");
        const providers: string[] = data?.llm_providers ?? [];
        set({ degraded: providers.length === 0 || providers.every((p) => p === "offline-mock") });
      } catch {
        set({ degraded: null });
      }
    },

    async send(args) {
      const text = args.text.trim();
      if (!text) return;
      const requestId = uid();
      const key = args.threadKey ?? `pending:${requestId}`;
      const summary = boundSummary(args.summary);
      const userMsg: CoachMessage = { key: `u-${requestId}`, role: "user", content: text, state: "done", blocks: [], actions: [], createdAt: nowIso() };
      const reply: CoachMessage = {
        key: `a-${requestId}`, role: "assistant", content: "", state: "streaming", blocks: [], actions: [],
        createdAt: nowIso(), requestId, prompt: text,
      };
      set((s) => ({
        messages: { ...s.messages, [key]: [...(s.messages[key] ?? []), userMsg, reply] },
        activeByTab: args.threadKey ? s.activeByTab : { ...s.activeByTab, [args.tab]: key },
        inflight: { ...s.inflight, [requestId]: { key, args: { ...args, text, summary } } },
      }));

      const frame = {
        thread_id: isReal(args.threadKey) ? args.threadKey : undefined,
        message: text,
        agent_mode: "auto",
        page_context: args.path,
        page_summary: summary,
      };
      if ((await realtime.whenOpen(3000)) && realtime.send({ type: "chat.send", request_id: requestId, ...frame })) return;
      await sendOverHttp(requestId, frame);
    },

    stop(requestId) {
      realtime.send({ type: "chat.cancel", request_id: requestId });
      fail(requestId, "", "stopped");
    },

    retry(key, messageKey) {
      const list = get().messages[key] ?? [];
      const idx = list.findIndex((m) => m.key === messageKey);
      const failed = list[idx];
      if (!failed?.prompt) return;
      const thread = get().threads[key];
      set((s) => ({ messages: { ...s.messages, [key]: list.filter((_, i) => i !== idx && i !== idx - 1) } }));
      void get().send({
        threadKey: isReal(key) ? key : null,
        text: failed.prompt,
        tab: thread?.sourceTab ?? "dashboard",
        path: thread?.context?.path ?? "/",
        summary: null,
      });
    },

    async decideAction(messageId, actionId, decision) {
      const { data } = await http.post(`/chat/actions/${messageId}/${actionId}`, { decision });
      const updated = data as CoachAction;
      set((s) => {
        const messages = Object.fromEntries(
          Object.entries(s.messages).map(([k, list]) => [
            k,
            list.map((m) => (m.id === messageId ? { ...m, actions: m.actions.map((a) => (a.id === actionId ? { ...a, ...updated } : a)) } : m)),
          ]),
        );
        const owner = s.pending.find((p) => p.id === actionId)?.thread_id
          ?? Object.entries(s.messages).find(([, list]) => list.some((m) => m.id === messageId))?.[0];
        const threads = owner && s.threads[owner]
          ? { ...s.threads, [owner]: { ...s.threads[owner], pendingActions: Math.max(0, s.threads[owner].pendingActions - 1) } }
          : s.threads;
        return { messages, threads, pending: s.pending.filter((p) => p.id !== actionId) };
      });
      return updated;
    },

    async renameThread(id, title) {
      const { data } = await http.patch(`/chat/threads/${id}`, { title });
      set((s) => ({ threads: { ...s.threads, [id]: { ...s.threads[id], title: data.title } } }));
    },

    async pinThread(id, pinned) {
      await http.patch(`/chat/threads/${id}`, { pinned });
      set((s) => ({ threads: { ...s.threads, [id]: { ...s.threads[id], pinned } } }));
    },

    async deleteThread(id) {
      await http.delete(`/chat/threads/${id}`);
      set((s) => {
        const { [id]: _t, ...threads } = s.threads;
        const { [id]: _m, ...messages } = s.messages;
        return {
          threads,
          messages,
          activeByTab: Object.fromEntries(Object.entries(s.activeByTab).map(([tab, k]) => [tab, k === id ? null : k])),
          pending: s.pending.filter((p) => p.thread_id !== id),
        };
      });
    },

    handleFrame(frame) {
      if (!frame || typeof frame !== "object" || typeof frame.type !== "string" || !frame.type.startsWith("chat.")) return;
      const rid = frame.request_id as string;
      if (!rid || !get().inflight[rid]) return;
      switch (frame.type) {
        case "chat.started":
          adopt(rid, frame.thread_id);
          break;
        case "chat.delta":
          patchReply(rid, (m) => ({ ...m, content: m.content + frame.text, tool: null }));
          break;
        case "chat.tool":
          // Text before a tool call is scratch work; the final reply replaces it.
          patchReply(rid, (m) => ({ ...m, content: "", tool: frame.name }));
          break;
        case "chat.done":
          finish(rid, frame.thread_id, frame.reply);
          break;
        case "chat.cancelled":
          fail(rid, "", "stopped");
          break;
        case "chat.error":
          fail(rid, typeof frame.detail === "string" ? frame.detail : "");
          break;
      }
    },
  };
});

let listening = false;
/** Start routing realtime chat frames into the store (idempotent; call once signed in). */
export function listenForCoachFrames() {
  if (listening) return;
  listening = true;
  realtime.subscribe((frame) => useCoach.getState().handleFrame(frame));
}
