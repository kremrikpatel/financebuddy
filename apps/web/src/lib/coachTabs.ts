import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useCoach } from "@/stores/coach";

/** Tab id for a route: "/" -> "dashboard", "/budgets/x" -> "budgets". */
export function tabOf(pathname: string): string {
  return pathname.split("?")[0].split("/")[1] || "dashboard";
}

export const tabPath = (tab: string) => (tab === "dashboard" ? "/" : `/${tab}`);

const NAV_KEY: Record<string, string> = {
  dashboard: "nav.dashboard",
  transactions: "nav.transactions",
  budgets: "nav.budgets",
  goals: "nav.goals",
  debts: "nav.debts",
  coach: "nav.chat",
  family: "nav.family",
  tax: "nav.tax",
  connections: "nav.connections",
  "ai-eval": "nav.aiEval",
  settings: "nav.settings",
};

export const tabLabelKey = (tab: string | null | undefined) => NAV_KEY[tab ?? ""] ?? "nav.chat";

/** i18n keys for the tab's suggested prompts (3-4 per tab). */
export function promptKeys(tab: string): string[] {
  const id = tab in NAV_KEY ? tab.replace("-", "") : "dashboard";
  return ["p1", "p2", "p3", "p4"].map((p) => `coach.prompts.${id}.${p}`);
}

/**
 * Publish a compact summary of what the current tab shows, so the coach can answer about it.
 * Keep it small (the server caps it at 4 KB) and free of names/emails; amounts in major units.
 */
export function useCoachContext(summary: Record<string, unknown> | null) {
  const tab = tabOf(useLocation().pathname);
  const setSummary = useCoach((s) => s.setSummary);
  const json = summary ? JSON.stringify(summary) : "";
  useEffect(() => {
    setSummary(tab, json ? JSON.parse(json) : null);
  }, [tab, json, setSummary]);
}
