import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { http } from "@/lib/api";
import { Badge, Button, Card, Input, Modal, SectionTitle, Select, Spinner } from "@/components/ui";
import { fmtMoney, todayISO } from "@/lib/utils";
import { useAuth } from "@/stores/auth";

export default function BudgetsPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const now = new Date();
  const [budgetId, setBudgetId] = useState<string>("");

  const budgets = useQuery({ queryKey: ["budgets"], queryFn: () => http.get("/budgets").then((r) => r.data) });
  const active = budgets.data?.[0];
  const selectedId = budgetId || active?.id;

  const status = useQuery({
    queryKey: ["budget-status", selectedId],
    queryFn: () => http.get(`/budgets/${selectedId}/status/${now.getFullYear()}/${now.getMonth() + 1}`).then((r) => r.data),
    enabled: Boolean(selectedId),
  });
  const cats = useQuery({ queryKey: ["cats"], queryFn: () => http.get("/categories").then((r) => r.data) });
  const suggestions = useQuery({ queryKey: ["budget-suggestions"], queryFn: () => http.get("/budgets/suggestions").then((r) => r.data.suggestions), enabled: !active });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => http.get("/accounts").then((r) => r.data) });

  const [createOpen, setCreateOpen] = useState(false);

  if (budgets.isLoading) return <Spinner label={t("common.loading")} />;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("budgets.title")}</h1>
        <Button onClick={() => setCreateOpen(true)}>+ {t("budgets.create")}</Button>
      </div>

      {!active && suggestions.data?.length > 0 && (
        <Card>
          <SectionTitle>{t("budgets.suggestions")}</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {(suggestions.data.slice(0, 10) as any[]).map((s: any) => (
              <Badge key={s.category_id} tone="brand">
                {(cats.data ?? []).find((c: any) => c.id === s.category_id)?.name}: {fmtMoney(s.suggested_monthly_minor)}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {active && (
        <>
          <Card className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">{active.name}</h2>
                <p className="text-xs text-muted">{active.strategy} · {active.currency}</p>
              </div>
              {status.data?.zero_based && (
                <Badge tone={status.data.zero_based.balanced ? "pos" : "warn"}>
                  {t("budgets.assignLeft")}: {fmtMoney(status.data.zero_based.unassigned_minor, active.currency, i18n.language)}
                </Badge>
              )}
            </div>
          </Card>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(status.data?.envelopes ?? []).map((e: any) => (
              <Card key={e.envelope_id} className={e.overspent ? "border-neg/40" : ""}>
                <div className="mb-2 flex items-center justify-between">
                  <p className="font-medium">{e.name}</p>
                  {e.overspent ? <Badge tone="neg">{t("budgets.overspent")}</Badge>
                    : e.pct_used >= 80 ? <Badge tone="warn">{e.pct_used}%</Badge>
                    : <Badge tone="pos">{e.pct_used}%</Badge>}
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-line">
                  <div
                    className={`h-full rounded-full transition-all ${e.overspent ? "bg-neg" : e.pct_used >= 80 ? "bg-amber-500" : "bg-brand"}`}
                    style={{ width: `${Math.min(100, e.pct_used)}%` }}
                  />
                </div>
                <div className="mt-3 flex justify-between text-xs text-muted tabular-nums">
                  <span>{t("budgets.spent")}: <b className="text-ink">{fmtMoney(e.spent_minor, active.currency, i18n.language)}</b></span>
                  <span>{t("budgets.remaining")}: <b className={e.overspent ? "text-neg" : ""}>{fmtMoney(e.remaining_minor, active.currency, i18n.language)}</b></span>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      {!active && (cats.data ?? []).length > 0 && (
        <Card><p className="text-sm text-muted">Create your first envelope budget to get AI-suggested allocations.</p></Card>
      )}

      <CreateBudgetModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}

function CreateBudgetModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
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
    <Modal open={open} onClose={onClose} title={t("budgets.create")}>
      <div className="max-h-[60vh] space-y-4 overflow-auto pr-1">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
        <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
          <option value="envelope">{t("budgets.envelope")}</option>
          <option value="zero_based">{t("budgets.zeroBased")}</option>
        </Select>
        <Input type="number" value={income} onChange={(e) => setIncome(e.target.value)} placeholder="Planned monthly income" />
        <div className="space-y-2">
          {(cats.data ?? []).filter((c: any) => c.kind === "expense" && c.name !== "Uncategorized").slice(0, 14).map((c: any) => {
            const sugg = suggestions.data?.find((s: any) => s.category_id === c.id);
            return (
              <div key={c.id} className="flex items-center gap-2">
                <span className="w-32 truncate text-sm">{c.name}</span>
                <Input type="number" className="h-9 py-0" value={allocations[c.id] ?? ""}
                  onChange={(e) => setAllocations((a) => ({ ...a, [c.id]: e.target.value }))} />
                {sugg && (
                  <button onClick={() => applySuggestion(c.id, sugg.suggested_monthly_minor)}
                    className="whitespace-nowrap rounded-lg bg-brand/10 px-2 py-1 text-xs text-brand hover:bg-brand/20"
                    title="Use 3-month average">
                    ~{fmtMoney(sugg.suggested_monthly_minor)}
                  </button>
                )}
              </div>
            );
          })}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={create}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
