import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid,
} from "recharts";
import { TrendingUp, TrendingDown, Wallet, Sparkles, Mic, AlertTriangle, CheckCircle2 } from "lucide-react";
import { http } from "@/lib/api";
import {
  Card, SectionTitle, Button, Input, Badge, Modal, Select, PageHeader, StatTile, PageSkeleton,
  ErrorState, ChartFrame, Field, IconButton,
} from "@/components/ui";
import { fmtMoney, todayISO } from "@/lib/utils";
import { useSpeechRecognition } from "@/lib/hooks";
import { useChartColors } from "@/lib/theme";
import { useCoachContext } from "@/lib/coachTabs";

export default function DashboardPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const colors = useChartColors();
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

  useCoachContext(stats ? {
    currency,
    net_worth: stats.netWorth / 100,
    spent_last_30d: stats.spend30 / 100,
    income_last_30d: stats.income30 / 100,
    savings_rate_pct: +stats.savingsRate.toFixed(1),
    top_categories: stats.topCats.map((c) => ({ name: c.name, spent: c.value / 100 })),
    open_alerts: (alerts.data ?? []).length,
  } : null);

  if (txns.isLoading || accounts.isLoading) return <PageSkeleton />;
  if (txns.isError || accounts.isError) {
    return <ErrorState onRetry={() => { void txns.refetch(); void accounts.refetch(); }} />;
  }

  const money = (minor: number) => fmtMoney(minor, currency, locale);
  const alertList = (alerts.data ?? []) as { id: string; title: string; body?: string | null; severity?: string }[];

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("nav.dashboard")}
        actions={
          <Button onClick={() => setQuickOpen(true)}>
            <Sparkles size={16} aria-hidden /> {t("dash.quickAdd")}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatTile label={t("dash.netWorth")} value={<span className="num">{money(stats?.netWorth ?? 0)}</span>} icon={<Wallet size={18} />} />
        <StatTile label={t("dash.thisMonth")} value={<span className="num">{money(-(stats?.spend30 ?? 0))}</span>} tone="neg" icon={<TrendingDown size={18} />} />
        <StatTile label={t("dash.income")} value={<span className="num">{money(stats?.income30 ?? 0)}</span>} tone="pos" icon={<TrendingUp size={18} />} />
        <StatTile label={t("dash.savingsRate")} value={<span className="num">{`${(stats?.savingsRate ?? 0).toFixed(1)}%`}</span>} icon={<Sparkles size={18} />} />
      </div>

      <div className="grid gap-4 sm:gap-6 lg:grid-cols-3">
        <Card as="section" className="lg:col-span-2">
          <SectionTitle right={<Badge tone="brand">{t("dash.forecast")}</Badge>}>{t("dash.cashflow")}</SectionTitle>
          <ChartFrame summary={t("dash.cashflowSummary", { count: stats?.series.length ?? 0 })}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stats?.series ?? []} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="net" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={colors.brand} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={colors.brand} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke={colors.grid} />
                <XAxis dataKey="month" tick={{ fontSize: 12, fill: colors.muted }} axisLine={false} tickLine={false} reversed={i18n.dir() === "rtl"} />
                <YAxis tick={{ fontSize: 12, fill: colors.muted }} axisLine={false} tickLine={false} width={48} orientation={i18n.dir() === "rtl" ? "right" : "left"} />
                <Tooltip
                  formatter={(v: number) => money(v * 100)}
                  contentStyle={{ background: colors.raised, border: `1px solid ${colors.grid}`, borderRadius: 8, color: colors.ink }}
                  labelStyle={{ color: colors.muted }}
                  cursor={{ stroke: colors.muted, strokeDasharray: "3 3" }}
                />
                <Area type="monotone" dataKey="net" name={t("dash.net")} stroke={colors.brand} strokeWidth={2} fill="url(#net)" activeDot={{ r: 4 }} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartFrame>
        </Card>

        <Card as="section">
          <SectionTitle>{t("dash.topCategories")}</SectionTitle>
          {(stats?.topCats ?? []).length === 0 ? (
            <p className="text-sm text-muted">{t("dash.noSpending")}</p>
          ) : (
            <div className="flex items-center gap-4">
              <div className="shrink-0" aria-hidden>
                <PieChart width={112} height={112}>
                  <Pie data={stats?.topCats ?? []} dataKey="value" innerRadius={34} outerRadius={54} stroke={colors.raised} strokeWidth={2} isAnimationActive={false}>
                    {(stats?.topCats ?? []).map((c, i) => (
                      <Cell key={c.name} fill={colors.series[i % colors.series.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </div>
              <ul className="min-w-0 flex-1 space-y-1.5 text-sm" aria-label={t("dash.topCategories")}>
                {(stats?.topCats ?? []).map((c, i) => (
                  <li key={c.name} className="flex items-center gap-2">
                    <span className="size-2.5 shrink-0 rounded-sm" style={{ background: colors.series[i % colors.series.length] }} aria-hidden />
                    <span className="min-w-0 flex-1 truncate text-ink">{c.name}</span>
                    <span className="num text-muted">{money(c.value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <h2 className="mb-3 mt-6 text-base font-semibold text-ink">{t("dash.alerts")}</h2>
          <ul className="space-y-2">
            {alertList.slice(0, 4).map((a) => (
              <li key={a.id} className="flex gap-2.5 rounded-lg bg-sunken px-3 py-2.5 text-sm">
                <AlertTriangle size={16} className={a.severity === "critical" ? "mt-0.5 shrink-0 text-neg" : "mt-0.5 shrink-0 text-warn"} aria-hidden />
                <div className="min-w-0">
                  <p className="font-medium text-ink">{a.title}</p>
                  {a.body && <p className="mt-0.5 line-clamp-1 text-muted">{a.body}</p>}
                </div>
              </li>
            ))}
            {alertList.length === 0 && (
              <li className="flex items-center gap-2 rounded-lg bg-pos/10 px-3 py-2.5 text-sm text-pos">
                <CheckCircle2 size={16} aria-hidden /> {t("dash.allClear")}
              </li>
            )}
          </ul>
        </Card>
      </div>

      <QuickAddModal open={quickOpen} onClose={() => setQuickOpen(false)} onDone={() => { void qc.invalidateQueries(); }} />
    </div>
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
      <div className="space-y-4">
        <Field label={t("dash.quickAddLabel")} hint={t("dash.quickAddHint")}>
          <div className="flex gap-2">
            <Input
              value={speech.transcript || text}
              onChange={(e) => setText(e.target.value)}
              autoFocus
            />
            {speech.supported && (
              <IconButton
                variant={speech.listening ? "danger" : "secondary"}
                label={t("coach.voice")}
                icon={<Mic size={16} />}
                onClick={speech.listening ? speech.stop : speech.start}
                aria-pressed={speech.listening}
              />
            )}
          </div>
        </Field>
        <Field label={t("common.account")}>
          <Select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t("dash.chooseAccount")}</option>
            {(accounts.data ?? []).filter((a: Account) => !a.archived).map((a: Account) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
        </Field>
        {parsed && (
          <div className="rounded-lg bg-sunken p-3 text-sm">
            <p className="text-ink">
              <b className="num">{fmtMoney(parsed.amount_minor ?? 0, parsed.currency, i18n.language)}</b>
              <span className="text-muted"> {t("dash.at")} </span>
              {parsed.merchant}
            </p>
            {parsed.items?.length > 1 && (
              <ul className="mt-1.5 space-y-0.5 text-muted">
                {parsed.items.map((it: any, i: number) => (
                  <li key={i} className="flex justify-between gap-3">
                    <span>{it.label}</span>
                    <span className="num">{fmtMoney(it.amount_minor, parsed.currency, i18n.language)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-1">
          {!parsed ? (
            <Button onClick={parse} disabled={busy || !(speech.transcript || text).trim()}>
              {busy ? t("common.loading") : t("dash.parse")}
            </Button>
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
