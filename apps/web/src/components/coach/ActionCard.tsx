import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { CheckCircle2, ShieldQuestion, XCircle } from "lucide-react";
import { Badge, Button, Notice } from "@/components/ui";
import { fmtMoney } from "@/lib/utils";
import { useCoach, type CoachAction } from "@/stores/coach";

const INVALIDATE: Record<string, string[][]> = {
  create_goal: [["goals"]],
  create_budget: [["budgets"], ["budget-status"], ["budget-suggestions"]],
  recategorize: [["txns"], ["budget-status"]],
};

function Details({ action }: { action: CoachAction }) {
  const { t, i18n } = useTranslation();
  const s = action.summary ?? {};
  const money = (m: number) => fmtMoney(m ?? 0, s.currency || "USD", i18n.language);
  if (action.type === "create_goal") {
    return (
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t("goals.target")}</dt>
        <dd className="num text-end font-medium text-ink">{money(s.target_minor)}</dd>
        <dt className="text-muted">{t("goals.monthly")}</dt>
        <dd className="num text-end font-medium text-ink">{money(s.monthly_amount_minor)}</dd>
        {s.target_date && (
          <>
            <dt className="text-muted">{t("goals.targetDate")}</dt>
            <dd className="num text-end font-medium text-ink">{s.target_date}</dd>
          </>
        )}
      </dl>
    );
  }
  if (action.type === "create_budget") {
    return (
      <ul className="space-y-1 text-sm">
        {(s.envelopes ?? []).slice(0, 8).map((e: { name: string; allocated_minor: number }) => (
          <li key={e.name} className="flex justify-between gap-3">
            <span className="truncate text-ink">{e.name}</span>
            <span className="num shrink-0 font-medium text-ink">{money(e.allocated_minor)}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (action.type === "recategorize") {
    return <p className="text-sm text-ink">{t("coach.action.recategorizeBody", { count: s.count, total: money(s.total_minor) })}</p>;
  }
  return null;
}

function titleFor(action: CoachAction, t: (k: string, o?: any) => string) {
  const s = action.summary ?? {};
  if (action.type === "create_goal") return t("coach.action.createGoal", { name: s.name });
  if (action.type === "create_budget") return t("coach.action.createBudget", { name: s.name });
  if (action.type === "recategorize") return t("coach.action.recategorize", { merchant: s.merchant, category: s.category });
  return t("coach.action.generic");
}

/** An AI-proposed change. Nothing is written until the user presses Confirm. */
export default function ActionCard({ action, messageId }: { action: CoachAction; messageId?: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const decide = useCoach((s) => s.decideAction);
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(decision: "confirm" | "cancel") {
    if (!messageId) return;
    setBusy(decision);
    setError(null);
    try {
      await decide(messageId, action.id, decision);
      if (decision === "confirm") {
        for (const key of INVALIDATE[action.type] ?? []) void qc.invalidateQueries({ queryKey: key });
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("coach.action.failed"));
    } finally {
      setBusy(null);
    }
  }

  const pending = action.status === "pending";
  return (
    <section
      aria-label={titleFor(action, t)}
      data-testid="action-card"
      data-status={action.status}
      className="space-y-3 rounded-lg border border-brand/40 bg-brand/5 p-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2">
          <ShieldQuestion size={16} className="mt-0.5 shrink-0 text-brand" aria-hidden />
          <p className="text-sm font-semibold text-ink">{titleFor(action, t)}</p>
        </div>
        {action.status === "confirmed" && (
          <Badge tone="pos"><CheckCircle2 size={12} aria-hidden /> {t("coach.action.applied")}</Badge>
        )}
        {action.status === "cancelled" && (
          <Badge><XCircle size={12} aria-hidden /> {t("coach.action.dismissed")}</Badge>
        )}
      </div>
      <Details action={action} />
      {error && <Notice tone="neg">{error}</Notice>}
      {pending && (
        <>
          <p className="text-xs text-muted">{t("coach.action.nothingChanges")}</p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => run("cancel")} disabled={busy !== null || !messageId}>
              {busy === "cancel" ? t("common.loading") : t("common.cancel")}
            </Button>
            <Button size="sm" onClick={() => run("confirm")} disabled={busy !== null || !messageId}>
              {busy === "confirm" ? t("common.loading") : t("common.confirm")}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
