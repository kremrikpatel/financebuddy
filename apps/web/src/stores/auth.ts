import { create } from "zustand";
import { http } from "@/lib/api";
import { lockVault } from "@/lib/vault";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  locale: string;
  base_currency: string;
  mfa_enabled: boolean;
  vault_configured?: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  mfaChallenge: boolean;
  bootstrap: () => Promise<void>;
  login: (email: string, password: string, totp?: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  refresh: () => Promise<string>;
  logout: () => void;
  bootstrapProfile: () => Promise<void>;
}

const REFRESH_KEY = "fb.refresh";

function persist(access: string, refresh?: string | null) {
  if (access) sessionStorage.setItem("fb.access", access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  accessToken: sessionStorage.getItem("fb.access"),
  refreshToken: localStorage.getItem(REFRESH_KEY),
  mfaChallenge: false,

  async bootstrapProfile() {
    try {
      const { data } = await http.get("/auth/me");
      set({ user: data });
    } catch {
      /* offline or unauthenticated */
    }
  },

  async bootstrap() {
    const storedAccess = sessionStorage.getItem("fb.access");
    if (storedAccess) {
      set({ accessToken: storedAccess });
      try {
        await get().bootstrapProfile();
        return;
      } catch {
        /* fallthrough to refresh */
      }
    }
    const stored = get().refreshToken;
    if (!stored) return;
    try {
      await get().refresh();
    } catch {
      get().logout();
    }
  },

  async login(email, password, totp) {
    const { data } = await http.post("/auth/login", {
      email,
      password,
      totp_code: totp || undefined,
    });
    if (data.mfa_required) {
      set({ mfaChallenge: true });
      throw new Error("mfa_required");
    }
    persist(data.access_token, data.refresh_token);
    set({ accessToken: data.access_token, refreshToken: data.refresh_token, mfaChallenge: false });
    await get().bootstrapProfile();
  },

  async register(email, password, name) {
    const { data } = await http.post("/auth/register", {
      email,
      password,
      full_name: name || null,
    });
    persist(data.access_token, data.refresh_token);
    set({ accessToken: data.access_token, refreshToken: data.refresh_token });
    await get().bootstrapProfile();
  },

  async refresh() {
    const token = get().refreshToken;
    if (!token) throw new Error("no refresh token");
    const { data } = await http.post("/auth/refresh", { refresh_token: token });
    persist(data.access_token, data.refresh_token);
    set({ accessToken: data.access_token, refreshToken: data.refresh_token });
    await get().bootstrapProfile();
    return data.access_token as string;
  },

  logout() {
    const token = get().refreshToken;
    if (token) http.post("/auth/logout", { refresh_token: token }).catch(() => {});
    localStorage.removeItem(REFRESH_KEY);
    sessionStorage.removeItem("fb.access");
    lockVault();
    set({ user: null, accessToken: null, refreshToken: null, mfaChallenge: false });
  },
}));
