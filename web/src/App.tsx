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
import LoginPage from "./pages/LoginPage";
import PortalAuthPage from "./pages/PortalAuthPage";
import PortalDashboardPage from "./pages/PortalDashboardPage";
import { AuthProvider, useAuth } from "./auth";
import { UserAuthProvider } from "./userAuth";

function ProtectedRoutes() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex min-h-screen bg-ink-50">
      <Sidebar />
      <main className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/predict" element={<PredictPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/usage" element={<UsagePage />} />
          <Route path="/keys" element={<ApiKeysPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="/cache" element={<CachePage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <UserAuthProvider>
        <BrowserRouter>
          <Routes>
            {/* User portal (OpenRouter-style) */}
            <Route path="/portal" element={<PortalDashboardPage />} />
            <Route path="/portal/login" element={<PortalAuthPage mode="login" />} />
            <Route path="/portal/signup" element={<PortalAuthPage mode="signup" />} />

            {/* Admin dashboard */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/*" element={<ProtectedRoutes />} />
          </Routes>
        </BrowserRouter>
      </UserAuthProvider>
    </AuthProvider>
  );
}
