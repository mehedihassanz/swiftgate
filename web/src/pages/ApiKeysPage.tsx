import { useState, useEffect } from "react";
import { Key, Plus, Trash2, Copy, Check, Loader2, Edit3, X, Save } from "lucide-react";
import { userFetch } from "../userAuth";

interface ApiKey {
  id: number;
  key_prefix: string;
  name: string;
  is_active: boolean;
  total_spend_cents: number;
  total_requests: number;
  monthly_budget_cents: number | null;
  per_request_limit_cents: number | null;
  created_at: string;
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "",
    monthly_budget_cents: "",
    per_request_limit_cents: "",
  });
  const [editForm, setEditForm] = useState({ name: "", monthly_budget_cents: "", per_request_limit_cents: "" });

  const load = async () => {
    setLoading(true);
    try {
      const resp = await userFetch("/user/keys");
      const data = await resp.json();
      setKeys(data || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    const resp = await userFetch("/user/keys", {
      method: "POST",
      body: JSON.stringify({
        name: form.name || "default",
        monthly_budget_cents: form.monthly_budget_cents ? Number(form.monthly_budget_cents) : undefined,
        per_request_limit_cents: form.per_request_limit_cents ? Number(form.per_request_limit_cents) : undefined,
      }),
    });
    const data = await resp.json();
    if (data.full_key) {
      setNewKey(data.full_key);
      setCopied(false);
      setForm({ name: "", monthly_budget_cents: "", per_request_limit_cents: "" });
      setShowCreate(false);
      load();
    }
  };

  const del = async (id: number) => {
    if (!confirm("Delete this API key? This cannot be undone.")) return;
    await userFetch(`/user/keys/${id}`, { method: "DELETE" });
    load();
  };

  const startEdit = (k: ApiKey) => {
    setEditing(k.id);
    setEditForm({
      name: k.name,
      monthly_budget_cents: k.monthly_budget_cents ? String(k.monthly_budget_cents) : "",
      per_request_limit_cents: k.per_request_limit_cents ? String(k.per_request_limit_cents) : "",
    });
  };

  const saveEdit = async (id: number) => {
    await userFetch(`/user/keys/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        name: editForm.name || undefined,
        monthly_budget_cents: editForm.monthly_budget_cents ? Number(editForm.monthly_budget_cents) : null,
        per_request_limit_cents: editForm.per_request_limit_cents ? Number(editForm.per_request_limit_cents) : null,
      }),
    });
    setEditing(null);
    load();
  };

  const copyKey = () => {
    if (newKey) {
      navigator.clipboard.writeText(newKey);
      setCopied(true);
    }
  };

  const fmtUsd = (cents: number) => `$${(cents / 10000).toFixed(4)}`;

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
            <Key className="h-6 w-6 text-brand-500" />
            API Keys
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            Create and manage API keys with spend limits.
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
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-green-900">✓ Key Created — Copy it now!</p>
              <p className="mt-1 truncate font-mono text-sm text-green-700">{newKey}</p>
            </div>
            <button
              onClick={copyKey}
              className="ml-3 flex items-center gap-1.5 rounded-lg border border-green-300 bg-white px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-100"
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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <input
              type="text"
              placeholder="Key name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
            <input
              type="number"
              placeholder="Monthly budget (¢)"
              value={form.monthly_budget_cents}
              onChange={(e) => setForm({ ...form, monthly_budget_cents: e.target.value })}
              className="rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
            <input
              type="number"
              placeholder="Per-request limit (¢)"
              value={form.per_request_limit_cents}
              onChange={(e) => setForm({ ...form, per_request_limit_cents: e.target.value })}
              className="rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={create} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
              Create
            </button>
            <button onClick={() => setShowCreate(false)} className="rounded-lg border border-ink-200 px-4 py-2 text-sm text-ink-600 hover:bg-ink-50">
              Cancel
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
        <div className="space-y-3">
          {keys.map((k) => (
            <div key={k.id} className="rounded-xl border border-ink-200 bg-white p-4">
              {editing === k.id ? (
                /* Edit mode */
                <div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <input
                      type="text"
                      placeholder="Name"
                      value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      className="rounded-lg border border-ink-200 px-3 py-2 text-sm"
                    />
                    <input
                      type="number"
                      placeholder="Monthly budget (¢)"
                      value={editForm.monthly_budget_cents}
                      onChange={(e) => setEditForm({ ...editForm, monthly_budget_cents: e.target.value })}
                      className="rounded-lg border border-ink-200 px-3 py-2 text-sm"
                    />
                    <input
                      type="number"
                      placeholder="Per-request limit (¢)"
                      value={editForm.per_request_limit_cents}
                      onChange={(e) => setEditForm({ ...editForm, per_request_limit_cents: e.target.value })}
                      className="rounded-lg border border-ink-200 px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button onClick={() => saveEdit(k.id)} className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700">
                      <Save className="h-3.5 w-3.5" /> Save
                    </button>
                    <button onClick={() => setEditing(null)} className="flex items-center gap-1.5 rounded-lg border border-ink-200 px-3 py-1.5 text-xs text-ink-600 hover:bg-ink-50">
                      <X className="h-3.5 w-3.5" /> Cancel
                    </button>
                  </div>
                </div>
              ) : (
                /* Display mode */
                <div className="flex items-start justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink-900">{k.name}</span>
                      <code className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-xs text-ink-600">{k.key_prefix}</code>
                      <span className={`h-2 w-2 rounded-full ${k.is_active ? "bg-green-500" : "bg-red-400"}`} />
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-500">
                      <span className="font-mono">{fmtUsd(k.total_spend_cents)} spent</span>
                      <span>{k.total_requests} requests</span>
                      {k.monthly_budget_cents && (
                        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">
                          budget: {fmtUsd(k.monthly_budget_cents)}/mo
                        </span>
                      )}
                      {k.per_request_limit_cents && (
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">
                          limit: {fmtUsd(k.per_request_limit_cents)}/req
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <button onClick={() => startEdit(k)} className="rounded-lg p-2 text-ink-400 hover:bg-ink-50 hover:text-brand-600">
                      <Edit3 className="h-4 w-4" />
                    </button>
                    <button onClick={() => del(k.id)} className="rounded-lg p-2 text-ink-400 hover:bg-red-50 hover:text-red-600">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
