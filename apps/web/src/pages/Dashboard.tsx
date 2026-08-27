import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import { TrendingUp, TrendingDown, Wallet, Sparkles, Mic } from "lucide-react";
import { http } from "@/lib/api";
import { Card, SectionTitle, Button, Input, Badge, Modal, Spinner, Select } from "@/components/ui";
import { fmtMoney, todayISO } from "@/lib/utils";
import { useSpeechRecognition } from "@/lib/hooks";

export default function DashboardPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [quickOpen, setQuickOpen] = useState(false);

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: () => http.get("/accounts").then((r) => r.data),
  });
  const txns = useQuery({
    queryKey: ["txns", "recent"],
    queryFn: () =>
      http
        .get("/transactions", { params: { limit: 500 } })
        .then((r) => r.data as Txn[]),
  });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => http.get("/alerts", { params: { limit: 6 } }).then((r) => r.data) });

  const currency = accounts.data?.[0]?.currency ?? "USD";
  const locale = i18n.language;

  const stats = useMemo(() => {
    const list = (txns.data ?? []) as Txn[];
    if (!list.length) return null;
    const cutoff = Date.now() - 30 * 86400e3;
    const recent = list.filter((x) => new Date(x.date).getTime() >= cutoff && !x.excluded);
    const income30 = recent.filter((x) => x.amount_minor > 0).reduce((s, x) => s + x.amount_minor, 0);
    const spend30 = recent.filter((x) => x.amount_minor < 0).reduce((s, x) => s - x.amount_minor, 0);
    const netWorth = (accounts.data ?? []).reduce((s: number, a: Account) => s + a.balance_minor, 0);
    const byCat = new Map<string, number>();
    for (const x of recent) {
      if (x.amount_minor < 0) byCat.set(x.category_name ?? t("txns.uncategorized"), (byCat.get(x.category_name ?? "") ?? 0) - x.amount_minor);
    }
    const topCats = [...byCat.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6)
      .map(([name, value]) => ({ name, value }));
    // monthly net series + simple forecast continuation
    const monthly = new Map<string, { income: number; spend: number }>();
    for (const x of list) {
      if (x.excluded) continue;
      const key = String(x.date).slice(0, 7);
      const b = monthly.get(key) ?? { income: 0, spend: 0 };
      if (x.amount_minor > 0) b.income += x.amount_minor / 100;
      else b.spend += -x.amount_minor / 100;
      monthly.set(key, b);
    }
    const series = [...monthly.entries()].sort().slice(-9).map(([month, v]) => ({
      month: month.slice(2), net: +(v.income - v.spend).toFixed(0), actual: true,
    }));
    const lastNets = series.map((s) => s.net).filter((_, i) => i >= series.length - 4);
    const trend = lastNets.length >= 2 ? lastNets[lastNets.length - 1] : 0;
    const fc1 = series.length ? Math.round(series[series.length - 1].net * 0.5 + trend * 0.5) : 0;
    series.push({ month: "F+1", net: fc1, actual: false }, { month: "F+2", net: Math.round(fc1 * 0.92), actual: false });
    return { income30, spend30, netWorth, topCats, series, savingsRate: income30 ? ((income30 - spend30) / income30) * 100 : 0 };
  }, [txns.data, accounts.data, t]);

  if (txns.isLoading || accounts.isLoading) return <Spinner label={t("common.loading")} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("nav.dashboard")}</h1>
        <Button onClick={() => setQuickOpen(true)}>
          <Sparkles size={16} /> {t("dash.quickAdd")}
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label={t("dash.netWorth")} value={fmtMoney(stats?.netWorth ?? 0, currency, locale)} icon={<Wallet size={18} />} />
        <Kpi label={t("dash.thisMonth")} value={fmtMoney(-(stats?.spend30 ?? 0), currency, locale)} tone="neg" icon={<TrendingDown size={18} />} />
        <Kpi label={t("dash.income")} value={fmtMoney(stats?.income30 ?? 0, currency, locale)} tone="pos" icon={<TrendingUp size={18} />} />
        <Kpi label={t("dash.savingsRate")} value={`${(stats?.savingsRate ?? 0).toFixed(1)}%`} icon={<Sparkles size={18} />} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <SectionTitle right={<Badge tone="brand">{t("dash.forecast")}</Badge>}>{t("dash.cashflow")}</SectionTitle>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stats?.series ?? []}>
                <defs>
                  <linearGradient id="net" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={44} />
                <Tooltip formatter={(v: number) => fmtMoney(v * 100, currency, locale)} />
                <Area type="monotone" dataKey="net" stroke="#6366f1" strokeWidth={2.5} fill="url(#net)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionTitle>{t("dash.topCategories")}</SectionTitle>
          <div className="flex items-center gap-2">
            <PieChart width={130} height={130}>
              <Pie data={stats?.topCats ?? []} dataKey="value" innerRadius={38} outerRadius={62} paddingAngle={3}>
                {(stats?.topCats ?? []).map((_: any, i: number) => (
                  <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                ))}
              </Pie>
            </PieChart>
            <ul className="space-y-1 text-xs text-muted">
              {(stats?.topCats ?? []).map((c: any, i: number) => (
                <li key={c.name} className="flex items-center gap-1.5 truncate">
                  <span className="size-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                  {c.name}
                </li>
              ))}
            </ul>
          </div>
          <SectionTitle>{t("dash.alerts")}</SectionTitle>
          <ul className="space-y-2">
            {(alerts.data ?? []).slice(0, 4).map((a: any) => (
              <li key={a.id} className="rounded-xl border border-line px-3 py-2 text-xs">
                <span className="font-medium">{a.title}</span>
                {a.body && <p className="mt-0.5 line-clamp-1 text-muted">{a.body}</p>}
              </li>
            ))}
            {(alerts.data ?? []).length === 0 && (
              <li className="rounded-xl bg-pos/10 px-3 py-2 text-xs text-pos">✓ All clear</li>
            )}
          </ul>
        </Card>
      </div>

      <QuickAddModal open={quickOpen} onClose={() => setQuickOpen(false)} onDone={() => { void qc.invalidateQueries(); }} />
    </div>
  );
}

const PALETTE = ["#6366f1", "#22c55e", "#f97316", "#0ea5e9", "#a855f7", "#ef4444"];

function Kpi({ label, value, tone, icon }: { label: string; value: string; tone?: "pos" | "neg"; icon?: React.ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between text-muted">
        <p className="text-xs font-medium uppercase tracking-wide">{label}</p>
        {icon}
      </div>
      <p className={`mt-2 text-xl font-bold tabular-nums ${tone === "neg" ? "text-neg" : tone === "pos" ? "text-pos" : ""}`}>
        {value}
      </p>
    </Card>
  );
}

interface Txn {
  id: string; date: string; amount_minor: number; merchant_raw: string; category_name?: string; excluded: boolean;
}
interface Account { id: string; name: string; currency: string; balance_minor: number; archived?: boolean }

export function QuickAddModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t, i18n } = useTranslation();
  const [text, setText] = useState("");
  const [accountId, setAccountId] = useState("");
  const [parsed, setParsed] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const speech = useSpeechRecognition(i18n.language);

  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => http.get("/accounts").then((r) => r.data), enabled: open });

  async function parse() {
    const input = speech.transcript || text;
    if (!input.trim()) return;
    setBusy(true);
    try {
      const { data } = await http.post("/chat/expenses/parse", { text: input });
      setParsed(data);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!parsed?.amount_minor || !accountId) return;
    setBusy(true);
    try {
      await http.post("/transactions", {
        account_id: accountId,
        date: parsed.date || todayISO(),
        amount_minor: -Math.abs(parsed.amount_minor),
        currency: parsed.currency,
        merchant_raw: parsed.merchant,
      });
      setParsed(null);
      setText("");
      onClose();
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t("dash.quickAdd")}>
      <div className="space-y-3">
        <div className="flex gap-2">
          <Input
            value={speech.transcript || text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("dash.quickAddHint")}
          />
          {speech.supported && (
            <Button variant={speech.listening ? "danger" : "outline"} onClick={speech.listening ? speech.stop : speech.start}>
              <Mic size={16} />
            </Button>
          )}
        </div>
        <Select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">— account —</option>
          {(accounts.data ?? []).filter((a: Account) => !a.archived).map((a: Account) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </Select>
        {parsed && (
          <div className="rounded-xl border border-line p-3 text-sm">
            <p><b>{fmtMoney(parsed.amount_minor ?? 0, parsed.currency)}</b> · {parsed.merchant}</p>
            {parsed.items?.length > 1 && (
              <ul className="mt-1 text-xs text-muted">{parsed.items.map((it: any, i: number) => <li key={i}>• {it.label}: {fmtMoney(it.amount_minor, parsed.currency)}</li>)}</ul>
            )}
          </div>
        )}
        <div className="flex justify-end gap-2">
          {!parsed ? (
            <Button onClick={parse} disabled={busy || !(speech.transcript || text).trim()}>{busy ? "…" : "Parse"}</Button>
          ) : (
            <>
              <Button variant="ghost" onClick={() => { setParsed(null); speech.reset(); }}>{t("common.cancel")}</Button>
              <Button onClick={save} disabled={busy || !accountId}>{t("common.save")}</Button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
