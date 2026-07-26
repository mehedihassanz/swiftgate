import { BrowserRouter, Routes, Route } from "react-router-dom";
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

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-ink-50 p-6">
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
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
