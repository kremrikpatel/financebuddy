import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Users, UserPlus, Shield, Pencil, Trash2, TrendingUp, AlertCircle, Plus } from "lucide-react";
import { http } from "@/lib/api";
import {
  Badge, Button, Card, Input, Modal, SectionTitle, Select, PageHeader, StatTile, PageSkeleton, EmptyState,
  Field, Notice, IconButton, Meter,
} from "@/components/ui";
import { fmtMoney } from "@/lib/utils";
import { useAuth } from "@/stores/auth";
import { useCoachContext } from "@/lib/coachTabs";

type Role = "owner" | "admin" | "member" | "child";

interface Member {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: Role;
  spending_limit_minor: number | null;
  spent_this_month_minor: number;
  is_active: boolean;
  joined_at?: string;
}

interface FamilyOverview {
  group: {
    id: string;
    name: string;
    owner_id: string;
    created_at: string;
  };
  members: Member[];
  total_spent_minor: number;
}

const roleTone = (role: string): "brand" | "pos" | "warn" | "neutral" =>
  role === "owner" ? "brand" : role === "admin" ? "pos" : role === "child" ? "warn" : "neutral";

export default function FamilyPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const currentUser = useAuth((s) => s.user);
  const currency = currentUser?.base_currency || "AUD";
  const money = (minor: number) => fmtMoney(minor, currency, i18n.language);

  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [editMember, setEditMember] = useState<Member | null>(null);
  const [removeMember, setRemoveMember] = useState<Member | null>(null);

  const [groupName, setGroupName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("member");
  const [inviteLimit, setInviteLimit] = useState("");
  const [editRole, setEditRole] = useState<Role>("member");
  const [editLimit, setEditLimit] = useState("");
  const [editIsActive, setEditIsActive] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: overview, isLoading, isError } = useQuery<FamilyOverview>({
    queryKey: ["family-overview"],
    queryFn: async () => (await http.get("/family/overview")).data,
    retry: false,
  });

  const createGroupMutation = useMutation({
    mutationFn: async (name: string) => (await http.post("/family", { name })).data,
    onSuccess: () => {
      setCreateGroupOpen(false);
      setGroupName("");
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["family-overview"] });
    },
    onError: (err: any) => setErrorMessage(err?.response?.data?.detail || t("family.createFailed")),
  });

  const inviteMemberMutation = useMutation({
    mutationFn: async (payload: { email: string; role: string; spending_limit_minor: number | null }) =>
      (await http.post("/family/members/invite", payload)).data,
    onSuccess: () => {
      setInviteOpen(false);
      setInviteEmail("");
      setInviteLimit("");
      setInviteRole("member");
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["family-overview"] });
    },
    onError: (err: any) => setErrorMessage(err?.response?.data?.detail || t("family.inviteFailed")),
  });

  const updateMemberMutation = useMutation({
    mutationFn: async ({
      memberId,
      role,
      spending_limit_minor,
      is_active,
    }: {
      memberId: string;
      role: string;
      spending_limit_minor: number | null;
      is_active: boolean;
    }) => (await http.patch(`/family/members/${memberId}`, { role, spending_limit_minor, is_active })).data,
    onSuccess: () => {
      setEditMember(null);
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["family-overview"] });
    },
    onError: (err: any) => setErrorMessage(err?.response?.data?.detail || t("family.updateFailed")),
  });

  const deleteMemberMutation = useMutation({
    mutationFn: async (memberId: string) => {
      await http.delete(`/family/members/${memberId}`);
    },
    onSuccess: () => {
      setRemoveMember(null);
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["family-overview"] });
    },
    onError: (err: any) => setErrorMessage(err?.response?.data?.detail || t("family.removeFailed")),
  });

  function openEditModal(m: Member) {
    setEditMember(m);
    setEditRole(m.role);
    setEditLimit(m.spending_limit_minor !== null ? (m.spending_limit_minor / 100).toFixed(2) : "");
    setEditIsActive(m.is_active);
    setErrorMessage(null);
  }

  function handleCreateGroup(e: React.FormEvent) {
    e.preventDefault();
    if (!groupName.trim()) return;
    createGroupMutation.mutate(groupName.trim());
  }

  function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    const limitMinor = inviteLimit.trim() ? Math.round(parseFloat(inviteLimit) * 100) : null;
    inviteMemberMutation.mutate({
      email: inviteEmail.trim(),
      role: inviteRole,
      spending_limit_minor: isNaN(Number(limitMinor)) ? null : limitMinor,
    });
  }

  function handleUpdate(e: React.FormEvent) {
    e.preventDefault();
    if (!editMember) return;
    const limitMinor = editLimit.trim() ? Math.round(parseFloat(editLimit) * 100) : null;
    updateMemberMutation.mutate({
      memberId: editMember.id,
      role: editRole,
      spending_limit_minor: isNaN(Number(limitMinor)) ? null : limitMinor,
      is_active: editIsActive,
    });
  }

  const roleOptions = (
    <>
      <option value="member">{t("family.roles.member")}</option>
      <option value="admin">{t("family.roles.admin")}</option>
      <option value="child">{t("family.roles.child")}</option>
      <option value="owner">{t("family.roles.owner")}</option>
    </>
  );

  // Aggregates only: member names and emails are never sent to the coach.
  const familyMembers = overview?.members ?? [];
  useCoachContext(overview?.group ? {
    currency,
    members: familyMembers.length,
    active_members: familyMembers.filter((m) => m.is_active).length,
    members_with_limits: familyMembers.filter((m) => m.spending_limit_minor !== null).length,
    members_over_limit: familyMembers.filter((m) => m.spending_limit_minor && m.spent_this_month_minor > m.spending_limit_minor).length,
    household_spend_this_month: overview.total_spent_minor / 100,
  } : { family_group: null });

  if (isLoading) return <PageSkeleton tiles={3} />;

  if (isError || !overview?.group) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("family.title")} subtitle={t("family.subtitle")} />
        <Card>
          <EmptyState
            icon={<Users size={22} />}
            title={t("family.createGroup")}
            body={t("family.noGroupPrompt")}
            action={
              <Button
                onClick={() => {
                  setGroupName("");
                  setErrorMessage(null);
                  setCreateGroupOpen(true);
                }}
              >
                <Plus size={16} aria-hidden /> {t("family.createGroup")}
              </Button>
            }
          />
        </Card>

        <Modal open={createGroupOpen} onClose={() => setCreateGroupOpen(false)} title={t("family.createGroup")}>
          <form onSubmit={handleCreateGroup} className="space-y-4">
            {errorMessage && <Notice tone="neg">{errorMessage}</Notice>}
            <Field label={t("family.groupName")}>
              <Input
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                placeholder={t("family.groupNamePlaceholder")}
                required
                autoFocus
              />
            </Field>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" onClick={() => setCreateGroupOpen(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={createGroupMutation.isPending}>
                {createGroupMutation.isPending ? t("common.loading") : t("common.save")}
              </Button>
            </div>
          </form>
        </Modal>
      </div>
    );
  }

  const members = overview.members || [];
  const activeMembersCount = members.filter((m) => m.is_active).length;
  const childMembersCount = members.filter((m) => m.role === "child" || m.spending_limit_minor !== null).length;
  const isCallerAdminOrOwner = members.some(
    (m) =>
      m.user_id === currentUser?.id &&
      (m.role === "owner" || m.role === "admin" || overview.group.owner_id === currentUser?.id),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={overview.group.name}
        badge={<Badge tone="brand">{t("family.groupBadge")}</Badge>}
        subtitle={t("family.subtitle")}
        actions={
          isCallerAdminOrOwner && (
            <Button
              onClick={() => {
                setInviteEmail("");
                setInviteLimit("");
                setInviteRole("member");
                setErrorMessage(null);
                setInviteOpen(true);
              }}
            >
              <UserPlus size={16} aria-hidden /> {t("family.inviteMember")}
            </Button>
          )
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
        <StatTile
          label={t("family.householdSpend")}
          icon={<TrendingUp size={18} />}
          value={<span className="num">{money(overview.total_spent_minor)}</span>}
          hint={t("family.acrossMembers", { count: activeMembersCount })}
        />
        <StatTile
          label={t("family.activeMembers")}
          icon={<Users size={18} />}
          value={<span className="num">{activeMembersCount}</span>}
          hint={t("family.registeredTotal", { count: members.length })}
        />
        <StatTile
          label={t("family.supervisedAccounts")}
          icon={<Shield size={18} />}
          value={<span className="num">{childMembersCount}</span>}
          hint={t("family.withLimits")}
          className="sm:col-span-2 lg:col-span-1"
        />
      </div>

      <Card as="section">
        <SectionTitle>{t("family.membersList")}</SectionTitle>
        <ul className="divide-y divide-line">
          {members.map((m) => {
            const hasLimit = m.spending_limit_minor !== null && m.spending_limit_minor > 0;
            const spentMinor = m.spent_this_month_minor || 0;
            const limitMinor = m.spending_limit_minor || 1;
            const pct = hasLimit ? Math.min(Math.round((spentMinor / limitMinor) * 100), 100) : 0;
            const isOverLimit = hasLimit && spentMinor > limitMinor;
            const isNearLimit = hasLimit && !isOverLimit && pct >= 80;

            return (
              <li key={m.id} className="flex flex-col gap-4 py-4 first:pt-0 last:pb-0 md:flex-row md:items-center md:justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="grid size-10 shrink-0 place-items-center rounded-full bg-brand/10 text-sm font-semibold text-brand" aria-hidden>
                    {(m.name || m.email).charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-medium text-ink">{m.name}</p>
                      <Badge tone={roleTone(m.role)}>{t(`family.roles.${m.role}`, m.role)}</Badge>
                      {!m.is_active && <Badge tone="warn">{t("family.statusInactive")}</Badge>}
                    </div>
                    <p className="truncate text-sm text-muted">{m.email}</p>
                  </div>
                </div>

                <div className="flex-1 md:max-w-xs">
                  <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                    <span className="text-muted">
                      {t("family.spentThisMonth")} <b className="num font-semibold text-ink">{money(spentMinor)}</b>
                    </span>
                    <span className="num text-muted">
                      {hasLimit ? `/ ${money(m.spending_limit_minor!)}` : t("family.unlimited")}
                    </span>
                  </div>
                  {hasLimit ? (
                    <div className="space-y-1">
                      <Meter
                        value={pct}
                        tone={isOverLimit ? "neg" : isNearLimit ? "warn" : "brand"}
                        label={t("family.limitMeter", { name: m.name, pct })}
                      />
                      <div className="flex items-center justify-between text-xs">
                        <span className={isOverLimit ? "font-semibold text-neg" : "text-muted"}>{t("family.pctUsed", { pct })}</span>
                        {isOverLimit ? (
                          <span className="flex items-center gap-1 font-semibold text-neg">
                            <AlertCircle size={12} aria-hidden /> {t("family.exceeded")}
                          </span>
                        ) : (
                          <span className="text-muted">
                            {t("family.remainingAmount", { amount: money(Math.max(0, m.spending_limit_minor! - spentMinor)) })}
                          </span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted">{t("family.noLimit")}</p>
                  )}
                </div>

                {isCallerAdminOrOwner && (
                  <div className="flex items-center gap-1 self-end md:self-center">
                    <Button size="sm" variant="secondary" onClick={() => openEditModal(m)}>
                      <Pencil size={14} aria-hidden /> {t("common.edit")}
                    </Button>
                    {m.role !== "owner" && (
                      <IconButton
                        label={t("family.removeNamed", { name: m.name })}
                        icon={<Trash2 size={16} />}
                        onClick={() => setRemoveMember(m)}
                        className="text-neg hover:bg-neg/10 hover:text-neg"
                      />
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <Modal open={inviteOpen} onClose={() => setInviteOpen(false)} title={t("family.inviteMember")}>
        <form onSubmit={handleInvite} className="space-y-4">
          {errorMessage && <Notice tone="neg">{errorMessage}</Notice>}
          <Field label={t("auth.email")}>
            <Input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder={t("family.emailPlaceholder")}
              required
              autoFocus
              dir="ltr"
            />
          </Field>
          <Field label={t("family.role")} hint={t(`family.roleDescriptions.${inviteRole}`)}>
            <Select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Role)}>{roleOptions}</Select>
          </Field>
          <Field label={`${t("family.spendingLimit")} (${currency})`} hint={t("family.spendingLimitPlaceholder")}>
            <Input type="number" inputMode="decimal" step="0.01" min="0" value={inviteLimit} onChange={(e) => setInviteLimit(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setInviteOpen(false)}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={inviteMemberMutation.isPending}>
              {inviteMemberMutation.isPending ? t("common.loading") : t("family.inviteMember")}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(editMember)} onClose={() => setEditMember(null)} title={t("family.editMember")}>
        <form onSubmit={handleUpdate} className="space-y-4">
          {errorMessage && <Notice tone="neg">{errorMessage}</Notice>}
          <div>
            <p className="font-medium text-ink">{editMember?.name}</p>
            <p className="text-sm text-muted">{editMember?.email}</p>
          </div>
          <Field label={t("family.role")}>
            <Select value={editRole} onChange={(e) => setEditRole(e.target.value as Role)}>{roleOptions}</Select>
          </Field>
          <Field label={`${t("family.spendingLimit")} (${currency})`} hint={t("family.spendingLimitPlaceholder")}>
            <Input type="number" inputMode="decimal" step="0.01" min="0" value={editLimit} onChange={(e) => setEditLimit(e.target.value)} />
          </Field>
          <label className="flex min-h-10 cursor-pointer items-center gap-2 text-sm font-medium text-ink">
            <input type="checkbox" checked={editIsActive} onChange={(e) => setEditIsActive(e.target.checked)} className="size-4 accent-brand" />
            {t("family.statusActive")}
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setEditMember(null)}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={updateMemberMutation.isPending}>
              {updateMemberMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(removeMember)} onClose={() => setRemoveMember(null)} title={t("family.removeMember")}>
        <div className="space-y-4">
          {errorMessage && <Notice tone="neg">{errorMessage}</Notice>}
          <p className="text-sm text-ink">{t("family.confirmRemove")}</p>
          <div className="rounded-lg bg-sunken p-3 text-sm">
            <p className="font-medium text-ink">{removeMember?.name}</p>
            <p className="text-muted">{removeMember?.email}</p>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setRemoveMember(null)}>{t("common.cancel")}</Button>
            <Button
              variant="danger"
              disabled={deleteMemberMutation.isPending}
              onClick={() => {
                if (removeMember) deleteMemberMutation.mutate(removeMember.id);
              }}
            >
              {deleteMemberMutation.isPending ? t("common.loading") : t("family.removeMember")}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
