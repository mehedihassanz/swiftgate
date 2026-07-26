import { useState, useEffect } from "react";
import { useUserAuth, userFetch } from "../userAuth";
import { useNavigate, Link } from "react-router-dom";
import {
  Zap, Key, Plus, Trash2, Copy, Check, LogOut, DollarSign,
  Activity, TrendingUp, ArrowRight, Loader2, AlertCircle
} from "lucide-react";

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

export default function PortalDashboardPage() {
  const { user, logout, isAuthenticated } = useUserAuth();
  const navigate = useNavigate();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [keys, setKeys] = useState<ApiKeyData[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newKeyName, setNewKeyName] = useState("default");
  const [showNewKey, setShowNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/portal/login");
      return;
    }
    loadData();
  }, [isAuthenticated]);

  const loadData = async () => {
    try {
      const [usageResp, keysResp] = await Promise.all([
        userFetch("/user/usage"),
        userFetch("/user/keys"),
      ]);
      if (usageResp.ok) setUsage(await usageResp.json());
      if (keysResp.ok) setKeys(await keysResp.json());
    } finally {
      setLoading(false);
    }
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
    } finally {
      setCreating(false);
    }
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

  return (
    <div className="min-h-screen bg-ink-50">
      {/* Top bar */}
      <header className="sticky top-0 z-10 border-b border-ink-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700">
              <Zap className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-ink-900">SwiftGate</span>
            <span className="ml-1 rounded bg-ink-100 px-1.5 py-0.5 text-xs text-ink-500">
              Portal
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-ink-600">{user?.email}</span>
            <button
              onClick={() => { logout(); navigate("/portal/login"); }}
              className="flex items-center gap-1 text-sm text-ink-500 hover:text-red-600"
            >
              <LogOut className="h-4 w-4" /> Logout
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-6 py-8">
        {/* Welcome */}
        <h1 className="mb-1 text-2xl font-bold text-ink-900">
          Welcome{user?.name ? `, ${user.name}` : ""} 👋
        </h1>
        <p className="mb-8 text-sm text-ink-500">
          Manage your API keys and track usage.
        </p>

        {/* Stats */}
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            icon={DollarSign}
            label="Credits"
            value={usage ? `$${usage.credits_remaining_usd.toFixed(2)}` : "—"}
            sub="available balance"
            color="green"
          />
          <StatCard
            icon={Activity}
            label="Total Requests"
            value={usage ? usage.total_requests.toLocaleString() : "—"}
            sub="all-time"
          />
          <StatCard
            icon={TrendingUp}
            label="Total Spend"
            value={usage ? `$${usage.total_spend_usd.toFixed(4)}` : "—"}
            sub={`${usage?.total_prompt_tokens?.toLocaleString() || 0} + ${usage?.total_completion_tokens?.toLocaleString() || 0} tokens`}
          />
        </div>

        {/* New key banner */}
        {showNewKey && (
          <div className="mb-6 rounded-xl border-2 border-green-300 bg-green-50 p-5">
            <div className="mb-2 flex items-center gap-2 font-semibold text-green-800">
              <Check className="h-5 w-5" /> Your new API key
            </div>
            <p className="mb-3 text-sm text-green-700">
              Copy this key now — you won't be able to see it again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-lg border border-green-200 bg-white px-3 py-2 font-mono text-sm text-green-900">
                {showNewKey}
              </code>
              <button
                onClick={() => copyKey(showNewKey)}
                className="rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700"
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
            <button
              onClick={() => setShowNewKey(null)}
              className="mt-3 text-sm font-medium text-green-700 hover:underline"
            >
              I've saved it — dismiss
            </button>
          </div>
        )}

        {/* API Keys */}
        <div className="rounded-xl border border-ink-200 bg-white">
          <div className="flex items-center justify-between border-b border-ink-200 px-5 py-4">
            <h2 className="flex items-center gap-2 font-semibold text-ink-900">
              <Key className="h-4 w-4 text-brand-500" /> API Keys
            </h2>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="key name"
                className="w-28 rounded-lg border border-ink-300 px-2 py-1.5 text-sm text-ink-900 focus:border-brand-500 focus:outline-none"
              />
              <button
                onClick={handleCreateKey}
                disabled={creating}
                className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                <Plus className="h-4 w-4" /> Create Key
              </button>
            </div>
          </div>

          {keys.length === 0 ? (
            <div className="p-12 text-center">
              <Key className="mx-auto mb-2 h-8 w-8 text-ink-300" />
              <p className="text-sm text-ink-500">
                No keys yet. Create your first API key to start building.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-ink-100">
              {keys.map((k) => (
                <div key={k.id} className="flex items-center justify-between px-5 py-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink-900">{k.name}</span>
                      <code className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-xs text-ink-600">
                        {k.key_prefix}
                      </code>
                      {k.is_active && (
                        <span className="flex items-center gap-1 text-xs text-green-600">
                          <span className="h-1.5 w-1.5 rounded-full bg-green-500" /> active
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-ink-400">
                      {(k.total_spend_cents / 100).toFixed(4)} USD · {k.total_requests} requests
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteKey(k.id)}
                    className="rounded-lg p-1.5 text-ink-400 hover:bg-red-50 hover:text-red-600"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quickstart */}
        <div className="mt-6 rounded-xl border border-ink-200 bg-white p-5">
          <h2 className="mb-3 font-semibold text-ink-900">Quickstart</h2>
          <p className="mb-4 text-sm text-ink-500">
            SwiftGate is OpenAI-compatible. Point any SDK at the base URL:
          </p>
          <div className="rounded-lg bg-ink-900 p-4">
            <pre className="overflow-x-auto text-sm text-green-400"><code>{`from openai import OpenAI

client = OpenAI(
    base_url="https://api.swiftgate.dev/v1",
    api_key="<your-key>",
)

response = client.chat.completions.create(
    model="auto",  # or "gpt-4o", "claude-sonnet-4", etc.
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)`}</code></pre>
          </div>
        </div>

        <div className="mt-6 text-center">
          <Link to="/login" className="text-xs text-ink-400 hover:text-ink-600">
            Admin dashboard →
          </Link>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon, label, value, sub, color
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  sub: string;
  color?: string;
}) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-5">
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
