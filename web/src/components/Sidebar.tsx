import { Zap, Gauge, BarChart3, Calculator, GitCompare, Settings, Key, Bot, Database, Trophy, LogOut } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { useUserAuth } from "../userAuth";

const cls = (...args: (string | false | undefined)[]) => args.filter(Boolean).join(" ");

const NAV = [
  { to: "/", label: "Dashboard", icon: Gauge },
  { to: "/predict", label: "Cost Predictor", icon: Calculator },
  { to: "/compare", label: "Compare Models", icon: GitCompare },
  { to: "/quality", label: "Quality & PII", icon: Trophy },
  { to: "/cache", label: "Cache", icon: Database },
  { to: "/usage", label: "Usage Analytics", icon: BarChart3 },
  { to: "/keys", label: "API Keys", icon: Key },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/admin", label: "Admin Panel", icon: Settings, adminOnly: true },
];

export default function Sidebar() {
  const { user, logout } = useUserAuth();
  const navigate = useNavigate();
  const visibleNav = NAV.filter((item) => !item.adminOnly || user?.is_admin);

  return (
    <aside className="flex w-60 flex-col border-r border-ink-200 bg-white">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700">
          <Zap className="h-5 w-5 text-white" />
        </div>
        <span className="text-base font-semibold tracking-tight text-ink-900">SwiftGate</span>
        {user?.is_admin && (
          <span className="ml-auto rounded bg-brand-100 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
            ADMIN
          </span>
        )}
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {visibleNav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cls(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-ink-200 p-3">
        <div className="mb-2 truncate px-3 text-xs text-ink-500">
          {user?.email}
        </div>
        <button
          onClick={() => { logout(); navigate("/portal/login"); }}
          className="mb-2 flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-ink-600 transition hover:bg-red-50 hover:text-red-600"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </aside>
  );
}
