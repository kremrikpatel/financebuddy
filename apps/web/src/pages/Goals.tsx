import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Target, CheckCircle2 } from "lucide-react";
import { http } from "@/lib/api";
import { Badge, Button, Card, Input, Modal, Spinner } from "@/components/ui";
import { fmtMoney, todayISO } from "@/lib/utils";
import { useAuth } from "@/stores/auth";

export default function GoalsPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const goals = useQuery({ queryKey: ["goals"], queryFn: () => http.get("/goals").then((r) => r.data) });
  const [open, setOpen] = useState(false);

  if (goals.isLoading) return <Spinner label={t("common.loading")} />;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("goals.title")}</h1>
        <Button onClick={() => setOpen(true)}>+ {t("goals.newGoal")}</Button>
      </div>

      {(goals.data ?? []).length === 0 && (
        <Card><p className="text-sm text-muted">No goals yet — create one and the AI advisor will track it.</p></Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {(goals.data ?? []).map((g: any) => (
          <Card key={g.id}>
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 font-medium"><Target size={16} className="text-brand" />{g.name}</div>
              {g.completed_at ? <Badge tone="pos"><CheckCircle2 size={12} /> done</Badge>
                : g.on_track ? <Badge tone="brand">{t("goals.onTrack")}</Badge> : <Badge tone="warn">{t("goals.behind")}</Badge>}
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-line">
              <div className="h-full rounded-full bg-gradient-to-r from-brand to-violet-500 transition-all"
                style={{ width: `${Math.min(100, g.pct ?? 0)}%` }} />
            </div>
            <div className="mt-3 flex justify-between text-sm tabular-nums">
              <span className="text-muted">{fmtMoney(g.saved_minor, g.currency, i18n.language)}</span>
              <span className="font-semibold">{fmtMoney(g.target_minor, g.currency, i18n.language)}</span>
            </div>
            <p className="mt-2 text-xs text-muted">
              {g.effective_monthly_minor > 0 && <>≈ {fmtMoney(g.effective_monthly_minor, g.currency, i18n.language)}/mo · </>}
              {g.months_to_complete != null ? `${g.months_to_complete} months left` : g.note}
              {g.target_date && ` · by ${g.target_date}`}
            </p>
            <ContributeButton id={g.id} />
          </Card>
        ))}
      </div>

      <NewGoalModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function ContributeButton({ id }: { id: string }) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState("");
  const [editing, setEditing] = useState(false);
  const mut = useMutation({
    mutationFn: () => http.post(`/goals/${id}/contribute`, { amount_minor: Math.round(Number(amount) * 100) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["goals"] }),
  });
  if (!editing)
    return (
      <Button size="sm" variant="outline" className="mt-3" onClick={() => setEditing(true)}>
        + Add funds
      </Button>
    );
  return (
    <div className="mt-3 flex gap-2">
      <Input className="h-9 py-0" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount" autoFocus />
      <Button size="sm" onClick={() => mut.mutate()} disabled={!amount}>OK</Button>
    </div>
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
      <div className="space-y-3">
        <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Emergency fund" autoFocus />
        <Input type="number" value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} placeholder="Target amount" />
        <select value={form.strategy} onChange={(e) => setForm({ ...form, strategy: e.target.value })} className="input">
          <option value="fixed_monthly">Fixed monthly amount</option>
          <option value="percent_income">% of income (auto-adjusts)</option>
        </select>
        {form.strategy === "percent_income" ? (
          <Input type="number" value={form.percent} onChange={(e) => setForm({ ...form, percent: e.target.value })} placeholder="% of income" />
        ) : (
          <Input type="number" value={form.monthly} onChange={(e) => setForm({ ...form, monthly: e.target.value })} placeholder="Monthly contribution" />
        )}
        <Input type="date" min={todayISO()} value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={create} disabled={!form.name || !form.target}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
