import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Receipt,
  FileText,
  Calculator,
  Sparkles,
  Plus,
  Trash2,
  Building2,
  Percent,
  CheckCircle2,
  TrendingDown,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  Input,
  Modal,
  SectionTitle,
  Select,
  Spinner,
} from "@/components/ui";
import { fmtMoney } from "@/lib/utils";

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

export default function TaxPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const currentYear = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState<number>(currentYear);
  const [selectedQuarter, setSelectedQuarter] = useState<number>(1);

  // Modals
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [deductionModalOpen, setDeductionModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Profile Form state
  const [businessType, setBusinessType] = useState<"sole_trader" | "company" | "partnership">("sole_trader");
  const [abn, setAbn] = useState("");
  const [gstRegistered, setGstRegistered] = useState(true);

  // Deduction Form state
  const [categoryId, setCategoryId] = useState("");
  const [deductionAmount, setDeductionAmount] = useState("");
  const [deductionGst, setDeductionGst] = useState("");
  const [deductionNotes, setDeductionNotes] = useState("");
  const [deductionReceipt, setDeductionReceipt] = useState("");

  // Queries
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
    queryFn: async () => {
      const res = await http.get(`/tax/summary?tax_year=${selectedYear}`);
      return res.data;
    },
  });

  const deductionsQuery = useQuery<TaxDeduction[]>({
    queryKey: ["tax-deductions", selectedYear],
    queryFn: async () => {
      const res = await http.get(`/tax/deductions?tax_year=${selectedYear}`);
      return res.data;
    },
  });

  const categoriesQuery = useQuery<TaxCategory[]>({
    queryKey: ["tax-categories"],
    queryFn: async () => {
      const res = await http.get("/tax/categories");
      return res.data;
    },
  });

  const suggestionsQuery = useQuery<DeductionSuggestion[]>({
    queryKey: ["tax-suggestions"],
    queryFn: async () => {
      const res = await http.get("/tax/suggestions");
      return res.data;
    },
  });

  const basQuery = useQuery<BasReport>({
    queryKey: ["tax-bas", selectedYear, selectedQuarter],
    queryFn: async () => {
      const res = await http.get(`/tax/bas?tax_year=${selectedYear}&quarter=${selectedQuarter}`);
      return res.data;
    },
  });

  // Mutations
  const saveProfileMutation = useMutation({
    mutationFn: async (payload: {
      tax_year: number;
      business_type: string;
      abn: string | null;
      gst_registered: boolean;
      country: string;
    }) => {
      const res = await http.post("/tax/profile", payload);
      return res.data;
    },
    onSuccess: () => {
      setProfileModalOpen(false);
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["tax-profile"] });
      void qc.invalidateQueries({ queryKey: ["tax-summary"] });
      void qc.invalidateQueries({ queryKey: ["tax-bas"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || "Failed to save tax profile");
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
    }) => {
      const res = await http.post("/tax/deductions", payload);
      return res.data;
    },
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
      setErrorMessage(err?.response?.data?.detail || "Failed to add deduction");
    },
  });

  const claimSuggestionMutation = useMutation({
    mutationFn: async (s: DeductionSuggestion) => {
      const res = await http.post("/tax/deductions", {
        tax_year: selectedYear,
        tax_category_code: s.suggested_category_code,
        transaction_id: s.transaction_id,
        amount_minor: s.amount_minor,
        gst_claimed_minor: Math.round(s.amount_minor / 11),
        notes: `${s.merchant_raw} - ${s.description || s.reasoning}`,
      });
      return res.data;
    },
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

  const summary = summaryQuery.data;
  const profile = profileQuery.data;
  const deductions = deductionsQuery.data || [];
  const suggestions = suggestionsQuery.data || [];
  const bas = basQuery.data;

  const currency = "AUD";

  return (
    <div className="space-y-6">
      {/* Top Header & Year Filter */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">{t("tax.title")}</h1>
          <p className="text-sm text-muted">{t("tax.subtitle")}</p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
            {t("tax.taxYear")}:
            <Select
              value={selectedYear}
              onChange={(e) => setSelectedYear(parseInt(e.target.value, 10))}
              className="h-9 w-28 py-1 text-sm font-semibold text-ink"
            >
              {[currentYear, currentYear - 1, currentYear - 2].map((y) => (
                <option key={y} value={y}>
                  FY {y}
                </option>
              ))}
            </Select>
          </label>
        </div>
      </div>

      {/* Tax Profile Card */}
      <Card className="flex flex-col gap-4 border-brand/20 bg-gradient-to-r from-brand/5 via-surface to-surface p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="grid size-12 place-items-center rounded-2xl bg-brand text-white shadow-md shadow-brand/20">
            <Building2 size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-bold text-ink">
                {profile
                  ? t(`tax.businessTypes.${profile.business_type}`, profile.business_type)
                  : "Sole Trader (AU)"}
              </h3>
              <Badge tone="brand">ATO Standard Brackets</Badge>
              {profile?.gst_registered ? (
                <Badge tone="pos">GST Registered (10%)</Badge>
              ) : (
                <Badge tone="neutral">No GST</Badge>
              )}
            </div>
            <p className="mt-0.5 text-xs text-muted">
              {profile?.abn ? `ABN: ${profile.abn}` : "No ABN recorded"} · Australia
            </p>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={openEditProfile}>
          {t("tax.editProfile")}
        </Button>
      </Card>

      {/* Tax Estimate KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            {t("tax.estimatedTax")}
          </span>
          <p className="mt-2 text-2xl font-bold text-brand">
            {summary ? fmtMoney(summary.estimated_tax_minor, currency) : "—"}
          </p>
          <div className="mt-1 flex items-center justify-between text-xs text-muted">
            <span>{t("tax.effectiveRate")}:</span>
            <span className="font-semibold text-ink">
              {summary ? `${summary.effective_rate_pct}%` : "0%"}
            </span>
          </div>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            {t("tax.medicareLevy")}
          </span>
          <p className="mt-2 text-2xl font-bold text-ink">
            {summary ? fmtMoney(summary.medicare_levy_minor, currency) : "—"}
          </p>
          <div className="mt-1 flex items-center justify-between text-xs text-muted">
            <span>{t("tax.marginalRate")}:</span>
            <span className="font-semibold text-ink">
              {summary ? `${summary.marginal_rate_pct}%` : "0%"}
            </span>
          </div>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            {t("tax.taxableIncome")}
          </span>
          <p className="mt-2 text-2xl font-bold text-ink">
            {summary ? fmtMoney(summary.taxable_income_minor, currency) : "—"}
          </p>
          <div className="mt-1 flex items-center justify-between text-xs text-muted">
            <span>{t("tax.grossIncome")}:</span>
            <span className="font-medium text-ink">
              {summary ? fmtMoney(summary.gross_income_minor, currency) : "$0"}
            </span>
          </div>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            {t("tax.totalDeductions")}
          </span>
          <p className="mt-2 text-2xl font-bold text-pos">
            {summary ? fmtMoney(summary.total_deductions_minor, currency) : "—"}
          </p>
          <div className="mt-1 flex items-center justify-between text-xs text-muted">
            <span>Claimed entries:</span>
            <span className="font-semibold text-pos">{deductions.length}</span>
          </div>
        </Card>
      </div>

      {/* Tax Brackets Breakdown Visual Card */}
      {summary?.tax_brackets_used && summary.tax_brackets_used.length > 0 && (
        <Card className="p-5">
          <SectionTitle right={<span className="text-xs text-muted font-normal">{t("tax.bracketsInfo")}</span>}>
            Australian Progressive Tax Calculation
          </SectionTitle>
          <div className="space-y-3 pt-2">
            {summary.tax_brackets_used.map((b, idx) => (
              <div key={idx} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="inline-block size-2 rounded-full bg-brand" />
                  <span className="font-medium text-ink">{b.bracket_name}</span>
                  <Badge tone={b.rate_pct > 0 ? "neutral" : "pos"}>
                    {b.rate_pct}% tax
                  </Badge>
                </div>
                <div className="flex items-center gap-4 text-muted">
                  <span>
                    Taxable: <b className="text-ink">{fmtMoney(b.taxable_in_bracket_minor, currency)}</b>
                  </span>
                  <span>
                    Tax: <b className="text-brand">{fmtMoney(b.tax_amount_minor, currency)}</b>
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* AI Deduction Suggestions */}
      {suggestions.length > 0 && (
        <Card className="border-brand/30 bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <div className="flex items-center gap-2">
              <div className="grid size-7 place-items-center rounded-lg bg-brand/10 text-brand">
                <Sparkles size={16} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-ink">
                  {t("tax.aiSuggestionsTitle")}
                </h3>
                <p className="text-xs text-muted">
                  {t("tax.aiSuggestionsSubtitle")}
                </p>
              </div>
            </div>
            <Badge tone="brand">{suggestions.length} suggestions</Badge>
          </div>

          <div className="divide-y divide-line/60 pt-1">
            {suggestions.map((s) => (
              <div
                key={s.transaction_id}
                className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-ink">{s.merchant_raw}</span>
                    <Badge tone="pos">{s.suggested_category_name}</Badge>
                    <span className="text-xs text-muted">({Math.round(s.confidence_score * 100)}% match)</span>
                  </div>
                  <p className="text-xs text-muted">{s.reasoning}</p>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-pos">
                    {fmtMoney(s.amount_minor, currency)}
                  </span>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => claimSuggestionMutation.mutate(s)}
                    disabled={claimSuggestionMutation.isPending}
                    className="flex items-center gap-1.5"
                  >
                    <Plus size={13} /> {t("tax.claimSuggestion")}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Deductions Tracker Section */}
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <SectionTitle>{t("tax.deductionsTitle")}</SectionTitle>
          <Button
            size="sm"
            onClick={() => {
              const defaultCat = categoriesQuery.data?.[0]?.id || "";
              setCategoryId(defaultCat);
              setDeductionAmount("");
              setDeductionGst("");
              setDeductionNotes("");
              setDeductionReceipt("");
              setErrorMessage(null);
              setDeductionModalOpen(true);
            }}
            className="flex items-center gap-1.5"
          >
            <Plus size={14} /> {t("tax.addManualDeduction")}
          </Button>
        </div>

        {deductions.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted">
            {t("tax.noDeductions")}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-line text-muted">
                <tr>
                  <th className="py-2.5 px-3">{t("tax.category")}</th>
                  <th className="py-2.5 px-3">{t("tax.notes")}</th>
                  <th className="py-2.5 px-3 text-right">{t("tax.amount")}</th>
                  <th className="py-2.5 px-3 text-right">{t("tax.gstClaimed")}</th>
                  <th className="py-2.5 px-3 text-center">{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {deductions.map((d) => (
                  <tr key={d.id} className="hover:bg-raised/40 transition">
                    <td className="py-3 px-3 font-medium text-ink">
                      <div className="flex items-center gap-2">
                        <Badge tone="neutral">{d.category_code || "Deduction"}</Badge>
                        <span>{d.category_name || "General Business"}</span>
                      </div>
                    </td>
                    <td className="py-3 px-3 text-muted max-w-xs truncate">
                      {d.notes || "—"}
                      {d.receipt_url && (
                        <a
                          href={d.receipt_url}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-1.5 inline-flex items-center text-brand hover:underline"
                        >
                          <ExternalLink size={10} />
                        </a>
                      )}
                    </td>
                    <td className="py-3 px-3 text-right font-semibold text-pos">
                      {fmtMoney(d.amount_minor, currency)}
                    </td>
                    <td className="py-3 px-3 text-right text-muted">
                      {fmtMoney(d.gst_claimed_minor, currency)}
                    </td>
                    <td className="py-3 px-3 text-center">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => deleteDeductionMutation.mutate(d.id)}
                        className="px-2 text-neg hover:bg-neg/10"
                        title={t("common.delete")}
                      >
                        <Trash2 size={13} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Quarterly BAS Preparation View */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
          <div>
            <h3 className="text-sm font-bold text-ink">{t("tax.basTitle")}</h3>
            <p className="text-xs text-muted">{t("tax.basSubtitle")}</p>
          </div>

          <div className="flex items-center gap-1 rounded-xl bg-raised p-1">
            {[1, 2, 3, 4].map((q) => (
              <button
                key={q}
                onClick={() => setSelectedQuarter(q)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  selectedQuarter === q
                    ? "bg-brand text-white shadow"
                    : "text-muted hover:text-ink"
                }`}
              >
                Q{q}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-line bg-surface p-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              {t("tax.g1Sales")}
            </span>
            <p className="mt-1 text-xl font-bold text-ink">
              {bas ? fmtMoney(bas.g1_total_sales_minor, currency) : "$0.00"}
            </p>
            <p className="mt-1 text-[10px] text-muted">Gross sales including GST</p>
          </div>

          <div className="rounded-xl border border-line bg-surface p-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              {t("tax.g1aGstSales")}
            </span>
            <p className="mt-1 text-xl font-bold text-brand">
              {bas ? fmtMoney(bas.g1a_gst_on_sales_minor, currency) : "$0.00"}
            </p>
            <p className="mt-1 text-[10px] text-muted">1/11th of total GST sales</p>
          </div>

          <div className="rounded-xl border border-line bg-surface p-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
              {t("tax.g1bGstPurchases")}
            </span>
            <p className="mt-1 text-xl font-bold text-pos">
              {bas ? fmtMoney(bas.g1b_gst_on_purchases_minor, currency) : "$0.00"}
            </p>
            <p className="mt-1 text-[10px] text-muted">GST input credits claimed</p>
          </div>

          <div className="rounded-xl border border-brand/40 bg-brand/5 p-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-brand">
              {t("tax.netGst")} (1A - 1B)
            </span>
            <p
              className={`mt-1 text-xl font-bold ${
                (bas?.net_gst_minor || 0) > 0 ? "text-brand" : "text-pos"
              }`}
            >
              {bas ? fmtMoney(Math.abs(bas.net_gst_minor), currency) : "$0.00"}
            </p>
            <p className="mt-1 text-[10px] font-medium text-muted">
              {(bas?.net_gst_minor || 0) >= 0 ? t("tax.gstPayable") : t("tax.gstRefund")}
            </p>
          </div>
        </div>
      </Card>

      {/* Tax Profile Edit Modal */}
      <Modal
        open={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
        title={t("tax.editProfile")}
      >
        <form onSubmit={handleSaveProfile} className="space-y-4">
          {errorMessage && (
            <div className="rounded-xl bg-neg/10 p-3 text-xs text-neg">
              {errorMessage}
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("tax.businessType")}
            </label>
            <Select
              value={businessType}
              onChange={(e) => setBusinessType(e.target.value as any)}
            >
              <option value="sole_trader">{t("tax.businessTypes.sole_trader")}</option>
              <option value="company">{t("tax.businessTypes.company")}</option>
              <option value="partnership">{t("tax.businessTypes.partnership")}</option>
            </Select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("tax.abn")}
            </label>
            <Input
              value={abn}
              onChange={(e) => setAbn(e.target.value)}
              placeholder={t("tax.abnPlaceholder")}
            />
          </div>

          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="gstRegistered"
              checked={gstRegistered}
              onChange={(e) => setGstRegistered(e.target.checked)}
              className="size-4 rounded border-line text-brand focus:ring-brand"
            />
            <label htmlFor="gstRegistered" className="text-xs font-medium text-ink">
              {t("tax.gstRegistered")}
            </label>
          </div>
          <p className="text-[11px] text-muted">{t("tax.gstRegisteredHelp")}</p>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setProfileModalOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={saveProfileMutation.isPending}>
              {saveProfileMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Manual Deduction Modal */}
      <Modal
        open={deductionModalOpen}
        onClose={() => setDeductionModalOpen(false)}
        title={t("tax.addManualDeduction")}
      >
        <form onSubmit={handleAddDeduction} className="space-y-4">
          {errorMessage && (
            <div className="rounded-xl bg-neg/10 p-3 text-xs text-neg">
              {errorMessage}
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("tax.category")}
            </label>
            <Select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              required
            >
              {(categoriesQuery.data || []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted">
                {t("tax.amount")} ($)
              </label>
              <Input
                type="number"
                step="0.01"
                min="0.01"
                value={deductionAmount}
                onChange={(e) => setDeductionAmount(e.target.value)}
                placeholder="250.00"
                required
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-muted">
                {t("tax.gstClaimed")} ($)
              </label>
              <Input
                type="number"
                step="0.01"
                min="0"
                value={deductionGst}
                onChange={(e) => setDeductionGst(e.target.value)}
                placeholder="Auto (1/11th)"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("tax.notes")}
            </label>
            <Input
              value={deductionNotes}
              onChange={(e) => setDeductionNotes(e.target.value)}
              placeholder={t("tax.notesPlaceholder")}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("tax.receiptUrl")}
            </label>
            <Input
              value={deductionReceipt}
              onChange={(e) => setDeductionReceipt(e.target.value)}
              placeholder={t("tax.receiptUrlPlaceholder")}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeductionModalOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={addDeductionMutation.isPending}>
              {addDeductionMutation.isPending ? t("common.loading") : t("tax.claimDeduction")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
