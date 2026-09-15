import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Link2,
  RefreshCw,
  Trash2,
  Globe2,
  Building2,
  CreditCard,
  CheckCircle2,
  ShieldCheck,
  Zap,
  Key,
  ExternalLink,
} from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Input,
  Modal,
  SectionTitle,
  Spinner,
} from "@/components/ui";

interface AU_Bank_Info {
  key: string;
  name: string;
  shortName: string;
  bgGradient: string;
  textTone: string;
  code: string;
}

const AU_BANKS: AU_Bank_Info[] = [
  {
    key: "cba",
    name: "Commonwealth Bank",
    shortName: "CommBank",
    bgGradient: "from-amber-500/15 to-amber-500/5",
    textTone: "text-amber-500",
    code: "CBA",
  },
  {
    key: "westpac",
    name: "Westpac Banking Corp",
    shortName: "Westpac",
    bgGradient: "from-red-500/15 to-red-500/5",
    textTone: "text-red-500",
    code: "WBC",
  },
  {
    key: "anz",
    name: "ANZ Bank",
    shortName: "ANZ",
    bgGradient: "from-blue-600/15 to-blue-600/5",
    textTone: "text-blue-500",
    code: "ANZ",
  },
  {
    key: "nab",
    name: "National Australia Bank",
    shortName: "NAB",
    bgGradient: "from-red-600/15 to-slate-800/10",
    textTone: "text-red-600",
    code: "NAB",
  },
  {
    key: "macquarie",
    name: "Macquarie Bank",
    shortName: "Macquarie",
    bgGradient: "from-slate-500/15 to-slate-500/5",
    textTone: "text-slate-400",
    code: "MQG",
  },
  {
    key: "suncorp",
    name: "Suncorp Bank",
    shortName: "Suncorp",
    bgGradient: "from-emerald-500/15 to-emerald-500/5",
    textTone: "text-emerald-500",
    code: "SUN",
  },
  {
    key: "bendigo",
    name: "Bendigo Bank",
    shortName: "Bendigo",
    bgGradient: "from-rose-700/15 to-rose-700/5",
    textTone: "text-rose-600",
    code: "BEN",
  },
  {
    key: "boq",
    name: "Bank of Queensland",
    shortName: "BOQ",
    bgGradient: "from-sky-500/15 to-sky-500/5",
    textTone: "text-sky-500",
    code: "BOQ",
  },
  {
    key: "ing_au",
    name: "ING Australia",
    shortName: "ING Direct",
    bgGradient: "from-orange-500/15 to-orange-500/5",
    textTone: "text-orange-500",
    code: "ING",
  },
  {
    key: "up",
    name: "UP Bank",
    shortName: "UP Banking",
    bgGradient: "from-orange-600/20 to-amber-500/10",
    textTone: "text-orange-500",
    code: "UP",
  },
];

type RegionTab = "ALL" | "AU" | "US" | "EU" | "STRIPE";

export default function ConnectionsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState<RegionTab>("ALL");
  const [stripeModalOpen, setStripeModalOpen] = useState(false);
  const [stripeApiKey, setStripeApiKey] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const providersQuery = useQuery({
    queryKey: ["providers"],
    queryFn: () => http.get("/connections/providers").then((r) => r.data),
  });

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: () => http.get("/connections").then((r) => r.data),
  });

  const startLinkMutation = useMutation({
    mutationFn: async ({ provider, institutionName }: { provider: string; institutionName?: string }) => {
      const res = await http.post("/connections/link/start", { provider });
      return { ...res.data, institutionName, provider };
    },
    onSuccess: (data) => {
      if (data.link_url) {
        window.open(data.link_url, "_blank");
        setStatusMessage(`Opened connection portal for ${data.institutionName || data.provider}.`);
      } else if (data.link_token) {
        setStatusMessage(`Link token initialized: ${data.link_token.slice(0, 16)}...`);
      } else {
        setStatusMessage(`Connected: ${JSON.stringify(data)}`);
      }
      void qc.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (e: any) => {
      setStatusMessage(e?.response?.data?.detail ?? "Provider unavailable. Mock banking flow active.");
    },
  });

  const stripeConnectMutation = useMutation({
    mutationFn: async (apiKey: string) => {
      const res = await http.post("/connections/stripe/connect", { api_key: apiKey });
      return res.data;
    },
    onSuccess: () => {
      setStripeModalOpen(false);
      setStripeApiKey("");
      setErrorMessage(null);
      setStatusMessage("✓ Stripe business account successfully connected and active!");
      void qc.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || "Failed to connect Stripe API key");
    },
  });

  const syncMutation = useMutation({
    mutationFn: (id: string) => http.post(`/connections/${id}/sync`).then((r) => r.data),
    onSuccess: (r) => {
      setStatusMessage(
        `✓ Synced: +${r.created_txns} new transactions (${(r.created_accounts ?? []).join(", ") || "up to date"})`,
      );
      void qc.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (err: any) => {
      setStatusMessage(`Sync error: ${err?.response?.data?.detail || "Failed to sync"}`);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: async (id: string) => {
      await http.delete(`/connections/${id}`);
    },
    onSuccess: () => {
      setStatusMessage("Connection disconnected.");
      void qc.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  function handleConnectStripe(e: React.FormEvent) {
    e.preventDefault();
    if (!stripeApiKey.trim()) return;
    stripeConnectMutation.mutate(stripeApiKey.trim());
  }

  const connections = connectionsQuery.data || [];
  const providers = providersQuery.data?.providers || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-ink">{t("connections.title")}</h1>
        <p className="text-sm text-muted">{t("connections.subtitle")}</p>
      </div>

      {/* Region Filter Tabs */}
      <div className="flex flex-wrap items-center gap-1.5 rounded-2xl bg-raised p-1.5 border border-line">
        {[
          { id: "ALL" as RegionTab, label: t("connections.allRegions") },
          { id: "AU" as RegionTab, label: t("connections.auRegion") },
          { id: "US" as RegionTab, label: t("connections.usRegion") },
          { id: "EU" as RegionTab, label: t("connections.euRegion") },
          { id: "STRIPE" as RegionTab, label: t("connections.businessRegion") },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-xl px-4 py-2 text-xs font-semibold transition ${
              activeTab === tab.id
                ? "bg-brand text-white shadow-md shadow-brand/20"
                : "text-muted hover:bg-surface hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Status banner */}
      {statusMessage && (
        <Card className="flex items-center justify-between border-brand/40 bg-brand/5 p-3.5 text-xs text-brand">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} />
            <span>{statusMessage}</span>
          </div>
          <button
            onClick={() => setStatusMessage(null)}
            className="text-xs text-muted hover:text-ink"
          >
            Dismiss
          </button>
        </Card>
      )}

      {/* 1. Australian Banks Grid (CDR / Basiq) */}
      {(activeTab === "ALL" || activeTab === "AU") && (
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <div>
              <h3 className="text-sm font-bold text-ink">{t("connections.auBanksTitle")}</h3>
              <p className="text-xs text-muted">{t("connections.auBanksSubtitle")}</p>
            </div>
            <Badge tone="brand">10 Major Banks Supported</Badge>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {AU_BANKS.map((bank) => {
              const isConnected = connections.some(
                (c: any) =>
                  c.status === "active" &&
                  (c.provider === bank.key || c.institution_name?.includes(bank.shortName)),
              );

              return (
                <div
                  key={bank.key}
                  className={`flex flex-col justify-between rounded-xl border border-line bg-gradient-to-b ${bank.bgGradient} p-4 transition hover:border-brand/40`}
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className={`text-xs font-extrabold tracking-wider ${bank.textTone}`}>
                        {bank.code}
                      </span>
                      {isConnected ? (
                        <Badge tone="pos">{t("connections.connected")}</Badge>
                      ) : (
                        <span className="text-[10px] text-muted font-mono">Open Banking</span>
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-ink leading-snug">{bank.name}</p>
                      <p className="text-[11px] text-muted">{bank.shortName}</p>
                    </div>
                  </div>

                  <div className="pt-4">
                    <Button
                      size="sm"
                      variant={isConnected ? "outline" : "primary"}
                      onClick={() =>
                        startLinkMutation.mutate({
                          provider: bank.key,
                          institutionName: bank.name,
                        })
                      }
                      disabled={startLinkMutation.isPending}
                      className="w-full text-xs"
                    >
                      {isConnected ? "Re-link" : "Connect"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* 2. Stripe Business Payments Integration */}
      {(activeTab === "ALL" || activeTab === "STRIPE") && (
        <Card className="border-brand/30 bg-gradient-to-r from-brand/10 via-surface to-surface p-6">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="flex items-start gap-4">
              <div className="grid size-12 place-items-center rounded-2xl bg-brand text-white shadow-lg shadow-brand/25">
                <CreditCard size={24} />
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-ink">{t("connections.stripeTitle")}</h3>
                  <Badge tone="brand">Business & Accounting</Badge>
                </div>
                <p className="text-xs text-muted max-w-xl">
                  {t("connections.stripeSubtitle")}. {t("connections.stripeHelp")}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <Button
                onClick={() => {
                  setStripeApiKey("");
                  setErrorMessage(null);
                  setStripeModalOpen(true);
                }}
                className="flex items-center gap-2 shadow-md"
              >
                <Key size={15} /> {t("connections.connectStripe")}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* 3. Global & Regional Providers (US / EU) */}
      {(activeTab === "ALL" || activeTab === "US" || activeTab === "EU") && (
        <Card>
          <SectionTitle>Global Open Banking Providers</SectionTitle>
          <div className="grid gap-3 md:grid-cols-3">
            {providers
              .filter((p: any) => {
                if (activeTab === "US") return p.region === "US";
                if (activeTab === "EU") return p.region === "EU/UK" || p.region === "EU";
                return p.key === "plaid" || p.key === "gocardless" || p.key === "basiq" || p.key === "mock";
              })
              .map((p: any) => (
                <div
                  key={p.key}
                  className="flex items-center justify-between rounded-xl border border-line bg-surface p-4"
                >
                  <div className="flex items-center gap-3">
                    <Globe2 size={20} className="text-brand" />
                    <div>
                      <p className="text-sm font-semibold capitalize text-ink">{p.name || p.key}</p>
                      <p className="text-xs text-muted">{p.region}</p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant={p.configured ? "primary" : "outline"}
                    disabled={!p.configured || startLinkMutation.isPending}
                    onClick={() => startLinkMutation.mutate({ provider: p.key })}
                  >
                    {p.configured ? "Connect" : "Sandbox"}
                  </Button>
                </div>
              ))}
          </div>
        </Card>
      )}

      {/* 4. Active Connections List */}
      <Card>
        <SectionTitle>{t("connections.yourConnections")}</SectionTitle>

        {connectionsQuery.isLoading ? (
          <Spinner />
        ) : connections.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted">
            {t("connections.noConnections")}
          </div>
        ) : (
          <div className="space-y-3 pt-1">
            {connections.map((c: any) => (
              <div
                key={c.id}
                className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex items-center gap-3">
                  <div className="grid size-10 place-items-center rounded-xl bg-brand/10 text-brand">
                    {c.provider === "stripe" ? <CreditCard size={18} /> : <Building2 size={18} />}
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-ink">
                      {c.institution_name || c.provider.toUpperCase()}
                    </p>
                    <p className="text-xs text-muted capitalize">
                      {c.provider} · {c.region || "Global"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center">
                  <Badge tone={c.status === "active" ? "pos" : "neutral"}>
                    {c.status}
                  </Badge>

                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => syncMutation.mutate(c.id)}
                    disabled={syncMutation.isPending}
                    className="flex items-center gap-1.5"
                  >
                    <RefreshCw
                      size={13}
                      className={syncMutation.isPending ? "animate-spin" : ""}
                    />
                    {t("connections.syncNow")}
                  </Button>

                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => revokeMutation.mutate(c.id)}
                    disabled={revokeMutation.isPending}
                    className="text-neg hover:bg-neg/10 px-2"
                    title={t("connections.disconnect")}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Stripe Connect Modal */}
      <Modal
        open={stripeModalOpen}
        onClose={() => setStripeModalOpen(false)}
        title={t("connections.connectStripe")}
      >
        <form onSubmit={handleConnectStripe} className="space-y-4">
          {errorMessage && (
            <div className="rounded-xl bg-neg/10 p-3 text-xs text-neg">
              {errorMessage}
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("connections.stripeApiKey")}
            </label>
            <Input
              type="password"
              value={stripeApiKey}
              onChange={(e) => setStripeApiKey(e.target.value)}
              placeholder={t("connections.stripeApiKeyPlaceholder")}
              required
              autoFocus
            />
            <p className="mt-1.5 text-[11px] text-muted">
              Enter your restricted or secret key from the Stripe Dashboard (e.g. <code>sk_test_...</code>, <code>sk_live_...</code>, <code>rk_live_...</code>).
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setStripeModalOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={stripeConnectMutation.isPending}>
              {stripeConnectMutation.isPending ? t("common.loading") : t("connections.connectStripe")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
