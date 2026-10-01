import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";

/**
 * AI Coach dock + hub, end to end in the browser. The REST API and the realtime socket are
 * replaced by a small in-memory fake, so no backend or database is needed.
 */

type Action = { id: string; type: string; status: string; summary: Record<string, unknown> };
type Msg = { id: string; role: "user" | "assistant"; content: string; created_at: string; blocks: []; actions: Action[] };
type Thread = { id: string; title: string; source_tab: string; context: { path: string }; pinned: boolean; created_at: string; updated_at: string; messages: Msg[] };

async function mockBackend(page: Page) {
  const threads = new Map<string, Thread>();
  const sends: { thread_id?: string; message: string }[] = [];
  const decisions: { messageId: string; actionId: string; decision: string }[] = [];
  const now = () => new Date().toISOString();
  const pendingOf = (t: Thread) =>
    t.messages.flatMap((m) => m.actions.filter((a) => a.status === "pending").map((a) => ({ a, m })));
  const threadOut = (t: Thread) => ({
    ...t, messages: undefined, preview: t.messages.at(-1)?.content ?? null, pending_actions: pendingOf(t).length,
  });

  await page.addInitScript(() => sessionStorage.setItem("fb.access", "e2e-test-token"));

  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = req.method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/auth/me") return json({ id: "u1", email: "e2e@example.test", full_name: null, locale: "en", base_currency: "USD", mfa_enabled: false });
    if (path === "/health") return json({ status: "ok", llm_providers: ["anthropic"] });
    if (path === "/chat/threads" && method === "GET") {
      const q = url.searchParams.get("q")?.toLowerCase();
      const list = [...threads.values()].filter(
        (t) => !q || t.title.toLowerCase().includes(q) || t.messages.some((m) => m.content.toLowerCase().includes(q)),
      );
      return json(list.map(threadOut));
    }
    const msgs = path.match(/^\/chat\/threads\/([^/]+)\/messages$/);
    if (msgs) return json(threads.get(msgs[1])?.messages ?? []);
    const one = path.match(/^\/chat\/threads\/([^/]+)$/);
    if (one && method === "PATCH") {
      const t = threads.get(one[1])!;
      Object.assign(t, req.postDataJSON());
      return json(threadOut(t));
    }
    if (one && method === "DELETE") {
      threads.delete(one[1]);
      return route.fulfill({ status: 204 });
    }
    if (path === "/chat/actions" && method === "GET") {
      return json([...threads.values()].flatMap((t) => pendingOf(t).map(({ a, m }) => ({
        ...a, message_id: m.id, thread_id: t.id, thread_title: t.title, source_tab: t.source_tab, created_at: m.created_at,
      }))));
    }
    const decide = path.match(/^\/chat\/actions\/([^/]+)\/([^/]+)$/);
    if (decide && method === "POST") {
      const { decision } = req.postDataJSON();
      decisions.push({ messageId: decide[1], actionId: decide[2], decision });
      const action = [...threads.values()].flatMap((t) => t.messages).find((m) => m.id === decide[1])!.actions.find((a) => a.id === decide[2])!;
      action.status = decision === "confirm" ? "confirmed" : "cancelled";
      return json(action);
    }
    return method === "GET" ? json([]) : json({});
  });

  await page.routeWebSocket(/\/ws\/notifications/, (ws) => {
    ws.onMessage((raw) => {
      const frame = JSON.parse(String(raw));
      if (frame.type !== "chat.send") return;
      sends.push({ thread_id: frame.thread_id, message: frame.message });
      let thread = frame.thread_id ? threads.get(frame.thread_id) : undefined;
      if (!thread) {
        const path = frame.page_context || "/";
        thread = {
          id: randomUUID(), title: frame.message.slice(0, 60), source_tab: path.split("/")[1] || "dashboard",
          context: { path }, pinned: false, created_at: now(), updated_at: now(), messages: [],
        };
        threads.set(thread.id, thread);
      }
      const wantsGoal = /goal/i.test(frame.message);
      const reply: Msg = {
        id: randomUUID(), role: "assistant", created_at: now(), blocks: [],
        content: wantsGoal ? "Here is a goal you could set up." : `Coach reply to: ${frame.message}`,
        actions: wantsGoal
          ? [{ id: "act-1", type: "create_goal", status: "pending", summary: { name: "Emergency fund", target_minor: 500000, monthly_amount_minor: 25000, currency: "USD" } }]
          : [],
      };
      thread.messages.push({ id: randomUUID(), role: "user", content: frame.message, created_at: now(), blocks: [], actions: [] }, reply);
      thread.updated_at = now();
      const rid = frame.request_id;
      ws.send(JSON.stringify({ type: "chat.started", request_id: rid, thread_id: thread.id }));
      ws.send(JSON.stringify({ type: "chat.delta", request_id: rid, text: reply.content }));
      ws.send(JSON.stringify({ type: "chat.done", request_id: rid, thread_id: thread.id, reply }));
    });
  });

  return { threads, sends, decisions };
}

/** Ask from the collapsed dock bar on the current tab and wait for the reply. */
async function askInDock(page: Page, text: string, expectReply: string) {
  await page.getByTestId("coach-dock-input").fill(text);
  await page.getByTestId("coach-dock-input").press("Enter");
  const panel = page.getByTestId("coach-panel");
  await expect(panel.getByText(expectReply)).toBeVisible();
  return panel;
}

const nav = (page: Page, name: string) =>
  page.getByRole("complementary", { name: "Main navigation" }).getByRole("link", { name, exact: true }).click();

test("threads started in docks on two tabs appear in the hub and can be resumed", async ({ page }) => {
  const api = await mockBackend(page);

  await page.goto("/goals");
  const goalsPanel = await askInDock(page, "Am I on track for my savings?", "Coach reply to: Am I on track for my savings?");
  await goalsPanel.getByRole("button", { name: "Close" }).click();

  await nav(page, "Debt Payoff");
  const debtsPanel = await askInDock(page, "Which debt first?", "Coach reply to: Which debt first?");
  await debtsPanel.getByRole("button", { name: "Close" }).click();

  // Client-side navigation keeps the shared store: both threads show with their origin tab.
  await nav(page, "AI Coach");
  const rows = page.getByTestId("coach-hub-thread");
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Am I on track for my savings?" })).toContainText("Goals");
  await expect(rows.filter({ hasText: "Which debt first?" })).toContainText("Debt Payoff");

  // Filter by source tab.
  await page.getByLabel("Filter by tab").selectOption("debts");
  await expect(rows).toHaveCount(1);
  await page.getByLabel("Filter by tab").selectOption("");
  await expect(rows).toHaveCount(2);

  // Resume the Goals thread in the hub and continue it.
  await rows.filter({ hasText: "Am I on track for my savings?" }).getByRole("button").first().click();
  await expect(page.getByText("Started on Goals")).toBeVisible();
  const composer = page.getByRole("textbox", { name: "Ask anything about your money…" });
  await composer.fill("And next month?");
  await composer.press("Enter");
  await expect(page.getByRole("paragraph").filter({ hasText: "Coach reply to: And next month?" })).toBeVisible();
  // The list preview follows the shared store without a refetch.
  await expect(rows.filter({ hasText: "Am I on track for my savings?" })).toContainText("Coach reply to: And next month?");
  const goalsThread = [...api.threads.values()].find((t) => t.source_tab === "goals")!;
  expect(api.sends.at(-1)?.thread_id).toBe(goalsThread.id);
  expect(goalsThread.messages).toHaveLength(4);

  // Jump back to the origin tab: the dock there reopens on the same thread.
  await page.getByTestId("coach-hub-jump").click();
  await expect(page).toHaveURL(/\/goals$/);
  await expect(page.getByTestId("coach-panel").getByText("Coach reply to: And next month?")).toBeVisible();
});

test("an AI action card changes nothing until Confirm, and pending actions aggregate in the hub", async ({ page }) => {
  const api = await mockBackend(page);

  await page.goto("/goals");
  const panel = await askInDock(page, "Set up an emergency fund goal", "Here is a goal you could set up.");
  await expect(panel.getByTestId("action-card")).toHaveAttribute("data-status", "pending");
  expect(api.decisions).toHaveLength(0);
  await panel.getByRole("button", { name: "Close" }).click();

  await nav(page, "AI Coach");
  const pending = page.getByTestId("coach-hub-pending");
  await expect(pending).toContainText("1 change waiting for you");
  expect(api.decisions).toHaveLength(0);

  await pending.getByRole("button", { name: "Confirm" }).click();
  await expect(pending).toBeHidden();
  expect(api.decisions).toEqual([{ messageId: expect.any(String), actionId: "act-1", decision: "confirm" }]);
});

test("hub can pin, rename and delete (with confirm) a thread", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/goals");
  const panel = await askInDock(page, "Quick question", "Coach reply to: Quick question");
  await panel.getByRole("button", { name: "Close" }).click();
  await nav(page, "AI Coach");

  const row = page.getByTestId("coach-hub-thread");
  await row.getByRole("button", { name: "Pin", exact: true }).click();
  await expect(row.getByRole("button", { name: "Unpin" })).toBeVisible();

  await row.getByRole("button", { name: "Rename conversation" }).click();
  await page.getByRole("dialog").getByRole("textbox").fill("Renamed thread");
  await page.getByTestId("coach-hub-dialog-submit").click();
  await expect(row).toContainText("Renamed thread");

  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("dialog")).toContainText("Delete conversation?");
  await page.getByTestId("coach-hub-dialog-submit").click();
  await expect(row).toHaveCount(0);
});
