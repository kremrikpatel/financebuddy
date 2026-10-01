import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Cpu, ShieldCheck, Activity, Zap, Clock, Layers, ChevronLeft, ChevronRight, Settings as SettingsIcon } from "lucide-react";
import { http } from "@/lib/api";
import { useCoachContext } from "@/lib/coachTabs";
import { Badge, Button, Card, SectionTitle, Select, Spinner, PageHeader, StatTile, Table, EmptyState, IconButton } from "@/components/ui";

interface AiEvalLog {
  id: string;
  user_id: string;
  thread_id: string | null;
  message_id: string | null;
  provider_used: string;
  model_name: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  route_chosen: string;
  confidence_score: number;
  pii_fields_masked: number;
  query_summary: string | null;
  created_at: string;
}

interface AiEvalHistoryResponse {
  items: AiEvalLog[];
  total: number;
  page: number;
  limit: number;
}

const ROUTES = ["coach", "budget", "tax", "fraud", "goals"] as const;

const routeTone = (route: string): "brand" | "pos" | "warn" | "neutral" => {
  switch (route.toLowerCase()) {
    case "tax":
      return "brand";
    case "budget":
    case "goals":
      return "pos";
    case "fraud":
      return "warn";
    default:
      return "neutral";
  }
};

const latencyTone = (ms: number): "pos" | "warn" | "neg" => (ms < 500 ? "pos" : ms < 1500 ? "warn" : "neg");

export default function AiEvalPage() {
  const { t, i18n } = useTranslation();

  const isEnabled = localStorage.getItem("fb.ai_eval_enabled") === "true";
  const [page, setPage] = useState<number>(1);
  const [limit] = useState<number>(20);
  const [selectedRoute, setSelectedRoute] = useState<string>("all");

  const { data, isLoading, refetch } = useQuery<AiEvalHistoryResponse>({
    queryKey: ["ai-eval-history", page, limit],
    queryFn: async () => (await http.get(`/ai/eval/history?page=${page}&limit=${limit}`)).data,
    enabled: isEnabled,
  });

  useCoachContext({ diagnostics_enabled: isEnabled, page, route_filter: selectedRoute, total_logged: data?.total ?? null });

  if (!isEnabled) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("aiEval.title")} subtitle={t("aiEval.subtitle")} />
        <Card>
          <EmptyState
            icon={<Cpu size={22} />}
            title={t("aiEval.disabledNotice")}
            body={t("aiEval.enablePrompt")}
            action={
              <Link to="/settings" className="btn-primary">
                <SettingsIcon size={16} aria-hidden /> {t("aiEval.openSettings")}
              </Link>
            }
          />
        </Card>
      </div>
    );
  }

  const items = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / limit) || 1;
  const filteredItems =
    selectedRoute === "all" ? items : items.filter((log) => log.route_chosen.toLowerCase() === selectedRoute.toLowerCase());

  const totalTokens = items.reduce((sum, item) => sum + (item.tokens_in + item.tokens_out), 0);
  const avgLatency = items.length > 0 ? Math.round(items.reduce((sum, item) => sum + item.latency_ms, 0) / items.length) : 0;
  const totalPii = items.reduce((sum, item) => sum + item.pii_fields_masked, 0);
  const rtl = i18n.dir() === "rtl";
  const nf = new Intl.NumberFormat(i18n.language);

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("aiEval.title")}
        subtitle={t("aiEval.subtitle")}
        actions={
          <Button variant="secondary" size="sm" onClick={() => void refetch()}>
            <Activity size={14} aria-hidden /> {t("aiEval.refresh")}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatTile label={t("aiEval.totalQueries")} icon={<Zap size={18} />} value={<span className="num">{nf.format(total)}</span>} hint={t("aiEval.acrossSessions")} />
        <StatTile label={t("aiEval.avgLatency")} icon={<Clock size={18} />} value={<span className="num">{t("aiEval.ms", { ms: nf.format(avgLatency) })}</span>} hint={t("aiEval.supervisorModel")} />
        <StatTile label={t("aiEval.totalTokens")} icon={<Layers size={18} />} value={<span className="num">{nf.format(totalTokens)}</span>} hint={t("aiEval.promptCompletion")} />
        <StatTile label={t("aiEval.piiRedacted")} tone="pos" icon={<ShieldCheck size={18} />} value={<span className="num">{nf.format(totalPii)}</span>} hint={t("aiEval.redactions")} />
      </div>

      <Card as="section">
        <SectionTitle
          right={
            <label className="flex items-center gap-2 text-sm text-muted">
              {t("aiEval.filterRoute")}
              <Select value={selectedRoute} onChange={(e) => setSelectedRoute(e.target.value)} className="h-9 w-36 py-0">
                <option value="all">{t("aiEval.allRoutes")}</option>
                {ROUTES.map((r) => (
                  <option key={r} value={r}>{t(`coach.modes.${r}`)}</option>
                ))}
              </Select>
            </label>
          }
        >
          {t("aiEval.logsTable")}
        </SectionTitle>

        {isLoading ? (
          <Spinner />
        ) : filteredItems.length === 0 ? (
          <EmptyState title={t("aiEval.noLogs")} />
        ) : (
          <Table label={t("aiEval.logsTable")}>
            <thead>
              <tr>
                <th>{t("aiEval.timestamp")}</th>
                <th>{t("aiEval.query")}</th>
                <th>{t("aiEval.route")}</th>
                <th className="hidden md:table-cell">{t("aiEval.model")}</th>
                <th className="!text-end">{t("aiEval.latency")}</th>
                <th className="hidden !text-end lg:table-cell">{t("aiEval.tokens")}</th>
                <th className="hidden !text-center lg:table-cell">{t("aiEval.confidence")}</th>
                <th className="!text-center">{t("aiEval.piiCount")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((log) => (
                <tr key={log.id}>
                  <td className="num whitespace-nowrap text-muted">
                    {new Date(log.created_at).toLocaleString(i18n.language, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </td>
                  <td className="max-w-xs"><span className="line-clamp-1 font-medium text-ink">{log.query_summary || t("aiEval.defaultQuery")}</span></td>
                  <td className="whitespace-nowrap"><Badge tone={routeTone(log.route_chosen)}>{t(`coach.modes.${log.route_chosen}`, log.route_chosen)}</Badge></td>
                  <td className="hidden whitespace-nowrap md:table-cell">
                    <span className="font-medium capitalize text-ink">{log.provider_used}</span>
                    <span className="ms-1 text-muted">({log.model_name})</span>
                  </td>
                  <td className="whitespace-nowrap text-end"><Badge tone={latencyTone(log.latency_ms)}>{t("aiEval.ms", { ms: log.latency_ms })}</Badge></td>
                  <td className="num hidden whitespace-nowrap text-end text-muted lg:table-cell">
                    {t("aiEval.tokensInOut", { in: log.tokens_in, out: log.tokens_out })}
                  </td>
                  <td className="num hidden text-center text-ink lg:table-cell">{Math.round(log.confidence_score * 100)}%</td>
                  <td className="text-center">
                    {log.pii_fields_masked > 0 ? (
                      <span className="inline-flex items-center gap-1 font-semibold text-pos">
                        <ShieldCheck size={14} aria-hidden /> {log.pii_fields_masked}
                      </span>
                    ) : (
                      <span className="text-muted">0</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}

        {total > limit && (
          <nav aria-label={t("aiEval.pagination")} className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 text-sm text-muted">
            <span>{t("aiEval.showing", { from: (page - 1) * limit + 1, to: Math.min(page * limit, total), total })}</span>
            <div className="flex items-center gap-2">
              <IconButton
                variant="secondary"
                label={t("aiEval.prev")}
                icon={rtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              />
              <span className="font-medium text-ink">{t("aiEval.pageOf", { page, total: totalPages })}</span>
              <IconButton
                variant="secondary"
                label={t("aiEval.next")}
                icon={rtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              />
            </div>
          </nav>
        )}
      </Card>
    </div>
  );
}
