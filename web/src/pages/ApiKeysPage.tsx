import { useState, useEffect } from "react";
import { Key, Plus, Trash2, Copy, Check, Loader2, DollarSign } from "lucide-react";

interface ApiKey {
  id: number;
  key_prefix: string;
  name: string;
  user_email: string | null;
  monthly_budget_cents: number | null;
  is_active: boolean;
  total_spend_cents: number;
  total_requests: number;
  created_at: string | null;
  last_used: string | null;
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [form, setForm] = useState({ name: "", monthly_budget_cents: "" });

  const load = async () => {
    setLoading(true);
    try {
      const resp = await fetch("/v1/keys");
      const data = await resp.json();
      setKeys(data.keys || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    const resp = await fetch("/v1/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: form.name || "default",
        monthly_budget_cents: form.monthly_budget_cents ? Number(form.monthly_budget_cents) : undefined,
      }),
    });
    const data = await resp.json();
    if (data.key) {
      setNewKey(data.key);
      setCopied(false);
      setForm({ name: "", monthly_budget_cents: "" });
      setShowCreate(false);
      load();
    }
  };

  const del = async (id: number) => {
    if (!confirm("Delete this API key? This cannot be undone.")) return;
    await fetch(`/v1/keys/${id}`, { method: "DELETE" });
    load();
  };

  const copyKey = () => {
    if (newKey) {
      navigator.clipboard.writeText(newKey);
      setCopied(true);
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
            <Key className="h-6 w-6 text-brand-500" />
            API Keys
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            Create and manage API keys for authentication. Keys are shown only once at creation.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" /> New Key
        </button>
      </div>

      {/* New key created — show once */}
      {newKey && (
        <div className="mb-4 rounded-xl border border-green-200 bg-green-50 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-green-900">✓ Key Created — Copy it now!</p>
              <p className="mt-1 font-mono text-sm text-green-700">{newKey}</p>
            </div>
            <button
              onClick={copyKey}
              className="flex items-center gap-1.5 rounded-lg border border-green-300 bg-white px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-100"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <button onClick={() => setNewKey(null)} className="mt-2 text-xs text-green-600 underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="mb-4 rounded-xl border border-ink-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-ink-700">Create New API Key</h3>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Key name (e.g. 'production')"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
            <input
              type="number"
              placeholder="Monthly budget (cents)"
              value={form.monthly_budget_cents}
              onChange={(e) => setForm({ ...form, monthly_budget_cents: e.target.value })}
              className="w-48 rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
            <button
              onClick={create}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              Create
            </button>
          </div>
        </div>
      )}

      {/* Keys list */}
      {loading ? (
        <div className="flex items-center gap-2 text-ink-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : keys.length === 0 ? (
        <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
          <Key className="mx-auto mb-2 h-8 w-8 text-ink-300" />
          <p className="text-sm text-ink-400">No API keys yet. Create one to get started.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-ink-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-200 bg-ink-50 text-left text-xs font-medium text-ink-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3 text-right">Requests</th>
                <th className="px-4 py-3 text-right">Spend</th>
                <th className="px-4 py-3 text-right">Budget</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {keys.map((k) => (
                <tr key={k.id} className="hover:bg-ink-50">
                  <td className="px-4 py-3 font-medium text-ink-900">{k.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-ink-500">{k.key_prefix}</td>
                  <td className="px-4 py-3 text-right text-ink-600">{k.total_requests}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-ink-600">
                    ${(k.total_spend_cents / 10000).toFixed(4)}
                  </td>
                  <td className="px-4 py-3 text-right text-xs text-ink-500">
                    {k.monthly_budget_cents ? `$${(k.monthly_budget_cents / 10000).toFixed(2)}` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                      k.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                    }`}>
                      {k.is_active ? "Active" : "Revoked"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => del(k.id)} className="text-ink-400 hover:text-red-500">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Usage note */}
      <div className="mt-4 rounded-lg bg-brand-50 p-4 text-xs text-brand-700">
        <p className="font-semibold">How to use your API key:</p>
        <p className="mt-1">Pass it as a Bearer token in the Authorization header:</p>
        <pre className="mt-1 rounded bg-white p-2 font-mono text-xs">
{`curl https://api.swiftgate.dev/v1/chat/completions \\
  -H "Authorization: Bearer sg-..." \\
  -H "Content-Type: application/json" \\
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Hello"}]}'`}
        </pre>
      </div>
    </div>
  );
}
