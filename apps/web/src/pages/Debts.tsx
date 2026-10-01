import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Landmark, Plus } from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, SectionTitle, PageHeader, PageSkeleton, ErrorState, EmptyState, StatTile,
  ChartFrame, Field,
} from "@/components/ui";
import { fmtMoney } from "@/lib/utils";
import { useChartColors } from "@/lib/theme";
import { useAuth } from "@/stores/auth";
import { useCoachContext } from "@/lib/coachTabs";

export default function DebtsPage() {
  const { t, i18n } = useTranslation();
  const colors = useChartColors();
  const baseCurrency = useAuth((s) => s.user?.base_currency) || "USD";
  const [extra, setExtra] = useState("100");
  const debts = useQuery({ queryKey: ["debts"], queryFn: () => http.get("/debts").then((r) => r.data) });
  const plan = useQuery({
    queryKey: ["payoff", extra],
    queryFn: () => http.post("/debts/payoff-plan", { extra_payment_minor: Math.round(Number(extra || 0) * 100) }).then((r) => r.data),
    enabled: (debts.data ?? []).length > 0,
  });
  const [open, setOpen] = useState(false);

  useCoachContext({
    currency: baseCurrency,
    extra_monthly_payment: Number(extra || 0),
    debts: ((debts.data ?? []) as any[]).slice(0, 10).map((d) => ({
      name: d.name,
      balance: (d.principal_minor ?? 0) / 100,
      apr_pct: (d.apr_bps ?? 0) / 100,
      min_payment: (d.min_payment_minor ?? 0) / 100,
    })),
    avalanche: plan.data ? { months: plan.data.avalanche.months, interest: plan.data.avalanche.total_interest_minor / 100 } : null,
    snowball: plan.data ? { months: plan.data.snowball.months, interest: plan.data.snowball.total_interest_minor / 100 } : null,
  });

  if (debts.isLoading) return <PageSkeleton tiles={3} />;
  if (debts.isError) return <ErrorState onRetry={() => void debts.refetch()} />;
  const list = debts.data ?? [];
  const money = (minor: number) => fmtMoney(minor, baseCurrency, i18n.language);
  const rtl = i18n.dir() === "rtl";

  const chartData = (plan?.data?.avalanche?.schedule ?? [])
    .slice(0, 24)
    .map((m: any) => ({
      month: `M${m.month}`,
      total: Object.values(m.balances).reduce((s: number, v: any) => s + Number(v), 0) / 100,
    }));

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("debts.title")}
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus size={16} aria-hidden /> {t("debts.addDebt")}
          </Button>
        }
      />

      {list.length === 0 && (
        <Card>
          <EmptyState
            icon={<Landmark size={22} />}
            title={t("debts.emptyTitle")}
            body={t("debts.emptyBody")}
            action={<Button onClick={() => setOpen(true)}>{t("debts.addDebt")}</Button>}
          />
        </Card>
      )}

      {plan.isError && <ErrorState onRetry={() => void plan.refetch()} />}

      {plan.data && list.length > 0 && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <StatTile
              label={t("debts.avalanche")}
              value={t("debts.months", { count: plan.data.avalanche.months })}
              hint={t("debts.interest", { amount: money(plan.data.avalanche.total_interest_minor) })}
            />
            <StatTile
              label={t("debts.snowball")}
              value={t("debts.months", { count: plan.data.snowball.months })}
              hint={t("debts.interest", { amount: money(plan.data.snowball.total_interest_minor) })}
            />
            <StatTile
              label={t("debts.interestSaved")}
              tone="pos"
              value={<span className="num">{money(plan.data.interest_saved_by_avalanche_minor)}</span>}
              hint={<Badge tone="pos">{t("debts.monthsFaster", { count: plan.data.months_saved_by_avalanche })}</Badge>}
            />
          </div>

          <Card as="section">
            <SectionTitle
              right={
                <label className="flex items-center gap-2 text-sm text-muted">
                  {t("debts.extraPayment")}
                  <Input
                    type="number"
                    inputMode="decimal"
                    className="h-9 w-28 py-0"
                    value={extra}
                    onChange={(e) => setExtra(e.target.value)}
                  />
                </label>
              }
            >
              {t("debts.trajectory")}
            </SectionTitle>
            <ChartFrame summary={t("debts.trajectorySummary", { count: chartData.length })}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={colors.grid} />
                  <XAxis dataKey="month" tick={{ fontSize: 12, fill: colors.muted }} axisLine={false} tickLine={false} reversed={rtl} />
                  <YAxis tick={{ fontSize: 12, fill: colors.muted }} axisLine={false} tickLine={false} width={56} orientation={rtl ? "right" : "left"} />
                  <Tooltip
                    formatter={(v: number) => money(v * 100)}
                    contentStyle={{ background: colors.raised, border: `1px solid ${colors.grid}`, borderRadius: 8, color: colors.ink }}
                    labelStyle={{ color: colors.muted }}
                    cursor={{ fill: colors.grid, opacity: 0.5 }}
                  />
                  <Bar dataKey="total" name={t("debts.balance")} fill={colors.brand} radius={[4, 4, 0, 0]} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Card>

          <Card as="section">
            <SectionTitle>{t("debts.payoffOrder")}</SectionTitle>
            <ol className="space-y-2 text-sm">
              {(plan.data.avalanche.payoff_order ?? []).map((name: string, i: number) => (
                <li key={name} className="flex items-center gap-3">
                  <span className="num grid size-7 shrink-0 place-items-center rounded-full bg-brand/10 text-sm font-semibold text-brand">{i + 1}</span>
                  <span className="text-ink">{name}</span>
                </li>
              ))}
            </ol>
          </Card>
        </>
      )}

      <NewDebtModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function NewDebtModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const baseCurrency = useAuth((s) => s.user?.base_currency) || "USD";
  const [f, setF] = useState({ name: "", principal: "", apr: "", min: "" });
  async function create() {
    await http.post("/debts", {
      name: f.name,
      principal_minor: Math.round(Number(f.principal) * 100),
      apr_bps: Math.round(Number(f.apr) * 100),
      min_payment_minor: Math.round(Number(f.min) * 100),
      currency: baseCurrency,
    });
    void qc.invalidateQueries({ queryKey: ["debts"] });
    onClose();
  }
  return (
    <Modal open={open} onClose={onClose} title={t("debts.addDebt")}>
      <div className="space-y-4">
        <Field label={t("debts.name")}>
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder={t("debts.namePlaceholder")} autoFocus />
        </Field>
        <Field label={t("debts.balanceLabel", { currency: baseCurrency })}>
          <Input type="number" inputMode="decimal" value={f.principal} onChange={(e) => setF({ ...f, principal: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("debts.apr")}>
            <Input type="number" inputMode="decimal" step="0.01" value={f.apr} onChange={(e) => setF({ ...f, apr: e.target.value })} />
          </Field>
          <Field label={t("debts.minPayment")}>
            <Input type="number" inputMode="decimal" value={f.min} onChange={(e) => setF({ ...f, min: e.target.value })} />
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={create}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
