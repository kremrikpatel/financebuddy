import { useMemo } from "react";
import { create } from "zustand";

const KEY = "fb.theme";

function initialDark(): boolean {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored) return stored === "dark";
  } catch {
    /* storage blocked: fall through to OS preference */
  }
  return matchMedia("(prefers-color-scheme: dark)").matches;
}

function apply(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0b0f17" : "#f6f7f9");
}

interface ThemeState {
  dark: boolean;
  toggle: () => void;
}

/** Single source of truth for light/dark so every consumer (toggle, charts) stays in sync. */
export const useThemeStore = create<ThemeState>((set, get) => ({
  dark: initialDark(),
  toggle() {
    const dark = !get().dark;
    try {
      localStorage.setItem(KEY, dark ? "dark" : "light");
    } catch {
      /* non-persistent is fine */
    }
    apply(dark);
    set({ dark });
  },
}));

/** Call once before first render so Login and the shell both paint in the right theme. */
export function applyInitialTheme() {
  apply(useThemeStore.getState().dark);
}

/** Resolved token colours for Recharts (SVG attributes cannot read CSS variables). */
export function useChartColors() {
  const dark = useThemeStore((s) => s.dark);
  return useMemo(() => {
    const cs = getComputedStyle(document.documentElement);
    const raw = (name: string) => cs.getPropertyValue(name).trim();
    const rgb = (name: string) => `rgb(${raw(name)})`;
    return {
      dark,
      series: [1, 2, 3, 4, 5, 6].map((i) => raw(`--series-${i}`)),
      brand: rgb("--brand"),
      ink: rgb("--ink"),
      muted: rgb("--muted"),
      raised: rgb("--raised"),
      grid: raw("--grid"),
    };
  }, [dark]);
}
