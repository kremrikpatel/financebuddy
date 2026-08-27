import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { http } from "@/lib/api";
import { Badge, Button, Card, Input, Modal, SectionTitle, Spinner } from "@/components/ui";
import { fmtMoney } from "@/lib/utils";
import { useAuth } from "@/stores/auth";

export default function DebtsPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [extra, setExtra] = useState("100");
  const debts = useQuery({ queryKey: ["debts"], queryFn: () => http.get("/debts").then((r) => r.data) });
  const plan = useQuery({
    queryKey: ["payoff", extra],
    queryFn: () => http.post("/debts/payoff-plan", { extra_payment_minor: Math.round(Number(extra || 0) * 100) }).then((r) => r.data),
    enabled: (debts.data ?? []).length > 0,
  });
  const [open, setOpen] = useState(false);

  if (debts.isLoading) return <Spinner label={t("common.loading")} />;
  const list = debts.data ?? [];

  const chartData = (plan?.data?.avalanche?.schedule ?? [])
    .slice(0, 24)
    .map((m: any) => ({
      month: `M${m.month}`,
      total: Object.values(m.balances).reduce((s: number, v: any) => s + Number(v), 0) / 100,
    }));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("debts.title")}</h1>
        <Button onClick={() => setOpen(true)}>+ {t("debts.addDebt")}</Button>
      </div>

      {list.length === 0 && (
        <Card><p className="text-sm text-muted">Track your first debt to unlock payoff simulations.</p></Card>
      )}

      {plan.data && list.length > 0 && (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Card><p className="text-xs uppercase text-muted">{t("debts.avalanche")}</p>
              <p className="mt-1 text-xl font-bold">{plan.data.avalanche.months} mo</p>
              <p className="text-xs text-muted">{fmtMoney(plan.data.avalanche.total_interest_minor)} interest</p></Card>
            <Card><p className="text-xs uppercase text-muted">{t("debts.snowball")}</p>
              <p className="mt-1 text-xl font-bold">{plan.data.snowball.months} mo</p>
              <p className="text-xs text-muted">{fmtMoney(plan.data.snowball.total_interest_minor)} interest</p></Card>
            <Card><p className="text-xs uppercase text-muted">{t("debts.interestSaved")}</p>
              <p className="mt-1 text-xl font-bold text-pos">{fmtMoney(plan.data.interest_saved_by_avalanche_minor)}</p>
              <Badge tone="pos">{plan.data.months_saved_by_avalanche} mo faster</Badge></Card>
          </div>

          <Card>
            <SectionTitle right={
              <Input type="number" className="h-9 w-32 py-0" value={extra}
                onChange={(e) => setExtra(e.target.value)}
                title={t("debts.extraPayment")} />
            }>Paydown trajectory ({fmtMoney(Number(extra || 0) * 100)}/mo extra)</SectionTitle>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={50} />
                  <Tooltip formatter={(v: number) => fmtMoney(v * 100)} />
                  <Bar dataKey="total" fill="#6366f1" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card>
            <SectionTitle>Payoff order</SectionTitle>
            <ol className="space-y-1.5 text-sm">
              {(plan.data.avalanche.payoff_order ?? []).map((name: string, i: number) => (
                <li key={name} className="flex items-center gap-2">
                  <span className="grid size-6 place-items-center rounded-full bg-brand/10 text-xs font-bold text-brand">{i + 1}</span>
                  {name}
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
      <div className="space-y-3">
        <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Name (e.g. Credit card)" autoFocus />
        <Input type="number" value={f.principal} onChange={(e) => setF({ ...f, principal: e.target.value })} placeholder="Balance" />
        <Input type="number" step="0.01" value={f.apr} onChange={(e) => setF({ ...f, apr: e.target.value })} placeholder="APR %" />
        <Input type="number" value={f.min} onChange={(e) => setF({ ...f, min: e.target.value })} placeholder="Minimum payment" />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={create}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
