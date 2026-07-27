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
import { UserAuthProvider, useUserAuth } from "./userAuth";

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user } = useUserAuth();
  if (!user?.is_admin) return <Navigate to="/portal" replace />;
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
          <Route path="/" element={<DashboardPage />} />
          <Route path="/predict" element={<PredictPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="/cache" element={<CachePage />} />
          <Route path="/usage" element={<UsagePage />} />
          <Route path="/keys" element={<ApiKeysPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <AdminPage />
              </AdminRoute>
            }
          />
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
          {/* User portal — the ONLY login entry point */}
          <Route path="/portal" element={<PortalDashboardPage />} />
          <Route path="/portal/login" element={<PortalAuthPage mode="login" />} />
          <Route path="/portal/signup" element={<PortalAuthPage mode="signup" />} />

          {/* Admin dashboard (same auth, admin-only routes gated) */}
          <Route path="/*" element={<PortalLayout />} />
        </Routes>
      </BrowserRouter>
    </UserAuthProvider>
  );
}
