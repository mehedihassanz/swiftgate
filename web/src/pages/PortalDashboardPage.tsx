import { useState, useEffect } from "react";
import { useUserAuth, userFetch } from "../userAuth";
import { useNavigate, Link } from "react-router-dom";
import {
  Zap, Key, Plus, Trash2, Copy, Check, LogOut, DollarSign,
  Activity, TrendingUp, Loader2, Clock, Cpu, ChevronRight,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

interface UsageData {
  total_requests: number;
  total_spend_usd: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  credits_remaining_usd: number;
}

interface ApiKeyData {
  id: number;
  key_prefix: string;
  name: string;
  is_active: boolean;
  created_at: string;
  total_spend_cents: number;
  total_requests: number;
  full_key?: string;
}

interface DailyEntry { date: string; cost_cents: number; requests: number; tokens: number; }
interface RecentEntry {
  id: number; model_id: string; provider_name: string | null;
  prompt_tokens: number; completion_tokens: number;
  cost_usd: number; latency_ms: number; created_at: string;
}

const BRAND = "#0A6CFF";

export default function PortalDashboardPage() {
  const { user, logout, isAuthenticated } = useUserAuth();
  const navigate = useNavigate();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [keys, setKeys] = useState<ApiKeyData[]>([]);
  const [daily, setDaily] = useState<DailyEntry[]>([]);
  const [recent, setRecent] = useState<RecentEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState("default");
  const [showNewKey, setShowNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [tab, setTab] = useState<"overview" | "keys" | "activity">("overview");

  useEffect(() => {
    if (!isAuthenticated) { navigate("/portal/login"); return; }
    loadData();
  }, [isAuthenticated]);

  const loadData = async () => {
    try {
      const [usageResp, keysResp, dailyResp, recentResp] = await Promise.all([
        userFetch("/user/usage"),
        userFetch("/user/keys"),
        userFetch("/user/usage/daily?days=30"),
        userFetch("/user/usage/recent?limit=20"),
      ]);
      if (usageResp.ok) setUsage(await usageResp.json());
      if (keysResp.ok) setKeys(await keysResp.json());
      if (dailyResp.ok) { const d = await dailyResp.json(); setDaily(d.daily || []); }
      if (recentResp.ok) { const r = await recentResp.json(); setRecent(r.records || []); }
    } finally { setLoading(false); }
  };

  const handleCreateKey = async () => {
    setCreating(true);
    try {
      const resp = await userFetch("/user/keys", {
        method: "POST",
        body: JSON.stringify({ name: newKeyName || "default" }),
      });
      if (resp.ok) {
        const newKey = await resp.json();
        setShowNewKey(newKey.full_key);
        setKeys([newKey, ...keys]);
        setNewKeyName("default");
      }
    } finally { setCreating(false); }
  };

  const handleDeleteKey = async (id: number) => {
    if (!confirm("Delete this key? Any apps using it will stop working.")) return;
    await userFetch(`/user/keys/${id}`, { method: "DELETE" });
    setKeys(keys.filter((k) => k.id !== id));
  };

  const copyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink-50">
        <Loader2 className="h-6 w-6 animate-spin text-brand-500" />
      </div>
    );
  }

  const chartData = daily.map((d) => ({
    date: d.date.slice(5),
    cost: d.cost_cents / 10000,
    requests: d.requests,
  }));

  return (
    <div className="min-h-screen bg-ink-50">
      {/* Top bar */}
      <header className="sticky top-0 z-10 border-b border-ink-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <Link to="/portal" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700">
              <Zap className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-ink-900">SwiftGate</span>
            <span className="ml-1 rounded bg-ink-100 px-1.5 py-0.5 text-xs text-ink-500">Portal</span>
          </Link>
          <div className="flex items-center gap-4">
            {usage && (
              <div className="hidden items-center gap-1.5 rounded-lg bg-green-50 px-3 py-1 sm:flex">
                <DollarSign className="h-3.5 w-3.5 text-green-600" />
                <span className="text-sm font-semibold text-green-700">
                  ${usage.credits_remaining_usd.toFixed(2)}
                </span>
              </div>
            )}
            <span className="text-sm text-ink-600">{user?.email}</span>
            <button
              onClick={() => { logout(); navigate("/portal/login"); }}
              className="flex items-center gap-1 text-sm text-ink-500 hover:text-red-600"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-6 py-8">
        {/* Welcome */}
        <h1 className="mb-1 text-2xl font-bold text-ink-900">
          Welcome{user?.name ? `, ${user.name}` : ""} 👋
        </h1>
        <p className="mb-6 text-sm text-ink-500">
          Manage your API keys, track usage, and build with 50+ AI models.
        </p>

        {/* Tabs */}
        <div className="mb-6 flex gap-1 border-b border-ink-200">
          <TabButton active={tab === "overview"} onClick={() => setTab("overview")}>Overview</TabButton>
          <TabButton active={tab === "keys"} onClick={() => setTab("keys")}>API Keys</TabButton>
          <TabButton active={tab === "activity"} onClick={() => setTab("activity")}>Activity</TabButton>
        </div>

        {/* ─── Overview Tab ─── */}
        {tab === "overview" && (
          <div className="space-y-6">
            {/* Stats */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard icon={DollarSign} label="Credits" value={usage ? `$${usage.credits_remaining_usd.toFixed(2)}` : "—"}
                sub="available" color="green" />
              <StatCard icon={Activity} label="Requests" value={usage ? usage.total_requests.toLocaleString() : "—"}
                sub="all-time" />
              <StatCard icon={TrendingUp} label="Total Spend" value={usage ? `$${usage.total_spend_usd.toFixed(4)}` : "—"}
                sub="all-time" />
              <StatCard icon={Cpu} label="Keys" value={String(keys.length)} sub="active" />
            </div>

            {/* Usage Chart */}
            <div className="rounded-xl border border-ink-200 bg-white p-5">
              <h3 className="mb-4 text-sm font-semibold text-ink-700">Spend (last 30 days)</h3>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={BRAND} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={BRAND} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                      tickFormatter={(v) => `$${v.toFixed(4)}`} />
                    <Tooltip
                      contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                      formatter={(v: any) => [`$${Number(v).toFixed(6)}`, "Cost"]}
                    />
                    <Area type="monotone" dataKey="cost" stroke={BRAND} strokeWidth={2} fill="url(#costGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-[200px] items-center justify-center text-sm text-ink-400">
                  No usage data yet. Start making API requests to see your spend chart.
                </div>
              )}
            </div>

            {/* Quickstart */}
            <div className="rounded-xl border border-ink-200 bg-white p-5">
              <h3 className="mb-3 font-semibold text-ink-900">Quickstart</h3>
              <p className="mb-4 text-sm text-ink-500">
                SwiftGate is OpenAI-compatible. Point any SDK at the base URL:
              </p>
              <div className="overflow-hidden rounded-lg bg-ink-900">
                <div className="flex items-center gap-2 border-b border-ink-700 px-4 py-2">
                  <div className="flex gap-1.5">
                    <span className="h-3 w-3 rounded-full bg-red-500" />
                    <span className="h-3 w-3 rounded-full bg-yellow-500" />
                    <span className="h-3 w-3 rounded-full bg-green-500" />
                  </div>
                  <span className="ml-2 text-xs text-ink-400">quickstart.py</span>
                </div>
                <pre className="overflow-x-auto p-4 text-sm text-green-400"><code>{`from openai import OpenAI

client = OpenAI(
    base_url="https://api.swiftgate.ai/v1",
    api_key="<your-key>",
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)`}</code></pre>
              </div>
            </div>
          </div>
        )}

        {/* ─── Keys Tab ─── */}
        {tab === "keys" && (
          <div className="space-y-4">
            {/* New key banner */}
            {showNewKey && (
              <div className="rounded-xl border-2 border-green-300 bg-green-50 p-5">
                <div className="mb-2 flex items-center gap-2 font-semibold text-green-800">
                  <Check className="h-5 w-5" /> Your new API key
                </div>
                <p className="mb-3 text-sm text-green-700">
                  Copy this key now — you won't be able to see it again.
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 overflow-x-auto rounded-lg border border-green-200 bg-white px-3 py-2 font-mono text-sm text-green-900">
                    {showNewKey}
                  </code>
                  <button onClick={() => copyKey(showNewKey)}
                    className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700">
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </button>
                </div>
                <button onClick={() => setShowNewKey(null)}
                  className="mt-3 text-sm font-medium text-green-700 hover:underline">
                  I've saved it — dismiss
                </button>
              </div>
            )}

            {/* Create key */}
            <div className="flex gap-2">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="Key name (e.g. 'production')"
                className="flex-1 rounded-lg border border-ink-300 px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none"
              />
              <button onClick={handleCreateKey} disabled={creating}
                className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
                {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                Create Key
              </button>
            </div>

            {/* Keys list */}
            {keys.length === 0 ? (
              <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
                <Key className="mx-auto mb-2 h-8 w-8 text-ink-300" />
                <p className="text-sm text-ink-500">
                  No keys yet. Create your first API key to start building.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-ink-200 bg-white">
                {keys.map((k, i) => (
                  <div key={k.id} className={`flex items-center justify-between px-5 py-4 ${i > 0 ? "border-t border-ink-100" : ""}`}>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-ink-900">{k.name}</span>
                        <code className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-xs text-ink-600">
                          {k.key_prefix}
                        </code>
                        {k.is_active ? (
                          <span className="flex items-center gap-1 text-xs text-green-600">
                            <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> active
                          </span>
                        ) : (
                          <span className="text-xs text-red-500">revoked</span>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-4 text-xs text-ink-400">
                        <span>${(k.total_spend_cents / 10000).toFixed(4)} spent</span>
                        <span>{k.total_requests} requests</span>
                        <span className="hidden sm:inline">
                          Created {new Date(k.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <button onClick={() => handleDeleteKey(k.id)}
                      className="ml-3 rounded-lg p-2 text-ink-400 hover:bg-red-50 hover:text-red-600">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ─── Activity Tab ─── */}
        {tab === "activity" && (
          <div className="rounded-xl border border-ink-200 bg-white">
            {recent.length === 0 ? (
              <div className="p-12 text-center">
                <Activity className="mx-auto mb-2 h-8 w-8 text-ink-300" />
                <p className="text-sm text-ink-500">No activity yet. Start making API requests to see usage here.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-ink-200 bg-ink-50 text-left text-xs font-medium text-ink-500">
                    <tr>
                      <th className="px-4 py-3">Model</th>
                      <th className="px-4 py-3">Provider</th>
                      <th className="px-4 py-3 text-right">Tokens</th>
                      <th className="px-4 py-3 text-right">Cost</th>
                      <th className="px-4 py-3 text-right">Latency</th>
                      <th className="px-4 py-3 text-right">When</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-100">
                    {recent.map((r) => (
                      <tr key={r.id} className="hover:bg-ink-50">
                        <td className="px-4 py-3 font-mono text-xs font-medium text-ink-900">{r.model_id}</td>
                        <td className="px-4 py-3 text-xs text-ink-500">{r.provider_name || "—"}</td>
                        <td className="px-4 py-3 text-right text-xs text-ink-600">
                          {(r.prompt_tokens + r.completion_tokens).toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-xs text-ink-700">
                          ${r.cost_usd.toFixed(6)}
                        </td>
                        <td className="px-4 py-3 text-right text-xs text-ink-500">
                          {r.latency_ms ? `${r.latency_ms}ms` : "—"}
                        </td>
                        <td className="px-4 py-3 text-right text-xs text-ink-400">
                          {r.created_at ? new Date(r.created_at).toLocaleString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {user?.is_admin && (
          <div className="mt-8 flex justify-center">
            <Link to="/" className="flex items-center gap-1 text-xs text-ink-400 hover:text-ink-600">
              Admin dashboard <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`border-b-2 px-4 py-2 text-sm font-medium transition ${
        active ? "border-brand-600 text-brand-700" : "border-transparent text-ink-500 hover:text-ink-700"
      }`}
    >
      {children}
    </button>
  );
}

function StatCard({
  icon: Icon, label, value, sub, color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string; value: string; sub: string; color?: string;
}) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4">
      <div className="mb-2 flex items-center gap-2">
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${
          color === "green" ? "bg-green-100 text-green-600" : "bg-brand-100 text-brand-600"
        }`}>
          <Icon className="h-4 w-4" />
        </div>
        <span className="text-sm text-ink-500">{label}</span>
      </div>
      <div className="text-2xl font-bold text-ink-900">{value}</div>
      <div className="mt-0.5 text-xs text-ink-400">{sub}</div>
    </div>
  );
}
