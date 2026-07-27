import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import DashboardPage from "./pages/DashboardPage";
import PredictPage from "./pages/PredictPage";
import ComparePage from "./pages/ComparePage";
import UsagePage from "./pages/UsagePage";
import AdminPage from "./pages/AdminPage";
import ApiKeysPage from "./pages/ApiKeysPage";
import AgentsPage from "./pages/AgentsPage";
import CachePage from "./pages/CachePage";
import QualityPage from "./pages/QualityPage";
import PortalAuthPage from "./pages/PortalAuthPage";
import PortalDashboardPage from "./pages/PortalDashboardPage";
import SettingsPage from "./pages/SettingsPage";
import ModelsBrowsePage from "./pages/ModelsBrowsePage";
import ActivityPage from "./pages/ActivityPage";
import { UserAuthProvider, useUserAuth } from "./userAuth";

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user } = useUserAuth();
  if (!user?.is_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function PortalLayout() {
  const { isAuthenticated } = useUserAuth();
  if (!isAuthenticated) return <Navigate to="/portal/login" replace />;

  return (
    <div className="flex min-h-screen bg-ink-50">
      <Sidebar />
      <main className="flex-1 overflow-auto p-6">
        <Routes>
          {/* User pages */}
          <Route path="/" element={<DashboardPage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/models" element={<ModelsBrowsePage />} />
          <Route path="/predict" element={<PredictPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/keys" element={<ApiKeysPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/settings" element={<SettingsPage />} />

          {/* Admin-only pages */}
          <Route path="/quality" element={<AdminRoute><QualityPage /></AdminRoute>} />
          <Route path="/cache" element={<AdminRoute><CachePage /></AdminRoute>} />
          <Route path="/usage" element={<AdminRoute><UsagePage /></AdminRoute>} />
          <Route path="/admin" element={<AdminRoute><AdminPage /></AdminRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <UserAuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Auth pages (no sidebar) */}
          <Route path="/portal" element={<PortalDashboardPage />} />
          <Route path="/portal/login" element={<PortalAuthPage mode="login" />} />
          <Route path="/portal/signup" element={<PortalAuthPage mode="signup" />} />

          {/* Sidebar layout (all authenticated pages) */}
          <Route path="/*" element={<PortalLayout />} />
        </Routes>
      </BrowserRouter>
    </UserAuthProvider>
  );
}
