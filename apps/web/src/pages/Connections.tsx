import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { RefreshCw, Trash2, Globe2, Building2, CreditCard, Key } from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, SectionTitle, Spinner, PageHeader, Segmented, Notice, Field, IconButton, EmptyState,
} from "@/components/ui";
import { useCoachContext } from "@/lib/coachTabs";

interface AuBank {
  key: string;
  name: string;
  shortName: string;
  code: string;
}

const AU_BANKS: AuBank[] = [
  { key: "cba", name: "Commonwealth Bank", shortName: "CommBank", code: "CBA" },
  { key: "westpac", name: "Westpac Banking Corp", shortName: "Westpac", code: "WBC" },
  { key: "anz", name: "ANZ Bank", shortName: "ANZ", code: "ANZ" },
  { key: "nab", name: "National Australia Bank", shortName: "NAB", code: "NAB" },
  { key: "macquarie", name: "Macquarie Bank", shortName: "Macquarie", code: "MQG" },
  { key: "suncorp", name: "Suncorp Bank", shortName: "Suncorp", code: "SUN" },
  { key: "bendigo", name: "Bendigo Bank", shortName: "Bendigo", code: "BEN" },
  { key: "boq", name: "Bank of Queensland", shortName: "BOQ", code: "BOQ" },
  { key: "ing_au", name: "ING Australia", shortName: "ING Direct", code: "ING" },
  { key: "up", name: "UP Bank", shortName: "UP Banking", code: "UP" },
];

type RegionTab = "ALL" | "AU" | "US" | "EU" | "STRIPE";

export default function ConnectionsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [activeTab, setActiveTab] = useState<RegionTab>("ALL");
  const [stripeModalOpen, setStripeModalOpen] = useState(false);
  const [stripeApiKey, setStripeApiKey] = useState("");
  const [statusMessage, setStatusMessage] = useState<{ tone: "pos" | "neg" | "brand"; text: string } | null>(null);
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
        window.open(data.link_url, "_blank", "noopener,noreferrer");
        setStatusMessage({ tone: "brand", text: t("connections.portalOpened", { name: data.institutionName || data.provider }) });
      } else if (data.link_token) {
        setStatusMessage({ tone: "brand", text: t("connections.linkTokenReady", { token: `${data.link_token.slice(0, 16)}...` }) });
      } else {
        setStatusMessage({ tone: "pos", text: t("connections.connectedGeneric", { name: data.institutionName || data.provider }) });
      }
      void qc.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (e: any) => {
      setStatusMessage({ tone: "neg", text: e?.response?.data?.detail ?? t("connections.providerUnavailable") });
    },
  });

  const stripeConnectMutation = useMutation({
    mutationFn: async (apiKey: string) => (await http.post("/connections/stripe/connect", { api_key: apiKey })).data,
    onSuccess: () => {
      setStripeModalOpen(false);
      setStripeApiKey("");
      setErrorMessage(null);
      setStatusMessage({ tone: "pos", text: t("connections.stripeConnected") });
      void qc.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || t("connections.stripeFailed"));
    },
  });

  const syncMutation = useMutation({
    mutationFn: (id: string) => http.post(`/connections/${id}/sync`).then((r) => r.data),
    onSuccess: (r) => {
      const accounts = (r.created_accounts ?? []).join(", ");
      setStatusMessage({
        tone: "pos",
        text: accounts
          ? t("connections.syncedWithAccounts", { count: r.created_txns, accounts })
          : t("connections.synced", { count: r.created_txns }),
      });
      void qc.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (err: any) => {
      setStatusMessage({ tone: "neg", text: t("connections.syncError", { detail: err?.response?.data?.detail || t("common.errorBody") }) });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: async (id: string) => {
      await http.delete(`/connections/${id}`);
    },
    onSuccess: () => {
      setStatusMessage({ tone: "brand", text: t("connections.disconnected") });
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

  useCoachContext({
    region_filter: activeTab,
    connections: (connections as any[]).slice(0, 12).map((c) => ({ provider: c.provider, region: c.region ?? null, status: c.status })),
    configured_providers: (providers as any[]).filter((p) => p.configured).map((p) => p.key),
  });

  return (
    <div className="space-y-6">
      <PageHeader title={t("connections.title")} subtitle={t("connections.subtitle")} />

      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <Segmented
          label={t("connections.regionFilter")}
          value={activeTab}
          onChange={setActiveTab}
          className="flex-nowrap"
          options={[
            { value: "ALL" as RegionTab, label: t("connections.allRegions") },
            { value: "AU" as RegionTab, label: t("connections.auRegion") },
            { value: "US" as RegionTab, label: t("connections.usRegion") },
            { value: "EU" as RegionTab, label: t("connections.euRegion") },
            { value: "STRIPE" as RegionTab, label: t("connections.businessRegion") },
          ]}
        />
      </div>

      {statusMessage && (
        <Notice tone={statusMessage.tone} onDismiss={() => setStatusMessage(null)}>
          {statusMessage.text}
        </Notice>
      )}

      {(activeTab === "ALL" || activeTab === "AU") && (
        <Card as="section">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="font-semibold text-ink">{t("connections.auBanksTitle")}</h2>
              <p className="text-sm text-muted">{t("connections.auBanksSubtitle")}</p>
            </div>
            <Badge tone="brand">{t("connections.banksSupported", { count: AU_BANKS.length })}</Badge>
          </div>

          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {AU_BANKS.map((bank) => {
              const isConnected = connections.some(
                (c: any) =>
                  c.status === "active" &&
                  (c.provider === bank.key || c.institution_name?.includes(bank.shortName)),
              );
              return (
                <li key={bank.key} className="flex flex-col justify-between gap-4 rounded-lg border border-line p-4 transition-colors hover:border-field">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="grid h-8 min-w-8 place-items-center rounded-md bg-sunken px-1.5 text-xs font-bold text-ink" aria-hidden>
                        {bank.code}
                      </span>
                      {isConnected && <Badge tone="pos">{t("connections.connected")}</Badge>}
                    </div>
                    <div>
                      <p className="font-medium leading-snug text-ink">{bank.name}</p>
                      <p className="text-sm text-muted">{bank.shortName}</p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant={isConnected ? "secondary" : "primary"}
                    onClick={() => startLinkMutation.mutate({ provider: bank.key, institutionName: bank.name })}
                    disabled={startLinkMutation.isPending}
                    className="w-full"
                    aria-label={t(isConnected ? "connections.relinkNamed" : "connections.connectNamed", { name: bank.name })}
                  >
                    {isConnected ? t("connections.relink") : t("connections.connect")}
                  </Button>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {(activeTab === "ALL" || activeTab === "STRIPE") && (
        <Card as="section" className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-4">
            <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand/10 text-brand" aria-hidden>
              <CreditCard size={20} />
            </div>
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-semibold text-ink">{t("connections.stripeTitle")}</h2>
                <Badge tone="brand">{t("connections.businessBadge")}</Badge>
              </div>
              <p className="max-w-xl text-sm text-muted">
                {t("connections.stripeSubtitle")}. {t("connections.stripeHelp")}
              </p>
            </div>
          </div>
          <Button
            onClick={() => {
              setStripeApiKey("");
              setErrorMessage(null);
              setStripeModalOpen(true);
            }}
          >
            <Key size={16} aria-hidden /> {t("connections.connectStripe")}
          </Button>
        </Card>
      )}

      {(activeTab === "ALL" || activeTab === "US" || activeTab === "EU") && (
        <Card as="section">
          <SectionTitle>{t("connections.globalProviders")}</SectionTitle>
          <ul className="grid gap-3 md:grid-cols-3">
            {providers
              .filter((p: any) => {
                if (activeTab === "US") return p.region === "US";
                if (activeTab === "EU") return p.region === "EU/UK" || p.region === "EU";
                return p.key === "plaid" || p.key === "gocardless" || p.key === "basiq" || p.key === "mock";
              })
              .map((p: any) => (
                <li key={p.key} className="flex items-center justify-between gap-3 rounded-lg border border-line p-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <Globe2 size={20} className="shrink-0 text-muted" aria-hidden />
                    <div className="min-w-0">
                      <p className="truncate font-medium capitalize text-ink">{p.name || p.key}</p>
                      <p className="text-sm text-muted">{p.region}</p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant={p.configured ? "primary" : "secondary"}
                    disabled={!p.configured || startLinkMutation.isPending}
                    onClick={() => startLinkMutation.mutate({ provider: p.key })}
                  >
                    {p.configured ? t("connections.connect") : t("connections.sandbox")}
                  </Button>
                </li>
              ))}
          </ul>
        </Card>
      )}

      <Card as="section">
        <SectionTitle>{t("connections.yourConnections")}</SectionTitle>
        {connectionsQuery.isLoading ? (
          <Spinner />
        ) : connections.length === 0 ? (
          <EmptyState icon={<Building2 size={22} />} title={t("connections.noConnections")} />
        ) : (
          <ul className="divide-y divide-line">
            {connections.map((c: any) => (
              <li key={c.id} className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-sunken text-muted" aria-hidden>
                    {c.provider === "stripe" ? <CreditCard size={18} /> : <Building2 size={18} />}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{c.institution_name || c.provider.toUpperCase()}</p>
                    <p className="text-sm capitalize text-muted">
                      {c.provider} · {c.region || t("connections.global")}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 self-end sm:self-center">
                  <Badge tone={c.status === "active" ? "pos" : "neutral"}>{c.status}</Badge>
                  <Button size="sm" variant="secondary" onClick={() => syncMutation.mutate(c.id)} disabled={syncMutation.isPending}>
                    <RefreshCw size={14} className={syncMutation.isPending ? "animate-spin" : ""} aria-hidden />
                    {syncMutation.isPending ? t("connections.syncing") : t("connections.syncNow")}
                  </Button>
                  <IconButton
                    label={t("connections.disconnectNamed", { name: c.institution_name || c.provider })}
                    icon={<Trash2 size={16} />}
                    onClick={() => revokeMutation.mutate(c.id)}
                    disabled={revokeMutation.isPending}
                    className="text-neg hover:bg-neg/10 hover:text-neg"
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal open={stripeModalOpen} onClose={() => setStripeModalOpen(false)} title={t("connections.connectStripe")}>
        <form onSubmit={handleConnectStripe} className="space-y-4">
          {errorMessage && <Notice tone="neg">{errorMessage}</Notice>}
          <Field label={t("connections.stripeApiKey")} hint={t("connections.stripeKeyHint")}>
            <Input
              type="password"
              value={stripeApiKey}
              onChange={(e) => setStripeApiKey(e.target.value)}
              placeholder={t("connections.stripeApiKeyPlaceholder")}
              autoComplete="off"
              required
              autoFocus
              dir="ltr"
            />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setStripeModalOpen(false)}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={stripeConnectMutation.isPending}>
              {stripeConnectMutation.isPending ? t("common.loading") : t("connections.connectStripe")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
