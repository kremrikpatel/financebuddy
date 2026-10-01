import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FileUp, ScanLine, Scissors, Search, ArrowLeftRight } from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, Select, PageHeader, Table, Skeleton, EmptyState, ErrorState, Notice, Field,
} from "@/components/ui";
import { fmtMoney, cn } from "@/lib/utils";
import { useCoachContext } from "@/lib/coachTabs";

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

  const list = txns.data ?? [];
  const categorySelect = (x: Txn, width: string) => (
    <Select
      className={cn("h-9 min-h-9 py-0 text-sm", width)}
      aria-label={t("txns.categoryFor", { merchant: x.merchant_raw })}
      value={x.category_id ?? ""}
      onChange={(e) => e.target.value && confirmCat.mutate({ id: x.id, categoryId: e.target.value })}
    >
      <option value="">{t("txns.uncategorized")}</option>
      {(cats.data ?? [])
        .filter((c) => c.kind !== "income")
        .map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </Select>
  );
  const catById = useMemo(() => new Map((cats.data ?? []).map((c) => [c.id, c.name])), [cats.data]);

  useCoachContext({
    filters: {
      search: search || null,
      category: categoryFilter ? catById.get(categoryFilter) ?? null : null,
      needs_review_only: reviewOnly,
    },
    shown: list.length,
    needs_review: list.filter((x) => x.needs_review).length,
    transactions: list.slice(0, 15).map((x) => ({
      date: x.date,
      merchant: x.merchant_raw.slice(0, 40),
      amount: x.amount_minor / 100,
      currency: x.currency,
      category: x.category_id ? catById.get(x.category_id) ?? null : null,
    })),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("txns.title")}
        actions={
          <>
            <ImportButton account={(accounts.data ?? [])[0]?.id} />
            <ReceiptButton />
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:max-w-xs">
          <Search size={16} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            type="search"
            className="ps-9"
            placeholder={t("txns.search")}
            aria-label={t("txns.search")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select
          className="w-auto min-w-40"
          aria-label={t("txns.category")}
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
        >
          <option value="">{t("txns.allCategories")}</option>
          {(cats.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <label className="flex min-h-10 cursor-pointer items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={reviewOnly}
            onChange={(e) => setReviewOnly(e.target.checked)}
            className="size-4 accent-brand"
          />
          {t("txns.needsReview")}
        </label>
      </div>

      {txns.isError ? (
        <ErrorState onRetry={() => void txns.refetch()} />
      ) : (
        <Card className="overflow-hidden py-0">
          {txns.isLoading ? (
            <div className="space-y-3 py-5" role="status" aria-label={t("common.loading")}>
              {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-10" />)}
            </div>
          ) : list.length === 0 ? (
            <EmptyState icon={<ArrowLeftRight size={22} />} title={t("txns.emptyTitle")} body={t("txns.emptyBody")} />
          ) : (
            <Table label={t("txns.title")}>
              <thead>
                <tr>
                  <th className="hidden sm:table-cell">{t("txns.date")}</th>
                  <th>{t("txns.merchant")}</th>
                  <th className="hidden sm:table-cell">{t("txns.category")}</th>
                  <th className="hidden md:table-cell">{t("common.account")}</th>
                  <th className="!text-end">{t("txns.amount")}</th>
                  <th className="hidden sm:table-cell"><span className="sr-only">{t("common.status")}</span></th>
                </tr>
              </thead>
              <tbody>
                {list.map((x) => (
                  <tr key={x.id} className={cn("transition-colors hover:bg-sunken/60", x.needs_review && "bg-warn/5")}>
                    <td className="num hidden whitespace-nowrap text-muted sm:table-cell">{x.date}</td>
                    <td className="max-w-[14rem]">
                      <p className="truncate font-medium text-ink">{x.merchant_raw}</p>
                      <p className="num text-xs text-muted sm:hidden">{x.date}</p>
                      <div className="mt-1 flex flex-wrap gap-1 empty:hidden">
                        {x.is_split_parent && <Badge tone="brand">{t("txns.splitBadge")}</Badge>}
                        {(x.tags ?? []).includes("possible-split") && !x.is_split_parent && (
                          <button
                            type="button"
                            onClick={() => suggestSplit.mutate(x.id)}
                            className="chip bg-brand/10 text-brand hover:bg-brand/20"
                          >
                            <Scissors size={12} aria-hidden /> {t("txns.split")}
                          </button>
                        )}
                        {x.needs_review && <span className="sm:hidden"><Badge tone="warn">{t("txns.review")}</Badge></span>}
                      </div>
                      {/* Below sm the category picker sits under the merchant so Amount stays visible. */}
                      <div className="mt-2 sm:hidden">{categorySelect(x, "w-full")}</div>
                    </td>
                    <td className="hidden sm:table-cell">{categorySelect(x, "w-44")}</td>
                    <td className="hidden text-muted md:table-cell">{acctById.get(x.account_id)?.name}</td>
                    <td className={cn("num whitespace-nowrap text-end font-semibold", x.amount_minor > 0 ? "text-pos" : "text-ink")}>
                      {fmtMoney(x.amount_minor, x.currency, i18n.language)}
                    </td>
                    <td className="hidden text-end sm:table-cell">
                      {x.needs_review && <Badge tone="warn">{t("txns.review")}</Badge>}
                      {x.categorization_method === "knn" && !x.needs_review && <Badge tone="brand">{t("txns.learned")}</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
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
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <FileUp size={16} aria-hidden /> {t("txns.importCsv")}
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} title={t("txns.importCsv")}>
        <div className="space-y-4">
          {!account && <Notice tone="neg">{t("txns.createAccountFirst")}</Notice>}
          <Field label={t("txns.chooseFile")} hint={t("txns.importHint")}>
            <input
              type="file"
              accept=".csv,.ofx,.qfx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-ink file:me-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-brand/10 file:px-3 file:py-2 file:font-medium file:text-brand"
            />
          </Field>
          {result && (
            <Notice tone="pos">{t("txns.importResult", { created: result.created, duplicates: result.duplicates })}</Notice>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
            <Button onClick={run} disabled={!file || !account}>{t("txns.import")}</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

function ReceiptButton() {
  const { t } = useTranslation();
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
      setError(e?.response?.data?.detail ?? t("txns.ocrUnavailable"));
    }
  }

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <ScanLine size={16} aria-hidden /> {t("txns.scanReceipt")}
      </Button>
      <Modal open={open} onClose={() => { setOpen(false); setParsed(null); }} title={t("txns.scanReceipt")}>
        <div className="space-y-4">
          <Field label={t("txns.chooseFile")}>
            <input
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-ink file:me-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-brand/10 file:px-3 file:py-2 file:font-medium file:text-brand"
            />
          </Field>
          {error && <Notice tone="neg">{error}</Notice>}
          {parsed && (
            <pre dir="ltr" className="max-h-48 overflow-auto rounded-lg bg-sunken p-3 text-xs text-ink">{JSON.stringify(parsed, null, 2)}</pre>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>{t("common.close")}</Button>
            <Button onClick={scan} disabled={!file}>{t("txns.scan")}</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
