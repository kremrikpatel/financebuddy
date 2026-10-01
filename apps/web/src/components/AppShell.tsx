import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  ArrowLeftRight,
  Wallet,
  Target,
  Landmark,
  MessageCircle,
  Link2,
  Users,
  Receipt,
  Cpu,
  Settings as SettingsIcon,
  LogOut,
  Sun,
  Moon,
  Menu,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/stores/auth";
import { useDialogBehavior, useTheme } from "@/lib/hooks";
import { LANGUAGES } from "@/i18n";
import { cn } from "@/lib/utils";
import { IconButton } from "@/components/ui";
import NotificationBell from "@/components/NotificationBell";
import CoachDock from "@/components/coach/CoachDock";
import { listenForCoachFrames } from "@/stores/coach";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
    isActive ? "bg-brand/10 text-brand" : "text-muted hover:bg-sunken hover:text-ink",
  );

export default function AppShell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const logout = useAuth((s) => s.logout);
  const email = useAuth((s) => s.user?.email ?? "");
  const [open, setOpen] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  useDialogBehavior(drawerRef, open, () => setOpen(false));
  const [aiEvalEnabled, setAiEvalEnabled] = useState<boolean>(() => {
    return localStorage.getItem("fb.ai_eval_enabled") === "true";
  });

  useEffect(() => {
    listenForCoachFrames();
  }, []);

  useEffect(() => {
    const handleStorage = () => {
      setAiEvalEnabled(localStorage.getItem("fb.ai_eval_enabled") === "true");
    };
    const handleCustomToggle = (e: Event) => {
      const detail = (e as CustomEvent<{ enabled?: boolean }>).detail;
      if (detail?.enabled !== undefined) setAiEvalEnabled(detail.enabled);
      else handleStorage();
    };

    window.addEventListener("storage", handleStorage);
    window.addEventListener("fb_ai_eval_toggle", handleCustomToggle);
    return () => {
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener("fb_ai_eval_toggle", handleCustomToggle);
    };
  }, []);

  const navItems = [
    { to: "/", icon: LayoutDashboard, key: "nav.dashboard" },
    { to: "/transactions", icon: ArrowLeftRight, key: "nav.transactions" },
    { to: "/budgets", icon: Wallet, key: "nav.budgets" },
    { to: "/goals", icon: Target, key: "nav.goals" },
    { to: "/debts", icon: Landmark, key: "nav.debts" },
    { to: "/coach", icon: MessageCircle, key: "nav.chat" },
    { to: "/family", icon: Users, key: "nav.family" },
    { to: "/tax", icon: Receipt, key: "nav.tax" },
    { to: "/connections", icon: Link2, key: "nav.connections" },
    ...(aiEvalEnabled ? [{ to: "/ai-eval", icon: Cpu, key: "nav.aiEval" }] : []),
  ];

  return (
    <div className="flex min-h-[100dvh]">
      <aside
        ref={drawerRef}
        aria-label={t("nav.primary")}
        className={cn(
          "fixed inset-y-0 start-0 z-40 flex w-64 flex-col border-e border-line bg-raised pt-safe pb-safe",
          "lg:sticky lg:top-0 lg:h-[100dvh]",
          // Closed drawer is not rendered on mobile: no off-canvas overflow (RTL) and no off-screen focus targets.
          open ? "max-lg:animate-fadeUp max-lg:shadow-pop" : "max-lg:hidden",
        )}
      >
        <div className="flex h-16 shrink-0 items-center gap-2.5 px-5">
          <div className="grid size-8 place-items-center rounded-lg bg-brand text-brand-ink" aria-hidden>
            <Wallet size={17} />
          </div>
          <span className="text-base font-semibold tracking-tight">FinanceBuddy</span>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
          {navItems.map(({ to, icon: Icon, key }) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)} className={navLinkClass}>
              <Icon size={18} aria-hidden />
              {t(key)}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-0.5 border-t border-line px-3 py-3">
          <NavLink to="/settings" onClick={() => setOpen(false)} className={navLinkClass}>
            <SettingsIcon size={18} aria-hidden />
            {t("nav.settings")}
          </NavLink>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="flex min-h-10 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted transition-colors hover:bg-neg/10 hover:text-neg"
          >
            <LogOut size={18} aria-hidden />
            {t("nav.logout")}
          </button>
          <p className="truncate px-3 pt-2 text-xs text-muted">{email}</p>
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-30 bg-ink/30 lg:hidden" onClick={() => setOpen(false)} aria-hidden />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-line bg-surface/85 pt-safe backdrop-blur">
          <div className="flex h-14 items-center gap-2 px-4 lg:px-8">
            <IconButton
              label={t("nav.openMenu")}
              icon={<Menu size={20} />}
              onClick={() => setOpen(true)}
              className="-ms-2 lg:hidden"
              aria-expanded={open}
            />
            <div className="flex-1" />
            <LangSwitcher />
            <ThemeToggle />
            <NotificationBell />
          </div>
        </header>

        <main
          className={cn(
            "mx-auto w-full max-w-6xl flex-1 px-4 pt-6 lg:px-8 lg:pt-8",
            location.pathname.startsWith("/coach") ? "pb-6" : "pb-28",
          )}
        >
          <div key={location.pathname} className="animate-fadeUp">
            <Outlet />
          </div>
        </main>
      </div>

      <CoachDock />
    </div>
  );
}

export function ThemeToggle() {
  const { t } = useTranslation();
  const { dark, toggle } = useTheme();
  return (
    <IconButton
      label={dark ? t("common.useLight") : t("common.useDark")}
      icon={dark ? <Sun size={18} /> : <Moon size={18} />}
      onClick={toggle}
    />
  );
}

function LangSwitcher() {
  const { t, i18n } = useTranslation();
  return (
    <select
      value={i18n.language.slice(0, 2)}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      className="input h-10 w-auto min-w-0 cursor-pointer py-0 pe-8 text-sm"
      aria-label={t("common.language")}
    >
      {LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.label}
        </option>
      ))}
    </select>
  );
}
