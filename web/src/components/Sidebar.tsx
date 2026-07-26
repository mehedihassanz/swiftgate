import { Zap, Gauge, BarChart3, Calculator, GitCompare, Settings, Key, Bot, Database, Trophy } from "lucide-react";
import { NavLink } from "react-router-dom";

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
  { to: "/admin", label: "Admin Panel", icon: Settings },
];

export default function Sidebar() {
  return (
    <aside className="flex w-60 flex-col border-r border-ink-200 bg-white">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700">
          <Zap className="h-5 w-5 text-white" />
        </div>
        <span className="text-base font-semibold tracking-tight text-ink-900">SwiftGate</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV.map((item) => (
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
        <div className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
          <div className="font-semibold text-ink-700">⚡ Cost Intelligence</div>
          <div className="mt-0.5">5 data flywheels · 43 endpoints</div>
        </div>
      </div>
    </aside>
  );
}
