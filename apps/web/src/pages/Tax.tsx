import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Sparkles, Plus, Trash2, Building2, ExternalLink } from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, SectionTitle, Select, PageHeader, StatTile, Table, Field, Notice,
  IconButton, Segmented, EmptyState, PageSkeleton,
} from "@/components/ui";
import { fmtMoney } from "@/lib/utils";
import { useCoachContext } from "@/lib/coachTabs";

interface TaxProfile {
  id: string;
  user_id: string;
  tax_year: number;
  country: string;
  business_type: "sole_trader" | "company" | "partnership";
  abn: string | null;
  gst_registered: boolean;
}

interface TaxSummary {
  gross_income_minor: number;
  total_deductions_minor: number;
  taxable_income_minor: number;
  estimated_tax_minor: number;
  medicare_levy_minor: number;
  total_tax_payable_minor: number;
  effective_rate_pct: number;
  marginal_rate_pct: number;
  tax_brackets_used: Array<{
    bracket_name: string;
    rate_pct: number;
    taxable_in_bracket_minor: number;
    tax_amount_minor: number;
  }>;
}

interface TaxCategory {
  id: string;
  name: string;
  code: string;
  type: string;
  description: string | null;
}

interface TaxDeduction {
  id: string;
  user_id: string;
  transaction_id: string | null;
  tax_category_id: string;
  category_name: string | null;
  category_code: string | null;
  amount_minor: number;
  gst_claimed_minor: number;
  tax_year: number;
  notes: string | null;
  receipt_url: string | null;
}

interface DeductionSuggestion {
  transaction_id: string;
  amount_minor: number;
  merchant_raw: string;
  description: string | null;
  date: string;
  suggested_category_code: string;
  suggested_category_name: string;
  confidence_score: number;
  reasoning: string;
}

interface BasReport {
  quarter: number;
  g1_total_sales_minor: number;
  g1a_gst_on_sales_minor: number;
  g1b_gst_on_purchases_minor: number;
  net_gst_minor: number;
  status: string;
}

const CURRENCY = "AUD";

export default function TaxPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const money = (minor: number) => fmtMoney(minor, CURRENCY, i18n.language);

  const currentYear = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState<number>(currentYear);
  const [selectedQuarter, setSelectedQuarter] = useState<number>(1);

  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [deductionModalOpen, setDeductionModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [businessType, setBusinessType] = useState<"sole_trader" | "company" | "partnership">("sole_trader");
  const [abn, setAbn] = useState("");
  const [gstRegistered, setGstRegistered] = useState(true);

  const [categoryId, setCategoryId] = useState("");
  const [deductionAmount, setDeductionAmount] = useState("");
  const [deductionGst, setDeductionGst] = useState("");
  const [deductionNotes, setDeductionNotes] = useState("");
  const [deductionReceipt, setDeductionReceipt] = useState("");

  const profileQuery = useQuery<TaxProfile>({
    queryKey: ["tax-profile", selectedYear],
    queryFn: async () => {
      try {
        const res = await http.get(`/tax/profile?tax_year=${selectedYear}`);
        return res.data;
      } catch (err: any) {
        if (err?.response?.status === 404) return null;
        throw err;
      }
    },
  });

  const summaryQuery = useQuery<TaxSummary>({
    queryKey: ["tax-summary", selectedYear],
    queryFn: async () => (await http.get(`/tax/summary?tax_year=${selectedYear}`)).data,
  });

  const deductionsQuery = useQuery<TaxDeduction[]>({
    queryKey: ["tax-deductions", selectedYear],
    queryFn: async () => (await http.get(`/tax/deductions?tax_year=${selectedYear}`)).data,
  });

  const categoriesQuery = useQuery<TaxCategory[]>({
    queryKey: ["tax-categories"],
    queryFn: async () => (await http.get("/tax/categories")).data,
  });

  const suggestionsQuery = useQuery<DeductionSuggestion[]>({
    queryKey: ["tax-suggestions"],
    queryFn: async () => (await http.get("/tax/suggestions")).data,
  });

  const basQuery = useQuery<BasReport>({
    queryKey: ["tax-bas", selectedYear, selectedQuarter],
    queryFn: async () => (await http.get(`/tax/bas?tax_year=${selectedYear}&quarter=${selectedQuarter}`)).data,
  });

  const saveProfileMutation = useMutation({
    mutationFn: async (payload: {
      tax_year: number;
      business_type: string;
      abn: string | null;
      gst_registered: boolean;
      country: string;
    }) => (await http.post("/tax/profile", payload)).data,
    onSuccess: () => {
      setProfileModalOpen(false);
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["tax-profile"] });
      void qc.invalidateQueries({ queryKey: ["tax-summary"] });
      void qc.invalidateQueries({ queryKey: ["tax-bas"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || t("tax.saveProfileFailed"));
    },
  });

  const addDeductionMutation = useMutation({
    mutationFn: async (payload: {
      tax_year: number;
      tax_category_id: string;
      amount_minor: number;
      gst_claimed_minor: number;
      notes?: string;
      receipt_url?: string;
    }) => (await http.post("/tax/deductions", payload)).data,
    onSuccess: () => {
      setDeductionModalOpen(false);
      setDeductionAmount("");
      setDeductionGst("");
      setDeductionNotes("");
      setDeductionReceipt("");
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["tax-deductions"] });
      void qc.invalidateQueries({ queryKey: ["tax-summary"] });
      void qc.invalidateQueries({ queryKey: ["tax-bas"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || t("tax.addDeductionFailed"));
    },
  });

  const claimSuggestionMutation = useMutation({
    mutationFn: async (s: DeductionSuggestion) =>
      (
        await http.post("/tax/deductions", {
          tax_year: selectedYear,
          tax_category_code: s.suggested_category_code,
          transaction_id: s.transaction_id,
          amount_minor: s.amount_minor,
          gst_claimed_minor: Math.round(s.amount_minor / 11),
          notes: `${s.merchant_raw} - ${s.description || s.reasoning}`,
        })
      ).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tax-deductions"] });
      void qc.invalidateQueries({ queryKey: ["tax-summary"] });
      void qc.invalidateQueries({ queryKey: ["tax-bas"] });
      void qc.invalidateQueries({ queryKey: ["tax-suggestions"] });
    },
  });

  const deleteDeductionMutation = useMutation({
    mutationFn: async (id: string) => {
      await http.delete(`/tax/deductions/${id}`);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tax-deductions"] });
      void qc.invalidateQueries({ queryKey: ["tax-summary"] });
      void qc.invalidateQueries({ queryKey: ["tax-bas"] });
    },
  });

  function openEditProfile() {
    const p = profileQuery.data;
    if (p) {
      setBusinessType(p.business_type);
      setAbn(p.abn || "");
      setGstRegistered(p.gst_registered);
    }
    setErrorMessage(null);
    setProfileModalOpen(true);
  }

  function openAddDeduction() {
    setCategoryId(categoriesQuery.data?.[0]?.id || "");
    setDeductionAmount("");
    setDeductionGst("");
    setDeductionNotes("");
    setDeductionReceipt("");
    setErrorMessage(null);
    setDeductionModalOpen(true);
  }

  function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    saveProfileMutation.mutate({
      tax_year: selectedYear,
      country: "AU",
      business_type: businessType,
      abn: abn.trim() || null,
      gst_registered: gstRegistered,
    });
  }

  function handleAddDeduction(e: React.FormEvent) {
    e.preventDefault();
    const amountMinor = Math.round(parseFloat(deductionAmount) * 100);
    if (!categoryId || isNaN(amountMinor) || amountMinor <= 0) return;

    const gstMinor = deductionGst.trim()
      ? Math.round(parseFloat(deductionGst) * 100)
      : Math.round(amountMinor / 11);

    addDeductionMutation.mutate({
      tax_year: selectedYear,
      tax_category_id: categoryId,
      amount_minor: amountMinor,
      gst_claimed_minor: isNaN(gstMinor) ? 0 : gstMinor,
      notes: deductionNotes.trim() || undefined,
      receipt_url: deductionReceipt.trim() || undefined,
    });
  }

  useCoachContext({
    tax_year: selectedYear,
    bas_quarter: selectedQuarter,
    currency: CURRENCY,
    business_type: profileQuery.data?.business_type ?? null,
    gst_registered: profileQuery.data?.gst_registered ?? null,
    estimated_tax: summaryQuery.data ? summaryQuery.data.estimated_tax_minor / 100 : null,
    taxable_income: summaryQuery.data ? summaryQuery.data.taxable_income_minor / 100 : null,
    total_deductions: summaryQuery.data ? summaryQuery.data.total_deductions_minor / 100 : null,
    effective_rate_pct: summaryQuery.data?.effective_rate_pct ?? null,
    deductions_claimed: (deductionsQuery.data ?? []).length,
    deduction_suggestions: (suggestionsQuery.data ?? []).length,
    net_gst: basQuery.data ? basQuery.data.net_gst_minor / 100 : null,
  });

  if (summaryQuery.isLoading && profileQuery.isLoading) return <PageSkeleton />;

  const summary = summaryQuery.data;
  const profile = profileQuery.data;
  const deductions = deductionsQuery.data || [];
  const suggestions = suggestionsQuery.data || [];
  const bas = basQuery.data;
  const netGst = bas?.net_gst_minor || 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("tax.title")}
        subtitle={t("tax.subtitle")}
        actions={
          <label className="flex items-center gap-2 text-sm font-medium text-muted">
            {t("tax.taxYear")}
            <Select
              value={selectedYear}
              onChange={(e) => setSelectedYear(parseInt(e.target.value, 10))}
              className="h-10 w-28 py-0"
            >
              {[currentYear, currentYear - 1, currentYear - 2].map((y) => (
                <option key={y} value={y}>{t("tax.fy", { year: y })}</option>
              ))}
            </Select>
          </label>
        }
      />

      {summaryQuery.isError && (
        <Notice tone="neg">
          {t("common.errorBody")}{" "}
          <button type="button" className="font-semibold underline" onClick={() => void summaryQuery.refetch()}>
            {t("common.retry")}
          </button>
        </Notice>
      )}

      <Card className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand/10 text-brand" aria-hidden>
            <Building2 size={20} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold text-ink">
                {t(`tax.businessTypes.${profile?.business_type ?? "sole_trader"}`)}
              </h2>
              <Badge tone="brand">{t("tax.atoBrackets")}</Badge>
              {profile?.gst_registered ? (
                <Badge tone="pos">{t("tax.gstRegisteredBadge")}</Badge>
              ) : (
                <Badge>{t("tax.noGst")}</Badge>
              )}
            </div>
            <p className="mt-0.5 text-sm text-muted">
              {profile?.abn ? t("tax.abnValue", { abn: profile.abn }) : t("tax.noAbn")} · {t("tax.australia")}
            </p>
          </div>
        </div>
        <Button size="sm" variant="secondary" onClick={openEditProfile}>
          {t("tax.editProfile")}
        </Button>
      </Card>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatTile
          label={t("tax.estimatedTax")}
          tone="brand"
          value={<span className="num">{summary ? money(summary.estimated_tax_minor) : "-"}</span>}
          hint={t("tax.effectiveRateValue", { pct: summary?.effective_rate_pct ?? 0 })}
        />
        <StatTile
          label={t("tax.medicareLevy")}
          value={<span className="num">{summary ? money(summary.medicare_levy_minor) : "-"}</span>}
          hint={t("tax.marginalRateValue", { pct: summary?.marginal_rate_pct ?? 0 })}
        />
        <StatTile
          label={t("tax.taxableIncome")}
          value={<span className="num">{summary ? money(summary.taxable_income_minor) : "-"}</span>}
          hint={t("tax.grossIncomeValue", { amount: money(summary?.gross_income_minor ?? 0) })}
        />
        <StatTile
          label={t("tax.totalDeductions")}
          tone="pos"
          value={<span className="num">{summary ? money(summary.total_deductions_minor) : "-"}</span>}
          hint={t("tax.claimedEntries", { count: deductions.length })}
        />
      </div>

      {summary?.tax_brackets_used && summary.tax_brackets_used.length > 0 && (
        <Card as="section">
          <SectionTitle>{t("tax.bracketsTitle")}</SectionTitle>
          <p className="-mt-2 mb-4 text-sm text-muted">{t("tax.bracketsInfo")}</p>
          <ul className="divide-y divide-line">
            {summary.tax_brackets_used.map((b, idx) => (
              <li key={idx} className="flex flex-col gap-1 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-ink">{b.bracket_name}</span>
                  <Badge tone={b.rate_pct > 0 ? "neutral" : "pos"}>{t("tax.ratePct", { pct: b.rate_pct })}</Badge>
                </div>
                <div className="flex items-center gap-4 text-muted">
                  <span>{t("tax.taxable")} <b className="num font-semibold text-ink">{money(b.taxable_in_bracket_minor)}</b></span>
                  <span>{t("tax.tax")} <b className="num font-semibold text-ink">{money(b.tax_amount_minor)}</b></span>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {suggestions.length > 0 && (
        <Card as="section">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div className="flex items-start gap-2.5">
              <Sparkles size={18} className="mt-0.5 shrink-0 text-brand" aria-hidden />
              <div>
                <h2 className="font-semibold text-ink">{t("tax.aiSuggestionsTitle")}</h2>
                <p className="text-sm text-muted">{t("tax.aiSuggestionsSubtitle")}</p>
              </div>
            </div>
            <Badge tone="brand">{t("tax.suggestionCount", { count: suggestions.length })}</Badge>
          </div>
          <ul className="divide-y divide-line">
            {suggestions.map((s) => (
              <li key={s.transaction_id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-ink">{s.merchant_raw}</span>
                    <Badge tone="pos">{s.suggested_category_name}</Badge>
                    <span className="text-sm text-muted">{t("tax.matchPct", { pct: Math.round(s.confidence_score * 100) })}</span>
                  </div>
                  <p className="text-sm text-muted">{s.reasoning}</p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="num font-semibold text-ink">{money(s.amount_minor)}</span>
                  <Button size="sm" onClick={() => claimSuggestionMutation.mutate(s)} disabled={claimSuggestionMutation.isPending}>
                    <Plus size={14} aria-hidden /> {t("tax.claimSuggestion")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card as="section">
        <SectionTitle
          right={
            <Button size="sm" onClick={openAddDeduction}>
              <Plus size={14} aria-hidden /> {t("tax.addManualDeduction")}
            </Button>
          }
        >
          {t("tax.deductionsTitle")}
        </SectionTitle>

        {deductions.length === 0 ? (
          <EmptyState title={t("tax.noDeductions")} />
        ) : (
          <Table label={t("tax.deductionsTitle")}>
            <thead>
              <tr>
                <th>{t("tax.category")}</th>
                <th className="hidden sm:table-cell">{t("tax.notes")}</th>
                <th className="!text-end">{t("tax.amount")}</th>
                <th className="hidden !text-end sm:table-cell">{t("tax.gstClaimed")}</th>
                <th><span className="sr-only">{t("common.actions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {deductions.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge>{d.category_code || t("tax.deduction")}</Badge>
                      <span className="font-medium text-ink">{d.category_name || t("tax.generalBusiness")}</span>
                    </div>
                  </td>
                  <td className="hidden max-w-xs text-muted sm:table-cell">
                    <span className="line-clamp-1">{d.notes || "-"}</span>
                    {d.receipt_url && (
                      <a
                        href={d.receipt_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-brand hover:underline"
                      >
                        <ExternalLink size={12} aria-hidden /> {t("tax.receipt")}
                      </a>
                    )}
                  </td>
                  <td className="num text-end font-semibold text-ink">{money(d.amount_minor)}</td>
                  <td className="num hidden text-end text-muted sm:table-cell">{money(d.gst_claimed_minor)}</td>
                  <td className="w-12 text-end">
                    <IconButton
                      label={t("tax.deleteDeduction")}
                      icon={<Trash2 size={16} />}
                      onClick={() => deleteDeductionMutation.mutate(d.id)}
                      className="text-neg hover:bg-neg/10 hover:text-neg"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card as="section">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold text-ink">{t("tax.basTitle")}</h2>
            <p className="text-sm text-muted">{t("tax.basSubtitle")}</p>
          </div>
          <Segmented
            label={t("tax.quarter")}
            value={selectedQuarter}
            onChange={setSelectedQuarter}
            options={[1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }))}
          />
        </div>

        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: t("tax.g1Sales"), value: bas?.g1_total_sales_minor ?? 0, help: t("tax.g1Help") },
            { label: t("tax.g1aGstSales"), value: bas?.g1a_gst_on_sales_minor ?? 0, help: t("tax.g1aHelp") },
            { label: t("tax.g1bGstPurchases"), value: bas?.g1b_gst_on_purchases_minor ?? 0, help: t("tax.g1bHelp") },
          ].map((row) => (
            <div key={row.label} className="rounded-lg bg-sunken p-4">
              <dt className="text-sm font-medium text-muted">{row.label}</dt>
              <dd className="num mt-1 text-xl font-semibold text-ink">{money(row.value)}</dd>
              <dd className="mt-1 text-xs text-muted">{row.help}</dd>
            </div>
          ))}
          <div className="rounded-lg border border-brand/40 bg-brand/5 p-4">
            <dt className="text-sm font-medium text-brand">{t("tax.netGst")} (1A - 1B)</dt>
            <dd className={`num mt-1 text-xl font-semibold ${netGst > 0 ? "text-ink" : "text-pos"}`}>{money(Math.abs(netGst))}</dd>
            <dd className="mt-1 text-xs font-medium text-muted">{netGst >= 0 ? t("tax.gstPayable") : t("tax.gstRefund")}</dd>
          </div>
        </dl>
      </Card>

      <Modal open={profileModalOpen} onClose={() => setProfileModalOpen(false)} title={t("tax.editProfile")}>
        <form onSubmit={handleSaveProfile} className="space-y-4">
          {errorMessage && <Notice tone="neg">{errorMessage}</Notice>}
          <Field label={t("tax.businessType")}>
            <Select value={businessType} onChange={(e) => setBusinessType(e.target.value as TaxProfile["business_type"])}>
              <option value="sole_trader">{t("tax.businessTypes.sole_trader")}</option>
              <option value="company">{t("tax.businessTypes.company")}</option>
              <option value="partnership">{t("tax.businessTypes.partnership")}</option>
            </Select>
          </Field>
          <Field label={t("tax.abn")}>
            <Input value={abn} onChange={(e) => setAbn(e.target.value)} placeholder={t("tax.abnPlaceholder")} inputMode="numeric" />
          </Field>
          <div>
            <label className="flex min-h-10 cursor-pointer items-center gap-2 text-sm font-medium text-ink">
              <input
                type="checkbox"
                checked={gstRegistered}
                onChange={(e) => setGstRegistered(e.target.checked)}
                className="size-4 accent-brand"
              />
              {t("tax.gstRegistered")}
            </label>
            <p className="text-sm text-muted">{t("tax.gstRegisteredHelp")}</p>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setProfileModalOpen(false)}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={saveProfileMutation.isPending}>
              {saveProfileMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={deductionModalOpen} onClose={() => setDeductionModalOpen(false)} title={t("tax.addManualDeduction")}>
        <form onSubmit={handleAddDeduction} className="space-y-4">
          {errorMessage && <Notice tone="neg">{errorMessage}</Notice>}
          <Field label={t("tax.category")}>
            <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} required>
              {(categoriesQuery.data || []).map((c) => (
                <option key={c.id} value={c.id}>{c.code}: {c.name}</option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("tax.amountCurrency", { currency: CURRENCY })}>
              <Input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0.01"
                value={deductionAmount}
                onChange={(e) => setDeductionAmount(e.target.value)}
                required
              />
            </Field>
            <Field label={t("tax.gstClaimed")} hint={t("tax.gstAutoHint")}>
              <Input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                value={deductionGst}
                onChange={(e) => setDeductionGst(e.target.value)}
              />
            </Field>
          </div>
          <Field label={t("tax.notes")}>
            <Input value={deductionNotes} onChange={(e) => setDeductionNotes(e.target.value)} placeholder={t("tax.notesPlaceholder")} />
          </Field>
          <Field label={t("tax.receiptUrl")} hint={t("common.optional")}>
            <Input value={deductionReceipt} onChange={(e) => setDeductionReceipt(e.target.value)} placeholder={t("tax.receiptUrlPlaceholder")} dir="ltr" />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setDeductionModalOpen(false)}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={addDeductionMutation.isPending}>
              {addDeductionMutation.isPending ? t("common.loading") : t("tax.claimDeduction")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
