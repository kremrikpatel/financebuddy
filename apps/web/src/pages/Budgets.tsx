import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus, Wallet } from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, SectionTitle, Select, PageHeader, PageSkeleton, ErrorState, EmptyState, Meter, Field,
} from "@/components/ui";
import { fmtMoney, todayISO, cn } from "@/lib/utils";
import { useAuth } from "@/stores/auth";
import { useCoachContext } from "@/lib/coachTabs";

export default function BudgetsPage() {
  const { t, i18n } = useTranslation();
  const now = new Date();

  const budgets = useQuery({ queryKey: ["budgets"], queryFn: () => http.get("/budgets").then((r) => r.data) });
  const active = budgets.data?.[0];
  const selectedId = active?.id;

  const status = useQuery({
    queryKey: ["budget-status", selectedId],
    queryFn: () => http.get(`/budgets/${selectedId}/status/${now.getFullYear()}/${now.getMonth() + 1}`).then((r) => r.data),
    enabled: Boolean(selectedId),
  });
  const cats = useQuery({ queryKey: ["cats"], queryFn: () => http.get("/categories").then((r) => r.data) });
  const suggestions = useQuery({ queryKey: ["budget-suggestions"], queryFn: () => http.get("/budgets/suggestions").then((r) => r.data.suggestions), enabled: !active });

  const [createOpen, setCreateOpen] = useState(false);

  useCoachContext(active ? {
    month: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
    budget: active.name,
    strategy: active.strategy,
    currency: active.currency,
    envelopes: (status.data?.envelopes ?? []).slice(0, 12).map((e: any) => ({
      name: e.name,
      pct_used: e.pct_used,
      spent: e.spent_minor / 100,
      remaining: e.remaining_minor / 100,
      overspent: e.overspent,
    })),
  } : { budget: null });

  if (budgets.isLoading) return <PageSkeleton tiles={3} />;
  if (budgets.isError) return <ErrorState onRetry={() => void budgets.refetch()} />;

  const money = (minor: number, currency?: string) => fmtMoney(minor, currency ?? active?.currency, i18n.language);
  const monthLabel = now.toLocaleDateString(i18n.language, { month: "long", year: "numeric" });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("budgets.title")}
        subtitle={active ? monthLabel : undefined}
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus size={16} aria-hidden /> {t("budgets.create")}
          </Button>
        }
      />

      {!active && suggestions.data?.length > 0 && (
        <Card as="section">
          <SectionTitle>{t("budgets.suggestions")}</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {(suggestions.data.slice(0, 10) as any[]).map((s: any) => (
              <Badge key={s.category_id} tone="brand">
                {(cats.data ?? []).find((c: any) => c.id === s.category_id)?.name}: {money(s.suggested_monthly_minor)}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {active && (
        <>
          <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <h2 className="font-semibold text-ink">{active.name}</h2>
              <p className="text-sm text-muted">
                {t(active.strategy === "zero_based" ? "budgets.zeroBased" : "budgets.envelope")} · {active.currency}
              </p>
            </div>
            {status.data?.zero_based && (
              <Badge tone={status.data.zero_based.balanced ? "pos" : "warn"}>
                {t("budgets.assignLeft")}: <span className="num">{money(status.data.zero_based.unassigned_minor)}</span>
              </Badge>
            )}
          </Card>

          {status.isError ? (
            <ErrorState onRetry={() => void status.refetch()} />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {(status.data?.envelopes ?? []).map((e: any) => {
                const tone = e.overspent ? "neg" : e.pct_used >= 80 ? "warn" : "brand";
                return (
                  <Card key={e.envelope_id} className={cn("space-y-3", e.overspent && "border-neg/40")}>
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate font-medium text-ink">{e.name}</p>
                      {e.overspent ? (
                        <Badge tone="neg">{t("budgets.overspent")}</Badge>
                      ) : (
                        <span className={cn("num text-sm font-semibold", tone === "warn" ? "text-warn" : "text-muted")}>
                          {e.pct_used}%
                        </span>
                      )}
                    </div>
                    <Meter value={e.pct_used} tone={tone} label={t("budgets.meterLabel", { name: e.name, pct: e.pct_used })} />
                    <div className="flex justify-between gap-2 text-sm">
                      <span className="text-muted">
                        {t("budgets.spent")} <b className="num font-semibold text-ink">{money(e.spent_minor)}</b>
                      </span>
                      <span className="text-muted">
                        {t("budgets.remaining")}{" "}
                        <b className={cn("num font-semibold", e.overspent ? "text-neg" : "text-ink")}>{money(e.remaining_minor)}</b>
                      </span>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}

      {!active && (
        <Card>
          <EmptyState
            icon={<Wallet size={22} />}
            title={t("budgets.emptyTitle")}
            body={t("budgets.emptyBody")}
            action={<Button onClick={() => setCreateOpen(true)}>{t("budgets.create")}</Button>}
          />
        </Card>
      )}

      <CreateBudgetModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}

function CreateBudgetModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const baseCurrency = useAuth((s) => s.user?.base_currency) || "USD";
  const [name, setName] = useState("Monthly");
  const [strategy, setStrategy] = useState("envelope");
  const [income, setIncome] = useState("");
  const [allocations, setAllocations] = useState<Record<string, string>>({});
  const cats = useQuery({ queryKey: ["cats"], queryFn: () => http.get("/categories").then((r) => r.data) });
  const suggestions = useQuery({ queryKey: ["budget-suggestions"], queryFn: () => http.get("/budgets/suggestions").then((r) => r.data.suggestions), enabled: open });

  function applySuggestion(catId: string, value: number) {
    setAllocations((a) => ({ ...a, [catId]: String(Math.round(value / 100)) }));
  }

  async function create() {
    const envelopes = Object.entries(allocations)
      .filter(([, v]) => Number(v) > 0)
      .map(([category_id, v]) => ({ category_id, allocated_minor: Math.round(Number(v) * 100) }));
    await http.post("/budgets", {
      name,
      strategy,
      start_date: todayISO(),
      income_planned_minor: Math.round(Number(income || 0) * 100),
      currency: baseCurrency,
      envelopes,
    });
    void qc.invalidateQueries();
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title={t("budgets.create")} size="lg">
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("budgets.name")}>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t("budgets.strategy")}>
            <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              <option value="envelope">{t("budgets.envelope")}</option>
              <option value="zero_based">{t("budgets.zeroBased")}</option>
            </Select>
          </Field>
        </div>
        <Field label={t("budgets.plannedIncome", { currency: baseCurrency })}>
          <Input type="number" inputMode="decimal" value={income} onChange={(e) => setIncome(e.target.value)} />
        </Field>
        <fieldset className="space-y-2">
          <legend className="label mb-2">{t("budgets.allocations", { currency: baseCurrency })}</legend>
          {(cats.data ?? []).filter((c: any) => c.kind === "expense" && c.name !== "Uncategorized").slice(0, 14).map((c: any) => {
            const sugg = suggestions.data?.find((s: any) => s.category_id === c.id);
            return (
              <div key={c.id} className="flex items-center gap-2">
                <label htmlFor={`alloc-${c.id}`} className="w-32 shrink-0 truncate text-sm text-ink">{c.name}</label>
                <Input
                  id={`alloc-${c.id}`}
                  type="number"
                  inputMode="decimal"
                  className="h-9 py-0"
                  value={allocations[c.id] ?? ""}
                  onChange={(e) => setAllocations((a) => ({ ...a, [c.id]: e.target.value }))}
                />
                {sugg && (
                  <button
                    type="button"
                    onClick={() => applySuggestion(c.id, sugg.suggested_monthly_minor)}
                    className="chip min-h-9 bg-brand/10 px-2.5 text-brand hover:bg-brand/20"
                    title={t("budgets.useAverage")}
                  >
                    <span className="num">~{fmtMoney(sugg.suggested_monthly_minor, baseCurrency, i18n.language)}</span>
                  </button>
                )}
              </div>
            );
          })}
        </fieldset>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={create}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
