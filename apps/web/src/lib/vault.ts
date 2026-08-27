/**
 * Zero-knowledge vault (WebCrypto).
 *
 * Master password → PBKDF2-SHA256 (600k iters, random salt) → KEK.
 * Random DEK wrapped by KEK. Server stores only salt + wrapped DEK +
 * an independent verifier so it can gate access without ever seeing keys.
 * DEK encrypts user-authored sensitive content client-side (AES-GCM-256).
 */
import { http } from "./api";

const enc = new TextEncoder();
const dec = new TextDecoder();

const b64 = (buf: ArrayBuffer | Uint8Array) => {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s);
};
const unb64 = (s: string) =>
  Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function deriveKEK(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, [
    "deriveKey",
  ]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: salt as BufferSource, iterations: 600_000, hash: "SHA-256" },
    base,
    { name: "AES-GCM", length: 256 },
    false,
    ["wrapKey", "unwrapKey", "encrypt", "decrypt"],
  );
}

async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data as BufferSource);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface VaultMaterial {
  kek: CryptoKey;
  dek: CryptoKey;
}

let cached: VaultMaterial | null = null;

/** Derive keys locally and register/verify them against the server. */
export async function unlockVault(password: string): Promise<VaultMaterial> {
  if (cached) return cached;

  const meta = await http.get("/auth/vault").then((r) => r.data).catch(() => null);

  if (!meta || !meta.kdf_salt_hex) {
    // first-time setup: generate everything client-side
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const dek = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, [
      "encrypt",
      "decrypt",
    ]);
    const kek = await deriveKEK(password, salt);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const rawDek = await crypto.subtle.exportKey("raw", dek);
    const wrapped = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: iv as BufferSource },
      kek,
      rawDek,
    );
    const verifierInput = enc.encode("fb-vault-verifier:" + password + ":" + b64(salt));
    const verifier = await sha256Hex(verifierInput);

    await http.post("/auth/vault", {
      kdf: "pbkdf2",
      kdf_salt_hex: Array.from(salt).map((b) => b.toString(16).padStart(2, "0")).join(""),
      wrapped_dek_b64: `${b64(iv)}.${b64(wrapped)}`,
      verifier_b64: verifier,
      algo: "aes-256-gcm",
    });
    cached = { kek, dek };
    return cached;
  }

  const salt = new Uint8Array(
    (meta.kdf_salt_hex.match(/.{2}/g) ?? []).map((h: string) => parseInt(h, 16)),
  );
  const kek = await deriveKEK(password, salt);
  // verify against server-stored verifier before unwrapping
  const verifierInput = enc.encode("fb-vault-verifier:" + password + ":" + b64(salt));
  const verifier = await sha256Hex(verifierInput);
  if (meta.verifier_b64 && verifier !== meta.verifier_b64) {
    throw new Error("Vault passphrase incorrect");
  }
  const [ivB64, wrappedB64] = String(meta.wrapped_dek_b64).split(".");
  const rawDek = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: unb64(ivB64) as BufferSource },
    kek,
    unb64(wrappedB64),
  );
  const dek = await crypto.subtle.importKey("raw", rawDek, { name: "AES-GCM" }, true, [
    "encrypt",
    "decrypt",
  ]);
  cached = { kek, dek };
  return cached;
}

/** Encrypt a UTF-8 string under the unlocked DEK → urlsafe token. */
export async function sealText(text: string): Promise<string | undefined> {
  if (!cached || !text) return undefined;
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as BufferSource },
    cached.dek,
    enc.encode(text),
  );
  return `v1.${b64(iv)}.${b64(ct)}`;
}

/** Decrypt a sealed token produced by sealText. */
export async function openSealedText(token?: string | null): Promise<string | null> {
  if (!cached || !token?.startsWith("v1.")) return null;
  try {
    const [, ivB64, ctB64] = token.split(".");
    const pt = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: unb64(ivB64) as BufferSource },
      cached.dek,
      unb64(ctB64),
    );
    return dec.decode(pt);
  } catch {
    return null;
  }
}

export function lockVault() {
  cached = null;
}

export function isVaultUnlocked(): boolean {
  return cached !== null;
}
