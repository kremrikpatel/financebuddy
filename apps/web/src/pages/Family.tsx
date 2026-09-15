import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Users,
  UserPlus,
  Shield,
  ShieldAlert,
  Edit2,
  Trash2,
  DollarSign,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
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
import { useAuth } from "@/stores/auth";

interface Member {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: "owner" | "admin" | "member" | "child";
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

export default function FamilyPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const currentUser = useAuth((s) => s.user);

  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [editMember, setEditMember] = useState<Member | null>(null);
  const [removeMember, setRemoveMember] = useState<Member | null>(null);

  // Form states
  const [groupName, setGroupName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"owner" | "admin" | "member" | "child">("member");
  const [inviteLimit, setInviteLimit] = useState("");
  const [editRole, setEditRole] = useState<"owner" | "admin" | "member" | "child">("member");
  const [editLimit, setEditLimit] = useState("");
  const [editIsActive, setEditIsActive] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const {
    data: overview,
    isLoading,
    isError,
  } = useQuery<FamilyOverview>({
    queryKey: ["family-overview"],
    queryFn: async () => {
      const res = await http.get("/family/overview");
      return res.data;
    },
    retry: false,
  });

  const createGroupMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await http.post("/family", { name });
      return res.data;
    },
    onSuccess: () => {
      setCreateGroupOpen(false);
      setGroupName("");
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["family-overview"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || "Failed to create family group");
    },
  });

  const inviteMemberMutation = useMutation({
    mutationFn: async (payload: {
      email: string;
      role: string;
      spending_limit_minor: number | null;
    }) => {
      const res = await http.post("/family/members/invite", payload);
      return res.data;
    },
    onSuccess: () => {
      setInviteOpen(false);
      setInviteEmail("");
      setInviteLimit("");
      setInviteRole("member");
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["family-overview"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || "Failed to invite member");
    },
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
    }) => {
      const res = await http.patch(`/family/members/${memberId}`, {
        role,
        spending_limit_minor,
        is_active,
      });
      return res.data;
    },
    onSuccess: () => {
      setEditMember(null);
      setErrorMessage(null);
      void qc.invalidateQueries({ queryKey: ["family-overview"] });
    },
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || "Failed to update member");
    },
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
    onError: (err: any) => {
      setErrorMessage(err?.response?.data?.detail || "Failed to remove member");
    },
  });

  function openEditModal(m: Member) {
    setEditMember(m);
    setEditRole(m.role);
    setEditLimit(
      m.spending_limit_minor !== null
        ? (m.spending_limit_minor / 100).toFixed(2)
        : "",
    );
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
    const limitMinor = inviteLimit.trim()
      ? Math.round(parseFloat(inviteLimit) * 100)
      : null;
    inviteMemberMutation.mutate({
      email: inviteEmail.trim(),
      role: inviteRole,
      spending_limit_minor: isNaN(Number(limitMinor)) ? null : limitMinor,
    });
  }

  function handleUpdate(e: React.FormEvent) {
    e.preventDefault();
    if (!editMember) return;
    const limitMinor = editLimit.trim()
      ? Math.round(parseFloat(editLimit) * 100)
      : null;
    updateMemberMutation.mutate({
      memberId: editMember.id,
      role: editRole,
      spending_limit_minor: isNaN(Number(limitMinor)) ? null : limitMinor,
      is_active: editIsActive,
    });
  }

  const roleTone = (role: string): "brand" | "pos" | "warn" | "neutral" => {
    switch (role) {
      case "owner":
        return "brand";
      case "admin":
        return "pos";
      case "child":
        return "warn";
      default:
        return "neutral";
    }
  };

  if (isLoading) return <Spinner label={t("common.loading")} />;

  // Empty state if no group exists
  if (isError || !overview?.group) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">{t("family.title")}</h1>
          <p className="text-sm text-muted">{t("family.subtitle")}</p>
        </div>

        <Card className="flex flex-col items-center justify-center p-12 text-center">
          <div className="mb-4 grid size-16 place-items-center rounded-2xl bg-brand/10 text-brand">
            <Users size={32} />
          </div>
          <h2 className="text-lg font-semibold text-ink">
            {t("family.createGroup")}
          </h2>
          <p className="mt-1 max-w-md text-sm text-muted">
            {t("family.noGroupPrompt")}
          </p>
          <Button
            onClick={() => {
              setGroupName("");
              setErrorMessage(null);
              setCreateGroupOpen(true);
            }}
            className="mt-6"
          >
            + {t("family.createGroup")}
          </Button>
        </Card>

        {/* Create Group Modal */}
        <Modal
          open={createGroupOpen}
          onClose={() => setCreateGroupOpen(false)}
          title={t("family.createGroup")}
        >
          <form onSubmit={handleCreateGroup} className="space-y-4">
            {errorMessage && (
              <div className="rounded-xl bg-neg/10 p-3 text-xs text-neg">
                {errorMessage}
              </div>
            )}
            <div>
              <label className="mb-1 block text-xs font-medium text-muted">
                {t("family.groupName")}
              </label>
              <Input
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                placeholder={t("family.groupNamePlaceholder")}
                required
                autoFocus
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreateGroupOpen(false)}
              >
                {t("common.cancel")}
              </Button>
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
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-ink">{overview.group.name}</h1>
            <Badge tone="brand">Family Group</Badge>
          </div>
          <p className="text-sm text-muted">{t("family.subtitle")}</p>
        </div>

        {isCallerAdminOrOwner && (
          <Button
            onClick={() => {
              setInviteEmail("");
              setInviteLimit("");
              setInviteRole("member");
              setErrorMessage(null);
              setInviteOpen(true);
            }}
            className="flex items-center gap-2"
          >
            <UserPlus size={16} /> {t("family.inviteMember")}
          </Button>
        )}
      </div>

      {/* KPI Overview Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("family.householdSpend")}
            </span>
            <div className="grid size-8 place-items-center rounded-lg bg-brand/10 text-brand">
              <TrendingUp size={16} />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-ink">
            {fmtMoney(overview.total_spent_minor, currentUser?.base_currency || "AUD")}
          </p>
          <p className="mt-1 text-xs text-muted">
            Across {activeMembersCount} active member{activeMembersCount === 1 ? "" : "s"}
          </p>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("family.activeMembers")}
            </span>
            <div className="grid size-8 place-items-center rounded-lg bg-pos/10 text-pos">
              <Users size={16} />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-ink">
            {activeMembersCount}
          </p>
          <p className="mt-1 text-xs text-muted">
            {members.length} registered total
          </p>
        </Card>

        <Card className="p-5 sm:col-span-2 lg:col-span-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("family.supervisedAccounts")}
            </span>
            <div className="grid size-8 place-items-center rounded-lg bg-amber-500/10 text-amber-500">
              <Shield size={16} />
            </div>
          </div>
          <p className="mt-2 text-2xl font-bold text-ink">
            {childMembersCount}
          </p>
          <p className="mt-1 text-xs text-muted">
            With active spending limits
          </p>
        </Card>
      </div>

      {/* Members Section */}
      <Card>
        <SectionTitle>{t("family.membersList")}</SectionTitle>

        <div className="space-y-4 pt-1">
          {members.map((m) => {
            const hasLimit = m.spending_limit_minor !== null && m.spending_limit_minor > 0;
            const spentMinor = m.spent_this_month_minor || 0;
            const limitMinor = m.spending_limit_minor || 1;
            const pct = hasLimit ? Math.min(Math.round((spentMinor / limitMinor) * 100), 100) : 0;
            const isOverLimit = hasLimit && spentMinor > limitMinor;
            const isNearLimit = hasLimit && !isOverLimit && pct >= 80;

            return (
              <div
                key={m.id}
                className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-4 transition md:flex-row md:items-center md:justify-between"
              >
                {/* Member Identity & Role */}
                <div className="flex items-center gap-3">
                  <div className="grid size-10 place-items-center rounded-xl bg-brand/10 text-sm font-bold text-brand">
                    {m.name ? m.name.charAt(0).toUpperCase() : m.email.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-ink">{m.name}</p>
                      <Badge tone={roleTone(m.role)}>
                        {t(`family.roles.${m.role}`, m.role)}
                      </Badge>
                      {!m.is_active && (
                        <Badge tone="warn">{t("family.statusInactive")}</Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted">{m.email}</p>
                  </div>
                </div>

                {/* Spending Progress Tracker */}
                <div className="flex-1 md:max-w-xs">
                  <div className="mb-1.5 flex items-center justify-between text-xs">
                    <span className="text-muted">
                      {t("family.spentThisMonth")}:{" "}
                      <b className="text-ink">
                        {fmtMoney(spentMinor, currentUser?.base_currency || "AUD")}
                      </b>
                    </span>
                    <span className="font-medium text-muted">
                      {hasLimit ? (
                        <>
                          / {fmtMoney(m.spending_limit_minor!, currentUser?.base_currency || "AUD")}
                        </>
                      ) : (
                        t("family.unlimited")
                      )}
                    </span>
                  </div>

                  {hasLimit ? (
                    <div className="space-y-1">
                      <div className="h-2 w-full overflow-hidden rounded-full bg-raised">
                        <div
                          className={`h-full rounded-full transition-all ${
                            isOverLimit
                              ? "bg-neg"
                              : isNearLimit
                              ? "bg-amber-500"
                              : "bg-brand"
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="flex items-center justify-between text-[10px]">
                        <span className={isOverLimit ? "font-semibold text-neg" : "text-muted"}>
                          {pct}% used
                        </span>
                        {isOverLimit ? (
                          <span className="font-semibold text-neg flex items-center gap-0.5">
                            <AlertCircle size={10} /> {t("family.exceeded")}
                          </span>
                        ) : (
                          <span className="text-pos">
                            {fmtMoney(
                              Math.max(0, m.spending_limit_minor! - spentMinor),
                              currentUser?.base_currency || "AUD",
                            )}{" "}
                            {t("family.remaining")}
                          </span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="text-[11px] text-muted italic">
                      {t("family.noLimit")}
                    </div>
                  )}
                </div>

                {/* Actions */}
                {isCallerAdminOrOwner && (
                  <div className="flex items-center gap-1.5 self-end md:self-center">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => openEditModal(m)}
                      title={t("family.editMember")}
                      className="px-2.5"
                    >
                      <Edit2 size={13} /> {t("common.edit")}
                    </Button>
                    {m.role !== "owner" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setRemoveMember(m)}
                        title={t("family.removeMember")}
                        className="px-2 text-neg hover:bg-neg/10"
                      >
                        <Trash2 size={13} />
                      </Button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Invite Member Modal */}
      <Modal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        title={t("family.inviteMember")}
      >
        <form onSubmit={handleInvite} className="space-y-4">
          {errorMessage && (
            <div className="rounded-xl bg-neg/10 p-3 text-xs text-neg">
              {errorMessage}
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("auth.email")}
            </label>
            <Input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder={t("family.emailPlaceholder")}
              required
              autoFocus
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("family.role")}
            </label>
            <Select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as any)}
            >
              <option value="member">{t("family.roles.member")}</option>
              <option value="admin">{t("family.roles.admin")}</option>
              <option value="child">{t("family.roles.child")}</option>
              <option value="owner">{t("family.roles.owner")}</option>
            </Select>
            <p className="mt-1 text-[11px] text-muted">
              {t(`family.roleDescriptions.${inviteRole}`)}
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("family.spendingLimit")} ({currentUser?.base_currency || "AUD"})
            </label>
            <Input
              type="number"
              step="0.01"
              min="0"
              value={inviteLimit}
              onChange={(e) => setInviteLimit(e.target.value)}
              placeholder={t("family.spendingLimitPlaceholder")}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setInviteOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={inviteMemberMutation.isPending}>
              {inviteMemberMutation.isPending ? t("common.loading") : t("family.inviteMember")}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Member Modal */}
      <Modal
        open={Boolean(editMember)}
        onClose={() => setEditMember(null)}
        title={t("family.editMember")}
      >
        <form onSubmit={handleUpdate} className="space-y-4">
          {errorMessage && (
            <div className="rounded-xl bg-neg/10 p-3 text-xs text-neg">
              {errorMessage}
            </div>
          )}

          <div>
            <p className="text-sm font-semibold text-ink">{editMember?.name}</p>
            <p className="text-xs text-muted">{editMember?.email}</p>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("family.role")}
            </label>
            <Select
              value={editRole}
              onChange={(e) => setEditRole(e.target.value as any)}
            >
              <option value="member">{t("family.roles.member")}</option>
              <option value="admin">{t("family.roles.admin")}</option>
              <option value="child">{t("family.roles.child")}</option>
              <option value="owner">{t("family.roles.owner")}</option>
            </Select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-muted">
              {t("family.spendingLimit")} ({currentUser?.base_currency || "AUD"})
            </label>
            <Input
              type="number"
              step="0.01"
              min="0"
              value={editLimit}
              onChange={(e) => setEditLimit(e.target.value)}
              placeholder={t("family.spendingLimitPlaceholder")}
            />
          </div>

          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="editIsActive"
              checked={editIsActive}
              onChange={(e) => setEditIsActive(e.target.checked)}
              className="size-4 rounded border-line text-brand focus:ring-brand"
            />
            <label htmlFor="editIsActive" className="text-xs font-medium text-ink">
              {t("family.statusActive")}
            </label>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setEditMember(null)}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={updateMemberMutation.isPending}>
              {updateMemberMutation.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Remove Confirmation Modal */}
      <Modal
        open={Boolean(removeMember)}
        onClose={() => setRemoveMember(null)}
        title={t("family.removeMember")}
      >
        <div className="space-y-4">
          <p className="text-sm text-ink">{t("family.confirmRemove")}</p>
          <div className="rounded-xl bg-raised p-3 text-xs">
            <p className="font-semibold text-ink">{removeMember?.name}</p>
            <p className="text-muted">{removeMember?.email}</p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setRemoveMember(null)}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={deleteMemberMutation.isPending}
              onClick={() => {
                if (removeMember) deleteMemberMutation.mutate(removeMember.id);
              }}
            >
              {deleteMemberMutation.isPending ? t("common.loading") : t("common.delete")}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
