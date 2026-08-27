import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FileUp, ScanLine, Scissors } from "lucide-react";
import { http } from "@/lib/api";
import { Badge, Button, Card, Input, Modal, Select, Spinner } from "@/components/ui";
import { fmtMoney } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface Txn {
  id: string; account_id: string; date: string; amount_minor: number; currency: string;
  merchant_raw: string; merchant_norm: string; description: string | null;
  category_id: string | null; needs_review: boolean; is_split_parent: boolean;
  categorization_method: string | null; tags: string[] | null;
}
interface Cat { id: string; name: string; color: string; kind: string }
interface Acct { id: string; name: string; currency: string }

export default function TransactionsPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("");

  const txns = useQuery({
    queryKey: ["txns", search, reviewOnly, categoryFilter],
    queryFn: () =>
      http
        .get("/transactions", {
          params: {
            limit: 300,
            search: search || undefined,
            needs_review: reviewOnly ? true : undefined,
            category_id: categoryFilter || undefined,
          },
        })
        .then((r) => r.data as Txn[]),
  });
  const cats = useQuery({ queryKey: ["cats"], queryFn: () => http.get("/categories").then((r) => r.data as Cat[]) });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => http.get("/accounts").then((r) => r.data) });

  const catById = useMemo(() => new Map<string, Cat>((cats.data ?? []).map((c) => [c.id, c])), [cats.data]);
  const acctById = useMemo(() => new Map<string, Acct>(((accounts.data ?? []) as Acct[]).map((a) => [a.id, a])), [accounts.data]);

  const confirmCat = useMutation({
    mutationFn: ({ id, categoryId }: { id: string; categoryId: string }) =>
      http.patch(`/transactions/${id}`, { category_id: categoryId, confirmed_by_user: true }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["txns"] }),
  });

  const suggestSplit = useMutation({
    mutationFn: (id: string) => http.post(`/transactions/suggest-split`, null, { params: { txn_id: id } }),
    onSuccess: () => void qc.invalidateQueries(),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{t("txns.title")}</h1>
        <div className="flex gap-2">
          <ImportButton account={(accounts.data ?? [])[0]?.id} />
          <ReceiptButton />
        </div>
      </div>

      <Card className="p-4">
        <div className="flex flex-wrap gap-3">
          <Input className="max-w-xs" placeholder={t("txns.search")} value={search} onChange={(e) => setSearch(e.target.value)} />
          <Select className="max-w-44" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            <option value="">All categories</option>
            {(cats.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <label className="flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={reviewOnly} onChange={(e) => setReviewOnly(e.target.checked)} className="accent-indigo-500" />
            {t("txns.needsReview")}
          </label>
        </div>
      </Card>

      {txns.isLoading ? (
        <Spinner label={t("common.loading")} />
      ) : (
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Merchant</th>
                <th className="px-4 py-3">Category</th>
                <th className="hidden px-4 py-3 md:table-cell">Account</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {(txns.data ?? []).map((x) => (
                <tr key={x.id} className={cn("border-b border-line/60 transition hover:bg-surface", x.needs_review && "bg-amber-500/5")}>
                  <td className="whitespace-nowrap px-4 py-2.5 text-muted tabular-nums">{x.date}</td>
                  <td className="max-w-[220px] px-4 py-2.5">
                    <p className="truncate font-medium">{x.merchant_raw}</p>
                    {x.is_split_parent && <Badge tone="brand">split</Badge>}
                    {(x.tags ?? []).includes("possible-split") && !x.is_split_parent && (
                      <button onClick={() => suggestSplit.mutate(x.id)} title={t("txns.split")} className="ml-1.5 inline-flex items-center gap-0.5 rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] text-brand hover:bg-brand/20">
                        <Scissors size={9} /> AI split
                      </button>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <Select
                      className="h-8 max-w-40 py-0 text-xs"
                      value={x.category_id ?? ""}
                      onChange={(e) => e.target.value && confirmCat.mutate({ id: x.id, categoryId: e.target.value })}
                    >
                      <option value="">{t("txns.uncategorized")}</option>
                      {(cats.data ?? [])
                        .filter((c) => c.kind !== "income")
                        .map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </Select>
                  </td>
                  <td className="hidden px-4 py-2.5 text-muted md:table-cell">{acctById.get(x.account_id)?.name}</td>
                  <td className={cn("px-4 py-2.5 text-right font-semibold tabular-nums", x.amount_minor > 0 ? "text-pos" : "")}>
                    {fmtMoney(x.amount_minor, x.currency, i18n.language)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {x.needs_review && <Badge tone="warn">review</Badge>}
                    {x.categorization_method === "knn" && !x.needs_review && <Badge tone="brand">learned</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(txns.data ?? []).length === 0 && <p className="py-10 text-center text-sm text-muted">No transactions yet — import a CSV or connect a bank.</p>}
        </Card>
      )}
    </div>
  );
}

function ImportButton({ account }: { account?: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<any>(null);

  async function run() {
    if (!file || !account) return;
    const form = new FormData();
    form.append("file", file);
    const kind = file.name.toLowerCase().endsWith(".ofx") || file.name.toLowerCase().endsWith(".qfx") ? "ofx" : "csv";
    const { data } = await http.post(`/import/${account}/${kind}`, form);
    setResult(data);
    void qc.invalidateQueries({ queryKey: ["txns"] });
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <FileUp size={15} /> {t("txns.importCsv")}
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} title={t("txns.importCsv")}>
        <div className="space-y-3">
          {!account && <p className="text-sm text-neg">Create an account first.</p>}
          <input type="file" accept=".csv,.ofx,.qfx" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand/10 file:px-3 file:py-2 file:text-brand" />
          {result && (
            <div className="rounded-xl bg-pos/10 p-3 text-sm text-pos">
              Imported {result.created}, skipped {result.duplicates} duplicates.
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
            <Button onClick={run} disabled={!file || !account}>Import</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

function ReceiptButton() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function scan() {
    if (!file) return;
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await http.post("/receipts/scan", form);
      setParsed(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "OCR unavailable");
    }
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <ScanLine size={15} /> Receipt
      </Button>
      <Modal open={open} onClose={() => { setOpen(false); setParsed(null); }} title="Scan receipt (OCR)">
        <div className="space-y-3">
          <input type="file" accept="image/*" capture="environment" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand/10 file:px-3 file:py-2 file:text-brand" />
          {error && <p className="text-sm text-neg">{error}</p>}
          {parsed && (
            <pre className="max-h-48 overflow-auto rounded-xl border border-line p-3 text-xs">{JSON.stringify(parsed, null, 2)}</pre>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>Close</Button>
            <Button onClick={scan} disabled={!file}>Scan</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
