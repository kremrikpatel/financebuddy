import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target, CheckCircle2, Plus } from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, Select, PageHeader, PageSkeleton, ErrorState, EmptyState, Meter, Field,
} from "@/components/ui";
import { fmtMoney, todayISO } from "@/lib/utils";
import { useAuth } from "@/stores/auth";
import { useCoachContext } from "@/lib/coachTabs";

export default function GoalsPage() {
  const { t, i18n } = useTranslation();
  const goals = useQuery({ queryKey: ["goals"], queryFn: () => http.get("/goals").then((r) => r.data) });
  const [open, setOpen] = useState(false);

  useCoachContext({
    goals: ((goals.data ?? []) as any[]).slice(0, 10).map((g) => ({
      name: g.name,
      currency: g.currency,
      saved: g.saved_minor / 100,
      target: g.target_minor / 100,
      pct: Math.round(g.pct ?? 0),
      monthly: (g.effective_monthly_minor ?? 0) / 100,
      months_to_complete: g.months_to_complete ?? null,
      target_date: g.target_date ?? null,
      on_track: Boolean(g.on_track),
      done: Boolean(g.completed_at),
    })),
  });

  if (goals.isLoading) return <PageSkeleton tiles={2} />;
  if (goals.isError) return <ErrorState onRetry={() => void goals.refetch()} />;
  const list = goals.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("goals.title")}
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus size={16} aria-hidden /> {t("goals.newGoal")}
          </Button>
        }
      />

      {list.length === 0 && (
        <Card>
          <EmptyState
            icon={<Target size={22} />}
            title={t("goals.emptyTitle")}
            body={t("goals.emptyBody")}
            action={<Button onClick={() => setOpen(true)}>{t("goals.newGoal")}</Button>}
          />
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {list.map((g: any) => {
          const money = (minor: number) => fmtMoney(minor, g.currency, i18n.language);
          const pct = Math.min(100, g.pct ?? 0);
          return (
            <Card key={g.id} as="article" className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <h2 className="flex min-w-0 items-center gap-2 font-semibold text-ink">
                  <Target size={16} className="shrink-0 text-brand" aria-hidden />
                  <span className="truncate">{g.name}</span>
                </h2>
                {g.completed_at ? (
                  <Badge tone="pos"><CheckCircle2 size={12} aria-hidden /> {t("goals.done")}</Badge>
                ) : g.on_track ? (
                  <Badge tone="brand">{t("goals.onTrack")}</Badge>
                ) : (
                  <Badge tone="warn">{t("goals.behind")}</Badge>
                )}
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <span className="num text-2xl font-semibold tracking-tight text-ink">{money(g.saved_minor)}</span>
                <span className="text-sm text-muted">
                  {t("goals.ofTarget", { amount: money(g.target_minor) })}
                </span>
              </div>
              <Meter
                value={pct}
                tone={g.completed_at ? "pos" : "brand"}
                label={t("goals.meterLabel", { name: g.name, pct: Math.round(pct) })}
              />
              <p className="text-sm text-muted">
                {[
                  g.effective_monthly_minor > 0 ? t("goals.perMonth", { amount: money(g.effective_monthly_minor) }) : null,
                  g.months_to_complete != null ? t("goals.monthsLeft", { count: g.months_to_complete }) : g.note,
                  g.target_date ? t("goals.byDate", { date: g.target_date }) : null,
                ].filter(Boolean).join(" · ")}
              </p>
              <ContributeButton id={g.id} name={g.name} />
            </Card>
          );
        })}
      </div>

      <NewGoalModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function ContributeButton({ id, name }: { id: string; name: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [amount, setAmount] = useState("");
  const [editing, setEditing] = useState(false);
  const mut = useMutation({
    mutationFn: () => http.post(`/goals/${id}/contribute`, { amount_minor: Math.round(Number(amount) * 100) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["goals"] }),
  });
  if (!editing)
    return (
      <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
        <Plus size={14} aria-hidden /> {t("goals.contribute")}
      </Button>
    );
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (amount) mut.mutate();
      }}
    >
      <Input
        className="h-9 py-0"
        type="number"
        inputMode="decimal"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        aria-label={t("goals.contributeTo", { name })}
        placeholder={t("goals.amount")}
        autoFocus
      />
      <Button size="sm" type="submit" disabled={!amount || mut.isPending}>{t("common.add")}</Button>
      <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>{t("common.cancel")}</Button>
    </form>
  );
}

function NewGoalModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const baseCurrency = useAuth((s) => s.user?.base_currency) || "USD";
  const [form, setForm] = useState({ name: "", target: "", monthly: "", percent: "10", strategy: "fixed_monthly", target_date: "" });

  async function create() {
    await http.post("/goals", {
      name: form.name,
      target_minor: Math.round(Number(form.target) * 100),
      currency: baseCurrency,
      strategy: form.strategy,
      monthly_amount_minor: Math.round(Number(form.monthly || 0) * 100),
      percent_of_income: Number(form.percent || 0),
      target_date: form.target_date || null,
    });
    void qc.invalidateQueries({ queryKey: ["goals"] });
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} title={t("goals.newGoal")}>
      <div className="space-y-4">
        <Field label={t("goals.name")}>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("goals.namePlaceholder")} autoFocus />
        </Field>
        <Field label={t("goals.targetAmount", { currency: baseCurrency })}>
          <Input type="number" inputMode="decimal" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} />
        </Field>
        <Field label={t("goals.strategy")}>
          <Select value={form.strategy} onChange={(e) => setForm({ ...form, strategy: e.target.value })}>
            <option value="fixed_monthly">{t("goals.fixedMonthly")}</option>
            <option value="percent_income">{t("goals.percentIncome")}</option>
          </Select>
        </Field>
        {form.strategy === "percent_income" ? (
          <Field label={t("goals.percentLabel")}>
            <Input type="number" inputMode="decimal" value={form.percent} onChange={(e) => setForm({ ...form, percent: e.target.value })} />
          </Field>
        ) : (
          <Field label={t("goals.monthly")}>
            <Input type="number" inputMode="decimal" value={form.monthly} onChange={(e) => setForm({ ...form, monthly: e.target.value })} />
          </Field>
        )}
        <Field label={t("goals.targetDate")} hint={t("common.optional")}>
          <Input type="date" min={todayISO()} value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={create} disabled={!form.name || !form.target}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
