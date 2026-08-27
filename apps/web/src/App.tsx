import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/stores/auth";
import AppShell from "@/components/AppShell";
import LoginPage from "@/pages/Login";
import DashboardPage from "@/pages/Dashboard";
import TransactionsPage from "@/pages/Transactions";
import BudgetsPage from "@/pages/Budgets";
import GoalsPage from "@/pages/Goals";
import DebtsPage from "@/pages/Debts";
import CoachPage from "@/pages/Coach";
import ConnectionsPage from "@/pages/Connections";
import SettingsPage from "@/pages/Settings";

export default function App() {
  const accessToken = useAuth((s) => s.accessToken);
  const refreshToken = useAuth((s) => s.refreshToken);
  const bootstrap = useAuth((s) => s.bootstrap);

  useEffect(() => {
    if (!accessToken && refreshToken) void bootstrap();
  }, [accessToken, refreshToken, bootstrap]);

  if (!accessToken) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="/transactions" element={<TransactionsPage />} />
        <Route path="/budgets" element={<BudgetsPage />} />
        <Route path="/goals" element={<GoalsPage />} />
        <Route path="/debts" element={<DebtsPage />} />
        <Route path="/coach" element={<CoachPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
