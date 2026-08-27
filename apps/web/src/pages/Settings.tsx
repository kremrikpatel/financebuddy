import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ShieldCheck, KeyRound, Fingerprint, Lock } from "lucide-react";
import { http } from "@/lib/api";
import { Badge, Button, Card, Input, SectionTitle, Spinner } from "@/components/ui";
import { unlockVault, lockVault, isVaultUnlocked } from "@/lib/vault";
import { LANGUAGES } from "@/i18n";

export default function SettingsPage() {
  const { t, i18n } = useTranslation();
  const user = useQuery({ queryKey: ["me"], queryFn: () => http.get("/auth/me").then((r) => r.data) });
  const vaultMeta = useQuery({
    queryKey: ["vault"],
    queryFn: () => http.get("/auth/vault").then((r) => r.data).catch(() => null),
  });

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">{t("settings.title")}</h1>

      <Card>
        <SectionTitle>Profile</SectionTitle>
        {!user.data ? <Spinner /> : (
          <div className="space-y-3 text-sm">
            <p><b>{user.data.email}</b> · {user.data.full_name}</p>
            <div className="flex flex-wrap gap-2">
              <Badge tone={user.data.mfa_enabled ? "pos" : "warn"}>
                2FA {user.data.mfa_enabled ? "enabled" : "disabled"}
              </Badge>
              <Badge tone="neutral">base currency {user.data.base_currency}</Badge>
            </div>
            <MfaControls enabled={user.data.mfa_enabled} />
          </div>
        )}
      </Card>

      <Card>
        <SectionTitle>Preferences</SectionTitle>
        <div className="grid max-w-md gap-4 text-sm">
          <label className="flex flex-col gap-1.5">
            <span className="text-muted">{t("common.language")}</span>
            <select className="input" value={i18n.language.slice(0, 2)} onChange={(e) => i18n.changeLanguage(e.target.value)}>
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </label>
        </div>
      </Card>

      <Card>
        <SectionTitle right={<Lock size={14} className="text-brand" />}>{t("settings.vault")}</SectionTitle>
        <VaultSetup configured={Boolean(vaultMeta.data?.kdf_salt_hex)} />
      </Card>

      <Card>
        <SectionTitle right={<Fingerprint size={14} className="text-brand" />}>{t("settings.passkeys")}</SectionTitle>
        <PasskeyManager />
      </Card>

      <Card>
        <SectionTitle>{t("settings.sessions")}</SectionTitle>
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

function MfaControls({ enabled }: { enabled: boolean }) {
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);

  if (enabled && !codes)
    return (
      <div className="flex items-center gap-2 pt-2">
        <Input className="max-w-40" placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
        <Button size="sm" variant="outline" onClick={() => http.post("/auth/mfa/disable", { code }).then(() => location.reload())}>
          Disable 2FA
        </Button>
      </div>
    );
  if (codes)
    return (
      <div className="rounded-xl bg-pos/10 p-3">
        <p className="mb-2 text-sm font-medium text-pos">Recovery codes (store safely):</p>
        <div className="flex flex-wrap gap-1.5 font-mono text-xs">{codes.map((c) => <span key={c} className="rounded bg-raised px-2 py-1">{c}</span>)}</div>
      </div>
    );
  return (
    <div className="pt-2">
      {!setup ? (
        <Button size="sm" onClick={() => http.post("/auth/mfa/setup").then((r) => setSetup(r.data))}>
          <ShieldCheck size={14} /> Enable 2FA
        </Button>
      ) : (
        <div className="space-y-3 rounded-xl border border-line p-3">
          <p className="text-xs text-muted">Add this secret to your authenticator:</p>
          <code className="block break-all rounded-lg bg-surface p-2 font-mono text-xs">{setup.secret}</code>
          <code className="block break-all text-[10px] text-muted">{setup.otpauth_uri}</code>
          <div className="flex gap-2">
            <Input className="max-w-40" placeholder="Verify code" value={code} onChange={(e) => setCode(e.target.value)} />
            <Button size="sm" onClick={() => http.post("/auth/mfa/confirm", { code }).then((r) => setCodes(r.data.recovery_codes))}>
              Confirm
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
  const [status, setStatus] = useState<string | null>(null);
  const [unlocked, setUnlocked] = useState(isVaultUnlocked());

  return (
    <div className="max-w-md space-y-3 text-sm">
      <p className="text-muted">
        {configured
          ? "Your vault is registered on the server — sensitive user fields and notes are end-to-end encrypted."
          : t("settings.vaultSetup")}
      </p>

      {configured ? (
        unlocked ? (
          <div className="flex items-center gap-3">
            <Badge tone="pos">✓ Vault unlocked for this session</Badge>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                lockVault();
                setUnlocked(false);
                setStatus("Vault locked.");
              }}
            >
              Lock vault
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            <Input
              type="password"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              placeholder="Enter passphrase to unlock"
            />
            <Button
              size="sm"
              disabled={!pass}
              onClick={async () => {
                try {
                  await unlockVault(pass);
                  setUnlocked(true);
                  setStatus("✓ Vault unlocked successfully");
                  setPass("");
                } catch (e: any) {
                  setStatus(`Failed to unlock: ${e.message}`);
                }
              }}
            >
              Unlock vault
            </Button>
          </div>
        )
      ) : (
        <div className="space-y-3">
          <Input
            type="password"
            value={pass}
            onChange={(e) => setPass(e.target.value)}
            placeholder="Vault passphrase (min 8 chars)"
          />
          <Button
            size="sm"
            disabled={pass.length < 8}
            onClick={async () => {
              try {
                await unlockVault(pass);
                setUnlocked(true);
                setStatus("✓ Vault created and initialized on this device");
                setPass("");
              } catch (e: any) {
                setStatus(String(e.message));
              }
            }}
          >
            Create vault
          </Button>
        </div>
      )}
      {status && <Badge tone={status.startsWith("✓") ? "pos" : "warn"}>{status}</Badge>}
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
        <ul className="space-y-2">
          {(keys.data ?? []).map((k: any) => (
            <li key={k.id} className="flex items-center justify-between rounded-xl border border-line px-3 py-2">
              <span><KeyRound size={13} className="mr-1.5 inline text-brand" />{k.label}</span>
              <span className="text-xs text-muted">{k.created_at?.slice(0, 10)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted">No passkeys registered.</p>
      )}
      <Button size="sm" variant="outline" onClick={registerPasskey}>{t("settings.registerPasskey")}</Button>
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
