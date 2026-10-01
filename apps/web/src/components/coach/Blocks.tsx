import { useTranslation } from "react-i18next";
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Meter } from "@/components/ui";
import { useChartColors } from "@/lib/theme";
import { cn, fmtMoney } from "@/lib/utils";
import { useAuth } from "@/stores/auth";
import type { Block, BudgetBlock, ChartBlock, TxnBlock } from "@/stores/coach";

function chartTitleKey(title: string) {
  if (title.startsWith("spend_by_category")) return "coach.blocks.spendByCategory";
  if (title.startsWith("net_flow_forecast")) return "coach.blocks.forecast";
  return "coach.blocks.chart";
}

function MiniChart({ block }: { block: ChartBlock }) {
  const { t, i18n } = useTranslation();
  const colors = useChartColors();
  const currency = useAuth((s) => s.user?.base_currency) || "USD";
  const data = block.series.map((p) => ({ label: p.label, value: p.value / 100 }));
  const money = (v: number) => fmtMoney(v * 100, currency, i18n.language);
  const title = t(chartTitleKey(block.title));
  const summary = block.series.map((p) => `${p.label}: ${money(p.value / 100)}`).join(", ");
  const tooltip = (
    <Tooltip
      formatter={(v: number) => money(v)}
      contentStyle={{ background: colors.raised, border: `1px solid ${colors.grid}`, borderRadius: 8, color: colors.ink, fontSize: 12 }}
      labelStyle={{ color: colors.muted }}
      cursor={{ fill: colors.grid, opacity: 0.4 }}
    />
  );
  return (
    <figure className="m-0 rounded-lg border border-line bg-raised p-3">
      <figcaption className="mb-2 text-sm font-medium text-ink">{title}</figcaption>
      <div className="h-28" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          {block.kind === "line" ? (
            <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: colors.muted }} axisLine={false} tickLine={false} reversed={i18n.dir() === "rtl"} />
              {tooltip}
              <Line type="monotone" dataKey="value" stroke={colors.series[0]} strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          ) : (
            <BarChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: colors.muted }} axisLine={false} tickLine={false} interval={0} tickFormatter={(v: string) => v.slice(0, 8)} reversed={i18n.dir() === "rtl"} />
              {tooltip}
              <Bar dataKey="value" fill={colors.series[0]} radius={[4, 4, 0, 0]} maxBarSize={22} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      <p className="sr-only">{summary}</p>
    </figure>
  );
}

function TxnList({ block }: { block: TxnBlock }) {
  const { t, i18n } = useTranslation();
  return (
    <div className="rounded-lg border border-line bg-raised">
      <p className="border-b border-line px-3 py-2 text-sm font-medium text-ink">
        {t("coach.blocks.transactions", { count: block.items.length })}
      </p>
      <ul className="divide-y divide-line">
        {block.items.map((x) => (
          <li key={x.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
            <div className="min-w-0">
              <p className="truncate text-ink">{x.merchant}</p>
              <p className="num text-xs text-muted">{x.date}</p>
            </div>
            <span className={cn("num shrink-0 font-medium", x.amount_minor > 0 ? "text-pos" : "text-ink")}>
              {fmtMoney(x.amount_minor, x.currency, i18n.language)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function BudgetDelta({ block }: { block: BudgetBlock }) {
  const { t, i18n } = useTranslation();
  const money = (m: number) => fmtMoney(m, block.currency, i18n.language);
  return (
    <div className="space-y-3 rounded-lg border border-line bg-raised p-3">
      <p className="text-sm font-medium text-ink">{t("coach.blocks.budget", { name: block.budget, month: block.month })}</p>
      <ul className="space-y-2.5">
        {block.envelopes.map((e) => (
          <li key={e.name} className="space-y-1">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate text-ink">{e.name}</span>
              <span className={cn("num shrink-0", e.overspent ? "font-semibold text-neg" : "text-muted")}>
                {e.overspent
                  ? t("coach.blocks.over", { amount: money(Math.abs(e.remaining_minor)) })
                  : t("coach.blocks.left", { amount: money(e.remaining_minor) })}
              </span>
            </div>
            <Meter
              value={e.pct_used}
              tone={e.overspent ? "neg" : e.pct_used >= 80 ? "warn" : "brand"}
              label={t("budgets.meterLabel", { name: e.name, pct: e.pct_used })}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BlockView({ block }: { block: Block }) {
  if (block.type === "chart") return <MiniChart block={block} />;
  if (block.type === "transactions") return <TxnList block={block} />;
  if (block.type === "budget_delta") return <BudgetDelta block={block} />;
  return null;
}
