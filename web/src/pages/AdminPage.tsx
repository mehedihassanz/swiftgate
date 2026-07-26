import { useState, useEffect } from "react";
import {
  Settings, Plus, Trash2, Edit3, X, Save, Server, Cpu, Loader2, RefreshCw,
} from "lucide-react";
import { authFetch } from "../auth";

interface Provider {
  id: number;
  name: string;
  display_name: string;
  base_url: string;
  api_key_env: string;
  priority: number;
  active: boolean;
}

interface Model {
  id: number;
  model_id: string;
  display_name: string;
  provider_id: number;
  provider_name?: string;
  tokenizer: string;
  prompt_price: string;
  completion_price: string;
  cached_price: string | null;
  context_window: number;
  max_output: number;
  supports_tools: boolean;
  supports_vision: boolean;
  supports_json: boolean;
  quality_score: number;
  speed_score: number;
  is_active: boolean;
  category: string;
}

type Tab = "models" | "providers";

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("models");
  const [models, setModels] = useState<Model[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModelForm, setShowModelForm] = useState(false);
  const [showProviderForm, setShowProviderForm] = useState(false);
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [m, p] = await Promise.all([
        authFetch("/admin/models").then((r) => r.json()),
        authFetch("/admin/providers").then((r) => r.json()),
      ]);
      setModels(m.models || []);
      setProviders(p.providers || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const deleteModel = async (id: number) => {
    if (!confirm("Delete this model?")) return;
    await authFetch(`/admin/models/${id}`, { method: "DELETE" });
    loadData();
  };

  const deleteProvider = async (id: number) => {
    if (!confirm("Delete this provider? Models must be removed first.")) return;
    const resp = await authFetch(`/admin/providers/${id}`, { method: "DELETE" });
    if (!resp.ok) {
      const err = await resp.json();
      alert(err.detail || "Failed to delete");
      return;
    }
    loadData();
  };

  const reseed = async () => {
    if (!confirm("Re-seed database with default providers and models?")) return;
    await authFetch("/admin/seed", { method: "POST" });
    loadData();
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
            <Settings className="h-6 w-6 text-brand-500" />
            Admin Panel
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            Manage providers and models. {providers.length} providers · {models.length} models
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={reseed} className="flex items-center gap-1.5 rounded-lg border border-ink-200 px-3 py-1.5 text-xs font-medium text-ink-600 hover:bg-ink-50">
            <RefreshCw className="h-3.5 w-3.5" /> Re-seed
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-4 flex gap-1 border-b border-ink-200">
        <TabButton active={tab === "models"} onClick={() => setTab("models")} icon={Cpu} label={`Models (${models.length})`} />
        <TabButton active={tab === "providers"} onClick={() => setTab("providers")} icon={Server} label={`Providers (${providers.length})`} />
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-ink-400"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
      ) : tab === "models" ? (
        <div>
          <div className="mb-3 flex justify-end">
            <button onClick={() => { setEditingModel(null); setShowModelForm(true); }} className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700">
              <Plus className="h-3.5 w-3.5" /> Add Model
            </button>
          </div>
          <div className="overflow-x-auto rounded-xl border border-ink-200 bg-white">
            <table className="w-full text-sm">
              <thead className="border-b border-ink-200 bg-ink-50 text-left text-xs font-medium text-ink-500">
                <tr>
                  <th className="px-3 py-2">Model ID</th>
                  <th className="px-3 py-2">Provider</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2 text-right">Prompt $/M</th>
                  <th className="px-3 py-2 text-right">Comp $/M</th>
                  <th className="px-3 py-2 text-right">Quality</th>
                  <th className="px-3 py-2 text-right">Speed</th>
                  <th className="px-3 py-2">Active</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {models.map((m) => (
                  <tr key={m.id} className="hover:bg-ink-50">
                    <td className="px-3 py-2 font-mono text-xs font-medium text-ink-900">{m.model_id}</td>
                    <td className="px-3 py-2 text-xs text-ink-500">{m.provider_name}</td>
                    <td className="px-3 py-2">
                      <CategoryBadge category={m.category} />
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-ink-700">${(parseFloat(m.prompt_price) * 1e6).toFixed(2)}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-ink-700">${(parseFloat(m.completion_price) * 1e6).toFixed(2)}</td>
                    <td className="px-3 py-2 text-right text-xs">{m.quality_score.toFixed(1)}</td>
                    <td className="px-3 py-2 text-right text-xs text-ink-500">{m.speed_score.toFixed(0)}</td>
                    <td className="px-3 py-2">
                      <span className={`h-2 w-2 rounded-full ${m.is_active ? "bg-green-500" : "bg-ink-300"}`} />
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1">
                        <button onClick={() => { setEditingModel(m); setShowModelForm(true); }} className="text-ink-400 hover:text-brand-600">
                          <Edit3 className="h-3.5 w-3.5" />
                        </button>
                        <button onClick={() => deleteModel(m.id)} className="text-ink-400 hover:text-red-500">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div>
          <div className="mb-3 flex justify-end">
            <button onClick={() => { setEditingProvider(null); setShowProviderForm(true); }} className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700">
              <Plus className="h-3.5 w-3.5" /> Add Provider
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {providers.map((p) => (
              <div key={p.id} className="rounded-xl border border-ink-200 bg-white p-4">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-ink-900">{p.display_name}</h3>
                      <span className={`h-2 w-2 rounded-full ${p.active ? "bg-green-500" : "bg-ink-300"}`} />
                    </div>
                    <p className="text-xs text-ink-400">{p.name}</p>
                    <p className="mt-1 font-mono text-xs text-ink-500 truncate max-w-[250px]">{p.base_url}</p>
                    <p className="mt-0.5 text-xs text-ink-400">Key: {p.api_key_env}</p>
                  </div>
                  <div className="flex gap-1">
                    <button onClick={() => { setEditingProvider(p); setShowProviderForm(true); }} className="text-ink-400 hover:text-brand-600">
                      <Edit3 className="h-3.5 w-3.5" />
                    </button>
                    <button onClick={() => deleteProvider(p.id)} className="text-ink-400 hover:text-red-500">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Model Form Modal */}
      {showModelForm && (
        <ModelForm
          model={editingModel}
          providers={providers}
          onClose={() => setShowModelForm(false)}
          onSaved={() => { setShowModelForm(false); loadData(); }}
        />
      )}

      {/* Provider Form Modal */}
      {showProviderForm && (
        <ProviderForm
          provider={editingProvider}
          onClose={() => setShowProviderForm(false)}
          onSaved={() => { setShowProviderForm(false); loadData(); }}
        />
      )}
    </div>
  );
}

function TabButton({ active, onClick, icon: Icon, label }: { active: boolean; onClick: () => void; icon: React.ElementType; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-medium transition ${
        active ? "border-brand-600 text-brand-700" : "border-transparent text-ink-500 hover:text-ink-700"
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}

function CategoryBadge({ category }: { category: string }) {
  const colors: Record<string, string> = {
    frontier: "bg-purple-100 text-purple-700",
    fast: "bg-blue-100 text-blue-700",
    cheap: "bg-green-100 text-green-700",
    reasoning: "bg-orange-100 text-orange-700",
    coding: "bg-indigo-100 text-indigo-700",
    general: "bg-ink-100 text-ink-600",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${colors[category] || colors.general}`}>
      {category}
    </span>
  );
}

// ─── Model Form ───────────────────────────────────────────────────────

function ModelForm({ model, providers, onClose, onSaved }: {
  model: Model | null;
  providers: Provider[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    model_id: model?.model_id || "",
    display_name: model?.display_name || "",
    provider_id: model?.provider_id || providers[0]?.id || 1,
    tokenizer: model?.tokenizer || "tiktoken",
    prompt_price: model?.prompt_price || "0.000001",
    completion_price: model?.completion_price || "0.000003",
    cached_price: model?.cached_price || "",
    context_window: model?.context_window || 128000,
    max_output: model?.max_output || 8192,
    supports_tools: model?.supports_tools ?? true,
    supports_vision: model?.supports_vision ?? false,
    supports_json: model?.supports_json ?? true,
    quality_score: model?.quality_score || 7.5,
    speed_score: model?.speed_score || 60,
    is_active: model?.is_active ?? true,
    category: model?.category || "general",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const body = { ...form, cached_price: form.cached_price || null };
      const url = model ? `/admin/models/${model.id}` : "/admin/models";
      const method = model ? "PUT" : "POST";
      const resp = await authFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Failed");
      }
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={model ? "Edit Model" : "Add Model"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Model ID" value={form.model_id} onChange={(v) => setForm({ ...form, model_id: v })} placeholder="claude-opus-5" />
        <Field label="Display Name" value={form.display_name} onChange={(v) => setForm({ ...form, display_name: v })} />
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-500">Provider</label>
          <select value={form.provider_id} onChange={(e) => setForm({ ...form, provider_id: Number(e.target.value) })} className="w-full rounded-lg border border-ink-200 px-3 py-1.5 text-sm">
            {providers.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-500">Category</label>
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="w-full rounded-lg border border-ink-200 px-3 py-1.5 text-sm">
            {["general", "frontier", "fast", "cheap", "reasoning", "coding", "vision"].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-500">Tokenizer</label>
          <select value={form.tokenizer} onChange={(e) => setForm({ ...form, tokenizer: e.target.value })} className="w-full rounded-lg border border-ink-200 px-3 py-1.5 text-sm">
            {["tiktoken", "anthropic", "llama", "qwen", "mistral", "char4"].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <Field label="Prompt Price ($/token)" value={form.prompt_price} onChange={(v) => setForm({ ...form, prompt_price: v })} placeholder="0.000005" mono />
        <Field label="Completion Price ($/token)" value={form.completion_price} onChange={(v) => setForm({ ...form, completion_price: v })} placeholder="0.000025" mono />
        <Field label="Cached Price (optional)" value={form.cached_price} onChange={(v) => setForm({ ...form, cached_price: v })} placeholder="0.00000125" mono />
        <Field label="Context Window" type="number" value={String(form.context_window)} onChange={(v) => setForm({ ...form, context_window: Number(v) })} />
        <Field label="Max Output" type="number" value={String(form.max_output)} onChange={(v) => setForm({ ...form, max_output: Number(v) })} />
        <Field label="Quality Score (0-10)" type="number" value={String(form.quality_score)} onChange={(v) => setForm({ ...form, quality_score: Number(v) })} />
        <Field label="Speed Score (0-100)" type="number" value={String(form.speed_score)} onChange={(v) => setForm({ ...form, speed_score: Number(v) })} />
      </div>
      <div className="mt-3 flex gap-4">
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={form.supports_tools} onChange={(e) => setForm({ ...form, supports_tools: e.target.checked })} /> Tools</label>
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={form.supports_vision} onChange={(e) => setForm({ ...form, supports_vision: e.target.checked })} /> Vision</label>
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={form.supports_json} onChange={(e) => setForm({ ...form, supports_json: e.target.checked })} /> JSON</label>
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active</label>
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg border border-ink-200 px-4 py-1.5 text-sm text-ink-600 hover:bg-ink-50">Cancel</button>
        <button onClick={save} disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save
        </button>
      </div>
    </Modal>
  );
}

// ─── Provider Form ────────────────────────────────────────────────────

function ProviderForm({ provider, onClose, onSaved }: {
  provider: Provider | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: provider?.name || "",
    display_name: provider?.display_name || "",
    base_url: provider?.base_url || "",
    api_key_env: provider?.api_key_env || "",
    priority: provider?.priority || 100,
    active: provider?.active ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const url = provider ? `/admin/providers/${provider.id}` : "/admin/providers";
      const method = provider ? "PUT" : "POST";
      const resp = await authFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || "Failed");
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={provider ? "Edit Provider" : "Add Provider"} onClose={onClose}>
      <div className="space-y-3">
        <Field label="Name (slug)" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="openai" mono disabled={!!provider} />
        <Field label="Display Name" value={form.display_name} onChange={(v) => setForm({ ...form, display_name: v })} placeholder="OpenAI" />
        <Field label="Base URL" value={form.base_url} onChange={(v) => setForm({ ...form, base_url: v })} placeholder="https://api.openai.com/v1" mono />
        <Field label="API Key Env Var" value={form.api_key_env} onChange={(v) => setForm({ ...form, api_key_env: v })} placeholder="OPENAI_API_KEY" mono />
        <Field label="Priority" type="number" value={String(form.priority)} onChange={(v) => setForm({ ...form, priority: Number(v) })} />
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Active</label>
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="rounded-lg border border-ink-200 px-4 py-1.5 text-sm text-ink-600 hover:bg-ink-50">Cancel</button>
        <button onClick={save} disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save
        </button>
      </div>
    </Modal>
  );
}

// ─── Shared Components ────────────────────────────────────────────────

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink-900">{title}</h2>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-600"><X className="h-5 w-5" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text", mono, disabled }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  mono?: boolean;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-ink-500">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={`w-full rounded-lg border border-ink-200 px-3 py-1.5 text-sm ${mono ? "font-mono" : ""} ${disabled ? "bg-ink-100" : ""}`}
      />
    </div>
  );
}
