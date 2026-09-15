import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Cpu,
  ShieldCheck,
  Activity,
  Zap,
  Clock,
  Layers,
  ChevronLeft,
  ChevronRight,
  Filter,
  Settings as SettingsIcon,
  CheckCircle2,
} from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  SectionTitle,
  Select,
  Spinner,
} from "@/components/ui";

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

export default function AiEvalPage() {
  const { t } = useTranslation();

  const isEnabled = localStorage.getItem("fb.ai_eval_enabled") === "true";
  const [page, setPage] = useState<number>(1);
  const [limit, setLimit] = useState<number>(20);
  const [selectedRoute, setSelectedRoute] = useState<string>("all");

  const { data, isLoading, refetch } = useQuery<AiEvalHistoryResponse>({
    queryKey: ["ai-eval-history", page, limit],
    queryFn: async () => {
      const res = await http.get(`/ai/eval/history?page=${page}&limit=${limit}`);
      return res.data;
    },
    enabled: isEnabled,
  });

  if (!isEnabled) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">{t("aiEval.title")}</h1>
          <p className="text-sm text-muted">{t("aiEval.subtitle")}</p>
        </div>

        <Card className="flex flex-col items-center justify-center p-12 text-center">
          <div className="mb-4 grid size-16 place-items-center rounded-2xl bg-brand/10 text-brand">
            <Cpu size={32} />
          </div>
          <h2 className="text-lg font-semibold text-ink">
            {t("aiEval.disabledNotice")}
          </h2>
          <p className="mt-1 max-w-md text-sm text-muted">
            {t("aiEval.enablePrompt")}
          </p>
          <Link to="/settings" className="mt-6">
            <Button className="flex items-center gap-2">
              <SettingsIcon size={16} /> {t("aiEval.openSettings")}
            </Button>
          </Link>
        </Card>
      </div>
    );
  }

  const items = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / limit) || 1;

  // Filter items by route if selected
  const filteredItems =
    selectedRoute === "all"
      ? items
      : items.filter((log) => log.route_chosen.toLowerCase() === selectedRoute.toLowerCase());

  // Aggregate stats
  const totalTokens = items.reduce((sum, item) => sum + (item.tokens_in + item.tokens_out), 0);
  const avgLatency =
    items.length > 0
      ? Math.round(items.reduce((sum, item) => sum + item.latency_ms, 0) / items.length)
      : 0;
  const totalPii = items.reduce((sum, item) => sum + item.pii_fields_masked, 0);

  const routeTone = (route: string): "brand" | "pos" | "warn" | "neutral" => {
    switch (route.toLowerCase()) {
      case "tax":
        return "brand";
      case "budget":
        return "pos";
      case "fraud":
        return "warn";
      case "goals":
        return "pos";
      default:
        return "neutral";
    }
  };

  const latencyTone = (ms: number): "pos" | "warn" | "neg" => {
    if (ms < 500) return "pos";
    if (ms < 1500) return "warn";
    return "neg";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-ink">{t("aiEval.title")}</h1>
            <Badge tone="brand">Real-time Telemetry</Badge>
          </div>
          <p className="text-sm text-muted">{t("aiEval.subtitle")}</p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={() => void refetch()}
          className="flex items-center gap-1.5"
        >
          <Activity size={14} /> Refresh Logs
        </Button>
      </div>

      {/* Overview Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("aiEval.totalQueries")}
            </span>
            <div className="grid size-8 place-items-center rounded-lg bg-brand/10 text-brand">
              <Zap size={16} />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-ink">{total}</p>
          <p className="mt-1 text-xs text-muted">Across all sessions</p>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("aiEval.avgLatency")}
            </span>
            <div className="grid size-8 place-items-center rounded-lg bg-pos/10 text-pos">
              <Clock size={16} />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-ink">{avgLatency} ms</p>
          <p className="mt-1 text-xs text-muted">Supervisor + Model execution</p>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("aiEval.totalTokens")}
            </span>
            <div className="grid size-8 place-items-center rounded-lg bg-amber-500/10 text-amber-500">
              <Layers size={16} />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-ink">
            {totalTokens.toLocaleString()}
          </p>
          <p className="mt-1 text-xs text-muted">Prompt + Completion</p>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("aiEval.piiRedacted")}
            </span>
            <div className="grid size-8 place-items-center rounded-lg bg-pos/10 text-pos">
              <ShieldCheck size={16} />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-pos">{totalPii}</p>
          <p className="mt-1 text-xs text-muted">Account & card redactions</p>
        </Card>
      </div>

      {/* Logs Table */}
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <SectionTitle>{t("aiEval.logsTable")}</SectionTitle>

          {/* Route Filter */}
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-muted" />
            <span className="text-xs text-muted font-medium">{t("aiEval.filterRoute")}:</span>
            <Select
              value={selectedRoute}
              onChange={(e) => setSelectedRoute(e.target.value)}
              className="h-8 py-0 text-xs w-32"
            >
              <option value="all">{t("aiEval.allRoutes")}</option>
              <option value="coach">Coach</option>
              <option value="budget">Budget</option>
              <option value="tax">Tax</option>
              <option value="fraud">Fraud</option>
              <option value="goals">Goals</option>
            </Select>
          </div>
        </div>

        {isLoading ? (
          <Spinner />
        ) : filteredItems.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted">
            {t("aiEval.noLogs")}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-line text-muted">
                <tr>
                  <th className="py-2.5 px-3">{t("aiEval.timestamp")}</th>
                  <th className="py-2.5 px-3">{t("aiEval.query")}</th>
                  <th className="py-2.5 px-3">{t("aiEval.route")}</th>
                  <th className="py-2.5 px-3">{t("aiEval.model")}</th>
                  <th className="py-2.5 px-3 text-right">{t("aiEval.latency")}</th>
                  <th className="py-2.5 px-3 text-right">{t("aiEval.tokens")}</th>
                  <th className="py-2.5 px-3 text-center">{t("aiEval.confidence")}</th>
                  <th className="py-2.5 px-3 text-center">{t("aiEval.piiCount")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {filteredItems.map((log) => {
                  const dateStr = new Date(log.created_at).toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  });

                  return (
                    <tr key={log.id} className="hover:bg-raised/40 transition">
                      <td className="py-3 px-3 whitespace-nowrap text-muted font-mono text-[11px]">
                        {dateStr}
                      </td>
                      <td className="py-3 px-3 max-w-xs truncate font-medium text-ink">
                        {log.query_summary || "Financial query"}
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        <Badge tone={routeTone(log.route_chosen)}>
                          {log.route_chosen}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span className="font-semibold text-ink capitalize">{log.provider_used}</span>
                        <span className="ml-1 text-[11px] text-muted">({log.model_name})</span>
                      </td>
                      <td className="py-3 px-3 text-right whitespace-nowrap">
                        <Badge tone={latencyTone(log.latency_ms)}>
                          {log.latency_ms} ms
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-right whitespace-nowrap text-muted">
                        <span className="font-medium text-ink">{log.tokens_in}</span> in /{" "}
                        <span className="font-medium text-ink">{log.tokens_out}</span> out
                      </td>
                      <td className="py-3 px-3 text-center whitespace-nowrap font-medium text-ink">
                        {Math.round(log.confidence_score * 100)}%
                      </td>
                      <td className="py-3 px-3 text-center whitespace-nowrap">
                        {log.pii_fields_masked > 0 ? (
                          <span className="inline-flex items-center gap-1 font-semibold text-pos">
                            <ShieldCheck size={13} /> {log.pii_fields_masked}
                          </span>
                        ) : (
                          <span className="text-muted">0</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {total > limit && (
          <div className="mt-4 flex items-center justify-between border-t border-line/60 pt-3 text-xs text-muted">
            <span>
              Showing {(page - 1) * limit + 1} - {Math.min(page * limit, total)} of {total}
            </span>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="size-8 p-0"
              >
                <ChevronLeft size={14} />
              </Button>
              <span className="font-medium text-ink">
                Page {page} of {totalPages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="size-8 p-0"
              >
                <ChevronRight size={14} />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
