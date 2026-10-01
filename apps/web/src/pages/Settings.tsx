import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ShieldCheck, KeyRound, Fingerprint, Lock, Cpu } from "lucide-react";
import { http } from "@/lib/api";
import { Badge, Button, Card, Input, SectionTitle, Spinner, PageHeader, Field, Notice } from "@/components/ui";
import { unlockVault, lockVault, isVaultUnlocked } from "@/lib/vault";
import { LANGUAGES } from "@/i18n";
import { cn } from "@/lib/utils";
import { useCoachContext } from "@/lib/coachTabs";

export default function SettingsPage() {
  const { t, i18n } = useTranslation();
  const user = useQuery({ queryKey: ["me"], queryFn: () => http.get("/auth/me").then((r) => r.data) });
  const vaultMeta = useQuery({
    queryKey: ["vault"],
    queryFn: () => http.get("/auth/vault").then((r) => r.data).catch(() => null),
  });

  useCoachContext({
    mfa_enabled: user.data?.mfa_enabled ?? null,
    vault_configured: Boolean(vaultMeta.data?.kdf_salt_hex),
    language: i18n.language.slice(0, 2),
  });

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader title={t("settings.title")} />

      <Card as="section">
        <SectionTitle>{t("settings.profile")}</SectionTitle>
        {!user.data ? <Spinner /> : (
          <div className="space-y-3 text-sm">
            <p className="text-ink"><b className="font-semibold">{user.data.email}</b> · {user.data.full_name}</p>
            <div className="flex flex-wrap gap-2">
              <Badge tone={user.data.mfa_enabled ? "pos" : "warn"}>
                {user.data.mfa_enabled ? t("settings.mfaOn") : t("settings.mfaOff")}
              </Badge>
              <Badge>{t("settings.baseCurrency", { currency: user.data.base_currency })}</Badge>
            </div>
            <MfaControls enabled={user.data.mfa_enabled} />
          </div>
        )}
      </Card>

      <AiDiagnosticsToggleCard />

      <Card as="section">
        <SectionTitle>{t("settings.preferences")}</SectionTitle>
        <Field label={t("common.language")} className="max-w-sm">
          <select className="input cursor-pointer pe-8" value={i18n.language.slice(0, 2)} onChange={(e) => i18n.changeLanguage(e.target.value)}>
            {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </Field>
      </Card>

      <Card as="section">
        <SectionTitle right={<Lock size={16} className="text-muted" aria-hidden />}>{t("settings.vault")}</SectionTitle>
        <VaultSetup configured={Boolean(vaultMeta.data?.kdf_salt_hex)} />
      </Card>

      <Card as="section">
        <SectionTitle right={<Fingerprint size={16} className="text-muted" aria-hidden />}>{t("settings.passkeys")}</SectionTitle>
        <PasskeyManager />
      </Card>

      <Card as="section">
        <SectionTitle>{t("settings.sessions")}</SectionTitle>
        <p className="mb-3 text-sm text-muted">{t("settings.revokeHelp")}</p>
        <Button
          variant="danger"
          size="sm"
          onClick={async () => {
            await http.delete("/auth/sessions/all");
            location.reload();
          }}
        >
          {t("settings.revokeAll")}
        </Button>
      </Card>
    </div>
  );
}

function AiDiagnosticsToggleCard() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState<boolean>(() => {
    return localStorage.getItem("fb.ai_eval_enabled") === "true";
  });

  const toggle = () => {
    const nextState = !enabled;
    setEnabled(nextState);
    localStorage.setItem("fb.ai_eval_enabled", nextState ? "true" : "false");
    // Broadcast change for other components (like AppShell sidebar)
    window.dispatchEvent(new Event("storage"));
    window.dispatchEvent(new CustomEvent("fb_ai_eval_toggle", { detail: { enabled: nextState } }));
  };

  return (
    <Card as="section">
      <SectionTitle right={<Cpu size={16} className="text-muted" aria-hidden />}>
        {t("settings.aiDiagnosticsTitle")}
      </SectionTitle>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p id="ai-diag-label" className="text-sm font-medium text-ink">{t("settings.aiDiagnosticsToggle")}</p>
          <p className="max-w-xl text-sm text-muted">{t("settings.aiDiagnosticsDesc")}</p>
        </div>
        <button
          type="button"
          onClick={toggle}
          role="switch"
          aria-checked={enabled}
          aria-labelledby="ai-diag-label"
          className={cn(
            "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border transition-colors duration-200",
            enabled ? "border-brand bg-brand" : "border-field bg-sunken",
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "pointer-events-none inline-block size-5 rounded-full bg-raised shadow transition-transform duration-200",
              enabled ? "translate-x-5 rtl:-translate-x-5" : "translate-x-0.5 rtl:-translate-x-0.5",
            )}
          />
        </button>
      </div>
    </Card>
  );
}

function MfaControls({ enabled }: { enabled: boolean }) {
  const { t } = useTranslation();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);

  if (enabled && !codes)
    return (
      <div className="flex flex-wrap items-end gap-2 pt-2">
        <Field label={t("auth.mfaCode")} className="w-40">
          <Input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
        </Field>
        <Button size="sm" variant="secondary" className="min-h-10" onClick={() => http.post("/auth/mfa/disable", { code }).then(() => location.reload())}>
          {t("settings.disableMfa")}
        </Button>
      </div>
    );
  if (codes)
    return (
      <Notice tone="pos">
        <p className="mb-2 font-medium">{t("settings.recoveryCodes")}</p>
        <div className="flex flex-wrap gap-1.5 font-mono text-xs" dir="ltr">
          {codes.map((c) => <span key={c} className="rounded bg-raised px-2 py-1">{c}</span>)}
        </div>
      </Notice>
    );
  return (
    <div className="pt-2">
      {!setup ? (
        <Button size="sm" onClick={() => http.post("/auth/mfa/setup").then((r) => setSetup(r.data))}>
          <ShieldCheck size={14} aria-hidden /> {t("settings.enableMfa")}
        </Button>
      ) : (
        <div className="space-y-3 rounded-lg border border-line p-4">
          <p className="text-sm text-muted">{t("settings.addSecret")}</p>
          <code dir="ltr" className="block break-all rounded-md bg-sunken p-2 font-mono text-xs text-ink">{setup.secret}</code>
          <code dir="ltr" className="block break-all text-xs text-muted">{setup.otpauth_uri}</code>
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t("settings.verifyCode")} className="w-40">
              <Input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
            </Field>
            <Button size="sm" className="min-h-10" onClick={() => http.post("/auth/mfa/confirm", { code }).then((r) => setCodes(r.data.recovery_codes))}>
              {t("common.confirm")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function VaultSetup({ configured }: { configured: boolean }) {
  const { t } = useTranslation();
  const [pass, setPass] = useState("");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [unlocked, setUnlocked] = useState(isVaultUnlocked());

  return (
    <div className="max-w-md space-y-3 text-sm">
      <p className="text-muted">{configured ? t("settings.vaultRegistered") : t("settings.vaultSetup")}</p>

      {configured ? (
        unlocked ? (
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone="pos">{t("settings.vaultUnlocked")}</Badge>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                lockVault();
                setUnlocked(false);
                setStatus({ ok: true, text: t("settings.vaultLockedMsg") });
              }}
            >
              {t("settings.lockVault")}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <Field label={t("settings.vaultPassphrase")}>
              <Input type="password" autoComplete="current-password" value={pass} onChange={(e) => setPass(e.target.value)} />
            </Field>
            <Button
              size="sm"
              disabled={!pass}
              onClick={async () => {
                try {
                  await unlockVault(pass);
                  setUnlocked(true);
                  setStatus({ ok: true, text: t("settings.vaultUnlockedMsg") });
                  setPass("");
                } catch (e: any) {
                  setStatus({ ok: false, text: t("settings.vaultUnlockFailed", { detail: e.message }) });
                }
              }}
            >
              {t("settings.unlockVault")}
            </Button>
          </div>
        )
      ) : (
        <div className="space-y-3">
          <Field label={t("settings.vaultPassphrase")} hint={t("settings.vaultMinLength")}>
            <Input type="password" autoComplete="new-password" value={pass} onChange={(e) => setPass(e.target.value)} />
          </Field>
          <Button
            size="sm"
            disabled={pass.length < 8}
            onClick={async () => {
              try {
                await unlockVault(pass);
                setUnlocked(true);
                setStatus({ ok: true, text: t("settings.vaultCreatedMsg") });
                setPass("");
              } catch (e: any) {
                setStatus({ ok: false, text: String(e.message) });
              }
            }}
          >
            {t("settings.createVault")}
          </Button>
        </div>
      )}
      {status && <Notice tone={status.ok ? "pos" : "warn"}>{status.text}</Notice>}
    </div>
  );
}

function PasskeyManager() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const keys = useQuery({ queryKey: ["sessions"], queryFn: () => http.get("/auth/sessions").then((r) => r.data.passkeys) });

  async function registerPasskey() {
    try {
      const { data: start } = await http.post("/auth/passkeys/register/start");
      const credential = await navigator.credentials.create({ publicKey: decodeOptions(start.options) });
      await http.post("/auth/passkeys/register/finish", {
        challenge_token: start.challenge_token,
        credential: serializeCredential(credential),
      });
      void qc.invalidateQueries({ queryKey: ["sessions"] });
    } catch (e: any) {
      alert(`Passkey registration failed: ${e.message}`);
    }
  }

  return (
    <div className="space-y-3 text-sm">
      {(keys.data ?? []).length > 0 ? (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {(keys.data ?? []).map((k: any) => (
            <li key={k.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
              <span className="flex items-center gap-2 text-ink"><KeyRound size={14} className="text-muted" aria-hidden />{k.label}</span>
              <span className="num text-muted">{k.created_at?.slice(0, 10)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">{t("settings.noPasskeys")}</p>
      )}
      <Button size="sm" variant="secondary" onClick={registerPasskey}>{t("settings.registerPasskey")}</Button>
    </div>
  );
}

// ── WebAuthn helpers ────────────────────────────────────────────────────

function bufToB64(buf: ArrayBuffer | null): string {
  if (!buf) return "";
  const bytes = new Uint8Array(buf);
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s);
}

function decodeOptions(options: any): PublicKeyCredentialCreationOptions {
  const challenge = Uint8Array.from(atob(options.challenge), (c) => c.charCodeAt(0)) as unknown as BufferSource;
  const user = { ...options.user, id: Uint8Array.from(atob(options.user.id), (c) => c.charCodeAt(0)) as unknown as BufferSource };
  return {
    challenge,
    rp: options.rp,
    user,
    pubKeyCredParams: options.pubKeyCredParams,
    timeout: options.timeout,
    authenticatorSelection: options.authenticatorSelection,
  };
}

function serializeCredential(cred: any) {
  return {
    id: cred.id,
    rawId: bufToB64(cred.rawId),
    type: cred.type,
    response: {
      attestationObject: bufToB64(cred.response.attestationObject),
      clientDataJSON: bufToB64(cred.response.clientDataJSON),
    },
  };
}
