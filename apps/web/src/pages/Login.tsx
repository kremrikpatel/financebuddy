import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Wallet, KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Input, Card } from "@/components/ui";
import { useAuth } from "@/stores/auth";
import { http } from "@/lib/api";

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
  const [email, setEmail] = useState("demo@financebuddy.app");
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
    <div className="grid min-h-screen place-items-center bg-surface p-4">
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="grid size-14 place-items-center rounded-2xl bg-brand text-white shadow-xl shadow-brand/30">
            <Wallet size={26} />
          </div>
          <h1 className="text-2xl font-bold">FinanceBuddy</h1>
          <p className="text-sm text-muted">{t("app.tagline")}</p>
        </div>

        <Card className="p-6">
          {mfaStep ? (
            <form onSubmit={submitMfa} className="space-y-4">
              <h2 className="text-lg font-semibold">{t("auth.mfaPrompt")}</h2>
              <Input
                value={totp}
                onChange={(e) => setTotp(e.target.value)}
                placeholder={t("auth.mfaCode")}
                inputMode="numeric"
                autoFocus
              />
              <Button className="w-full" disabled={busy}>
                {t("auth.signIn")}
              </Button>
            </form>
          ) : (
            <>
              <div className="mb-5 flex rounded-xl bg-surface p-1">
                {(["login", "register"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`flex-1 rounded-lg py-2 text-sm font-medium transition ${
                      mode === m ? "bg-raised text-ink shadow" : "text-muted"
                    }`}
                  >
                    {t(m === "login" ? "auth.signIn" : "auth.signUp")}
                  </button>
                ))}
              </div>
              <form onSubmit={submit} className="space-y-4">
                {mode === "register" && (
                  <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("auth.name")} />
                )}
                <Input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("auth.email")}
                />
                <Input
                  type="password"
                  required
                  minLength={10}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("auth.password")}
                />
                {error && error !== "mfa_required" && (
                  <p className="text-sm text-neg">{error}</p>
                )}
                <Button className="w-full" disabled={busy}>
                  {busy ? "…" : t(mode === "login" ? "auth.signIn" : "auth.signUp")}
                </Button>
              </form>
              <button
                type="button"
                className="btn-ghost mt-3 flex w-full items-center justify-center gap-1.5 text-xs text-muted hover:text-ink"
                onClick={handlePasskeyLogin}
                disabled={busy}
              >
                <KeyRound size={13} /> {t("auth.usePasskey")}
              </button>
            </>
          )}
          {error === "mfa_required" && (
            <p className="mt-3 text-center text-xs text-muted">Enter your 2FA code to continue.</p>
          )}
        </Card>
        <p className="mt-6 text-center text-xs text-muted/70">
          demo@financebuddy.app · DemoPass123!
        </p>
      </motion.div>
    </div>
  );
}
