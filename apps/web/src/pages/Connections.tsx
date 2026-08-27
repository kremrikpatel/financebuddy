import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, RefreshCw, Trash2, Globe2 } from "lucide-react";
import { http } from "@/lib/api";
import { Badge, Button, Card, SectionTitle, Spinner } from "@/components/ui";

export default function ConnectionsPage() {
  const qc = useQueryClient();
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => http.get("/connections/providers").then((r) => r.data.providers) });
  const connections = useQuery({ queryKey: ["connections"], queryFn: () => http.get("/connections").then((r) => r.data) });
  const [status, setStatus] = useState<string | null>(null);

  const startLink = useMutation({
    mutationFn: async (provider: string) =>
      (await http.post("/connections/link/start", { provider })).data,
    onSuccess: (data) => {
      if (data.link_url) window.open(data.link_url, "_blank");
      else if (data.link_token) {
        // Plaid Link flow would initialize here with the token.
        setStatus("Link token received — integrate Plaid Link drop-in to complete.");
      } else setStatus(JSON.stringify(data));
    },
    onError: (e: any) => setStatus(e?.response?.data?.detail ?? "Provider unavailable"),
  });

  const sync = useMutation({
    mutationFn: (id: string) => http.post(`/connections/${id}/sync`).then((r) => r.data),
    onSuccess: (r) => {
      setStatus(`Synced: +${r.created_txns} new transactions (${(r.created_accounts ?? []).join(", ") || "no new accounts"})`);
      void qc.invalidateQueries();
    },
  });

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Bank connections</h1>

      <Card>
        <SectionTitle>Open banking providers</SectionTitle>
        <div className="grid gap-3 md:grid-cols-3">
          {(providers.data ?? []).map((p: any) => (
            <div key={p.key} className="flex items-center justify-between rounded-xl border border-line p-3.5">
              <div className="flex items-center gap-3">
                <Globe2 size={18} className="text-brand" />
                <div>
                  <p className="text-sm font-semibold capitalize">{p.key}</p>
                  <p className="text-xs text-muted">{p.region}</p>
                </div>
              </div>
              <Button size="sm" variant={p.configured ? "primary" : "outline"} disabled={!p.configured}
                onClick={() => startLink.mutate(p.key)}>
                {p.configured ? "Connect" : "No keys"}
              </Button>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">
          CSV / OFX import and OCR receipts are available on the Transactions page for any institution.
        </p>
      </Card>

      {status && <Card className="border-brand/40 text-sm text-brand">{status}</Card>}

      <Card>
        <SectionTitle>Your connections</SectionTitle>
        {connections.isLoading ? <Spinner /> : (connections.data ?? []).length === 0 ? (
          <p className="py-6 text-center text-sm text-muted">No connections yet.</p>
        ) : (
          <ul className="space-y-2">
            {(connections.data ?? []).map((c: any) => (
              <li key={c.id} className="flex items-center justify-between rounded-xl border border-line p-3.5">
                <div>
                  <p className="text-sm font-medium">{c.institution_name ?? c.provider}</p>
                  <p className="text-xs text-muted capitalize">{c.provider} · {c.region}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={c.status === "active" ? "pos" : "neutral"}>{c.status}</Badge>
                  <Button size="sm" variant="outline" onClick={() => sync.mutate(c.id)} disabled={sync.isPending}>
                    <RefreshCw size={13} /> Sync
                  </Button>
                  <Button size="sm" variant="ghost" onClick={async () => { await http.delete(`/connections/${c.id}`); void qc.invalidateQueries(); }}>
                    <Trash2 size={13} className="text-neg" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
