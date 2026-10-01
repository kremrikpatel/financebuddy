import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Wallet, KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Card, Field, Notice, Segmented } from "@/components/ui";
import { useAuth } from "@/stores/auth";
import { http } from "@/lib/api";

// Demo builds (and local dev) prefill and show the seeded demo account; production builds never do.
const env = (import.meta as any).env ?? {};
const DEMO_MODE = Boolean(env.DEV) || env.VITE_DEMO_MODE === "true";
const DEMO_EMAIL = "demo@financebuddy.app";

function bufToB64(buf: ArrayBuffer | null): string {
  if (!buf) return "";
  const bytes = new Uint8Array(buf);
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s);
}

function base64ToUint8Array(b64: string): Uint8Array {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const base64 = (b64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const login = useAuth((s) => s.login);
  const register = useAuth((s) => s.register);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState(DEMO_MODE ? DEMO_EMAIL : "");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [totp, setTotp] = useState("");
  const [mfaStep, setMfaStep] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name);
      }
      navigate("/");
    } catch (err: any) {
      if (err?.message === "mfa_required") setMfaStep(true);
      else setError(err?.response?.data?.detail ?? String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function submitMfa(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password, totp);
      navigate("/");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  async function handlePasskeyLogin() {
    setBusy(true);
    setError(null);
    try {
      if (!window.PublicKeyCredential || !navigator.credentials) {
        throw new Error("WebAuthn is not supported in this browser");
      }
      const { data: start } = await http.post("/auth/passkeys/auth/start", {
        email: email || undefined,
      });
      const options = start.options || {};
      const challengeBytes = base64ToUint8Array(options.challenge);
      const allowCredentials = (options.allowCredentials || options.allow_credentials || []).map((c: any) => ({
        id: base64ToUint8Array(c.id) as unknown as BufferSource,
        type: "public-key" as const,
        transports: c.transports,
      }));

      const publicKey: PublicKeyCredentialRequestOptions = {
        challenge: challengeBytes as unknown as BufferSource,
        timeout: options.timeout || 60000,
        rpId: options.rpId || options.rp_id || window.location.hostname,
        userVerification: options.userVerification || options.user_verification || "preferred",
        ...(allowCredentials.length > 0 ? { allowCredentials } : {}),
      };

      const assertion = (await navigator.credentials.get({ publicKey })) as any;
      if (!assertion) throw new Error("Passkey authentication was cancelled");

      const authResp = assertion.response;
      const credentialPayload = {
        id: assertion.id,
        rawId: bufToB64(assertion.rawId),
        type: assertion.type,
        response: {
          clientDataJSON: bufToB64(authResp.clientDataJSON),
          authenticatorData: bufToB64(authResp.authenticatorData),
          signature: bufToB64(authResp.signature),
          userHandle: authResp.userHandle ? bufToB64(authResp.userHandle) : null,
        },
      };

      const { data: tokens } = await http.post("/auth/passkeys/auth/finish", {
        challenge_token: start.challenge_token,
        credential: credentialPayload,
      });

      if (tokens.access_token) {
        sessionStorage.setItem("fb.access", tokens.access_token);
        if (tokens.refresh_token) localStorage.setItem("fb.refresh", tokens.refresh_token);
        useAuth.setState({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
        await useAuth.getState().bootstrapProfile();
        navigate("/");
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err?.message ?? "Passkey login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-[100dvh] place-items-center bg-surface px-4 py-10 pt-safe pb-safe">
      <div className="w-full max-w-sm animate-fadeUp">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div className="grid size-12 place-items-center rounded-xl bg-brand text-brand-ink" aria-hidden>
            <Wallet size={22} />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">FinanceBuddy</h1>
          <p className="text-sm text-muted">{t("app.tagline")}</p>
        </div>

        <Card className="p-6">
          {mfaStep ? (
            <form onSubmit={submitMfa} className="space-y-4">
              <h2 className="text-lg font-semibold">{t("auth.mfaPrompt")}</h2>
              <Field label={t("auth.mfaCode")}>
                <Input
                  value={totp}
                  onChange={(e) => setTotp(e.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                />
              </Field>
              {error && <Notice tone="neg">{error}</Notice>}
              <Button type="submit" className="w-full" disabled={busy}>
                {t("auth.signIn")}
              </Button>
            </form>
          ) : (
            <>
              <Segmented
                label={t("auth.mode")}
                value={mode}
                onChange={setMode}
                className="mb-5 flex w-full [&>button]:flex-1"
                options={[
                  { value: "login" as const, label: t("auth.signIn") },
                  { value: "register" as const, label: t("auth.signUp") },
                ]}
              />
              <form onSubmit={submit} className="space-y-4">
                {mode === "register" && (
                  <Field label={t("auth.name")}>
                    <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
                  </Field>
                )}
                <Field label={t("auth.email")}>
                  <Input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    dir="ltr"
                  />
                </Field>
                <Field label={t("auth.password")} hint={mode === "register" ? t("auth.passwordHint") : undefined}>
                  <Input
                    type="password"
                    required
                    minLength={10}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                  />
                </Field>
                {error && error !== "mfa_required" && <Notice tone="neg">{error}</Notice>}
                <Button type="submit" className="w-full" disabled={busy}>
                  {busy ? t("common.loading") : t(mode === "login" ? "auth.signIn" : "auth.signUp")}
                </Button>
              </form>
              <Button variant="ghost" className="mt-2 w-full" onClick={handlePasskeyLogin} disabled={busy}>
                <KeyRound size={16} aria-hidden /> {t("auth.usePasskey")}
              </Button>
            </>
          )}
          {error === "mfa_required" && (
            <p className="mt-3 text-center text-sm text-muted">{t("auth.mfaContinue")}</p>
          )}
        </Card>
        {DEMO_MODE && (
          <p className="mt-6 text-center text-xs text-muted" data-testid="demo-credentials">
            {DEMO_EMAIL} · DemoPass123!
          </p>
        )}
      </div>
    </div>
  );
}
