import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, ArrowLeftRight, Wallet, Target, Landmark,
  MessageCircle, Link2, Settings as SettingsIcon, LogOut, Sun, Moon, Bell,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/stores/auth";
import { useTheme } from "@/lib/hooks";
import { LANGUAGES } from "@/i18n";
import { cn } from "@/lib/utils";
import NotificationBell from "@/components/NotificationBell";

const items = [
  { to: "/", icon: LayoutDashboard, key: "nav.dashboard" },
  { to: "/transactions", icon: ArrowLeftRight, key: "nav.transactions" },
  { to: "/budgets", icon: Wallet, key: "nav.budgets" },
  { to: "/goals", icon: Target, key: "nav.goals" },
  { to: "/debts", icon: Landmark, key: "nav.debts" },
  { to: "/coach", icon: MessageCircle, key: "nav.chat" },
  { to: "/connections", icon: Link2, key: "nav.connections" },
];

export default function AppShell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const logout = useAuth((s) => s.logout);
  const email = useAuth((s) => s.user?.email ?? "");
  const [open, setOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-line bg-raised transition-transform lg:static lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center gap-2.5 border-b border-line px-5">
          <div className="grid size-9 place-items-center rounded-xl bg-brand text-white shadow-lg shadow-brand/30">
            <Wallet size={18} />
          </div>
          <span className="text-lg font-bold tracking-tight">FinanceBuddy</span>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {items.map(({ to, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition",
                  isActive
                    ? "bg-brand/10 text-brand"
                    : "text-muted hover:bg-surface hover:text-ink",
                )
              }
            >
              <Icon size={18} />
              {t(key)}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-1 border-t border-line p-3">
          <NavLink to="/settings" className={({ isActive }) =>
            cn("flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition",
              isActive ? "bg-brand/10 text-brand" : "text-muted hover:bg-surface hover:text-ink")}>
            <SettingsIcon size={18} />
            {t("nav.settings")}
          </NavLink>
          <button
            onClick={() => { logout(); navigate("/login"); }}
            className="flex w-full items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium text-muted transition hover:bg-neg/10 hover:text-neg"
          >
            <LogOut size={18} />
            {t("nav.logout")}
          </button>
          <p className="truncate px-3.5 pt-2 text-xs text-muted/70">{email}</p>
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setOpen(false)} />
      )}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-line bg-surface/80 px-4 backdrop-blur lg:px-8">
          <button className="btn-ghost lg:hidden" onClick={() => setOpen(true)}>☰</button>
          <div className="flex-1" />
          <LangSwitcher />
          <ThemeToggle />
          <NotificationBell />
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 p-4 lg:p-8">
          <AnimatePresence mode="wait">
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

export function ThemeToggle() {
  const { dark, toggle } = useTheme();
  return (
    <button onClick={toggle} className="btn-ghost size-10 rounded-xl" aria-label="theme">
      {dark ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  );
}

function LangSwitcher() {
  const { i18n } = useTranslation();
  return (
    <select
      value={i18n.language.slice(0, 2)}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      className="input h-10 w-auto py-0 text-xs"
      aria-label="language"
    >
      {LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.label}
        </option>
      ))}
    </select>
  );
}
