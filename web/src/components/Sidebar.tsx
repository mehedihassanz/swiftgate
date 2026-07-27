import {
  Zap, Gauge, Key, Activity, Cpu, Settings, Bot,
  Calculator, GitCompare, Database, Trophy, LogOut,
} from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { useUserAuth } from "../userAuth";

const cls = (...args: (string | false | undefined)[]) => args.filter(Boolean).join(" ");

const SECTIONS = [
  {
    title: "Overview",
    items: [
      { to: "/", label: "Dashboard", icon: Gauge },
      { to: "/activity", label: "Activity", icon: Activity },
    ],
  },
  {
    title: "Build",
    items: [
      { to: "/models", label: "Models", icon: Cpu },
      { to: "/predict", label: "Cost Predictor", icon: Calculator },
      { to: "/compare", label: "Compare", icon: GitCompare },
    ],
  },
  {
    title: "Manage",
    items: [
      { to: "/keys", label: "API Keys", icon: Key },
      { to: "/agents", label: "Agents", icon: Bot },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
  {
    title: "Admin",
    adminOnly: true,
    items: [
      { to: "/quality", label: "Quality & PII", icon: Trophy },
      { to: "/cache", label: "Cache", icon: Database },
      { to: "/usage", label: "Usage Analytics", icon: Activity },
      { to: "/admin", label: "Admin Panel", icon: Settings },
    ],
  },
];

export default function Sidebar() {
  const { user, logout } = useUserAuth();
  const navigate = useNavigate();

  return (
    <aside className="flex w-60 flex-col border-r border-ink-200 bg-white">
      {/* Logo */}
      <NavLink to="/" className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700">
          <Zap className="h-5 w-5 text-white" />
        </div>
        <span className="text-base font-semibold tracking-tight text-ink-900">SwiftGate</span>
        {user?.is_admin && (
          <span className="ml-auto rounded bg-brand-100 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
            ADMIN
          </span>
        )}
      </NavLink>

      {/* Nav sections */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {SECTIONS.filter((s) => !s.adminOnly || user?.is_admin).map((section) => (
          <div key={section.title} className="mb-4">
            <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-ink-400">
              {section.title}
            </div>
            <div className="space-y-0.5">
              {section.items.map((item) => (
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
            </div>
          </div>
        ))}
      </nav>

      {/* Credits pill */}
      <div className="px-3 pb-2">
        <NavLink to="/settings" className="block rounded-lg bg-ink-50 px-3 py-2.5 hover:bg-ink-100">
          <div className="flex items-center justify-between">
            <span className="text-xs text-ink-500">Credits</span>
            <span className="rounded bg-brand-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
              +
            </span>
          </div>
          <div className="mt-0.5 text-lg font-bold text-ink-900">
            ${((user?.credits_usd ?? 0)).toFixed(2)}
          </div>
        </NavLink>
      </div>

      {/* User + logout */}
      <div className="border-t border-ink-200 p-3">
        <div className="mb-2 truncate px-3 text-xs text-ink-500">{user?.email}</div>
        <button
          onClick={() => { logout(); navigate("/portal/login"); }}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-ink-600 transition hover:bg-red-50 hover:text-red-600"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </aside>
  );
}
