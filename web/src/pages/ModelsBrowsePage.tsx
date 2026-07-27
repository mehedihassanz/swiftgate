import { useState, useEffect } from "react";
import { Cpu, Search, Loader2, X, Copy, Check } from "lucide-react";
import { authFetch } from "../auth";

interface ModelInfo {
  model_id: string;
  display_name: string;
  category: string;
  context_window: number;
  supports_tools: boolean;
  supports_vision: boolean;
  supports_json: boolean;
  quality_score: number;
  speed_score: number;
  pricing: { prompt_per_mtok: number; completion_per_mtok: number; cached_per_mtok: number | null };
}

const CATEGORY_COLORS: Record<string, string> = {
  frontier: "bg-purple-100 text-purple-700",
  fast: "bg-blue-100 text-blue-700",
  cheap: "bg-green-100 text-green-700",
  reasoning: "bg-orange-100 text-orange-700",
  coding: "bg-indigo-100 text-indigo-700",
  general: "bg-ink-100 text-ink-600",
  vision: "bg-pink-100 text-pink-700",
};

export default function ModelsBrowsePage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("all");
  const [selected, setSelected] = useState<ModelInfo | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    authFetch("/v1/models")
      .then((r: any) => r.json())
      .then((d) => setModels(d.models || []))
      .finally(() => setLoading(false));
  }, []);

  const filtered = models.filter((m) => {
    const matchesSearch = !search ||
      m.display_name.toLowerCase().includes(search.toLowerCase()) ||
      m.model_id.toLowerCase().includes(search.toLowerCase());
    const matchesFilter = filter === "all" || m.category === filter;
    return matchesSearch && matchesFilter;
  });

  const categories = ["all", ...new Set(models.map((m) => m.category))];
  const copySnippet = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <Cpu className="h-6 w-6 text-brand-500" />
          Models
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Browse {models.length} models across all providers. Click any model for code snippets.
        </p>
      </div>

      {/* Search + filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search models..."
            className="w-full rounded-lg border border-ink-300 py-2 pl-10 pr-3 text-sm text-ink-900 focus:border-brand-500 focus:outline-none"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition ${
                filter === cat
                  ? "bg-brand-600 text-white"
                  : "bg-ink-100 text-ink-600 hover:bg-ink-200"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Model grid */}
      {loading ? (
        <div className="flex items-center gap-2 text-ink-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading models...
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((m) => (
            <button
              key={m.model_id}
              onClick={() => setSelected(m)}
              className="rounded-xl border border-ink-200 bg-white p-4 text-left hover:border-brand-300 hover:shadow-sm transition"
            >
              <div className="flex items-start justify-between">
                <div className="min-w-0 flex-1">
                  <h3 className="truncate font-semibold text-ink-900">{m.display_name}</h3>
                  <code className="text-xs text-ink-400">{m.model_id}</code>
                </div>
                <span className={`ml-2 flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  CATEGORY_COLORS[m.category] || CATEGORY_COLORS.general
                }`}>
                  {m.category}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-ink-400">Input</span>
                  <p className="font-mono font-medium text-ink-700">
                    ${m.pricing.prompt_per_mtok.toFixed(2)}/M
                  </p>
                </div>
                <div>
                  <span className="text-ink-400">Output</span>
                  <p className="font-mono font-medium text-ink-700">
                    ${m.pricing.completion_per_mtok.toFixed(2)}/M
                  </p>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1">
                <span className="rounded bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-500">
                  {Math.round(m.context_window / 1000)}K ctx
                </span>
                <span className="rounded bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-500">
                  ★ {m.quality_score.toFixed(1)}
                </span>
                <span className="rounded bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-500">
                  ⚡ {m.speed_score.toFixed(0)}
                </span>
                {m.supports_tools && (
                  <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[10px] text-brand-600">tools</span>
                )}
                {m.supports_vision && (
                  <span className="rounded bg-pink-50 px-1.5 py-0.5 text-[10px] text-pink-600">vision</span>
                )}
                {m.supports_json && (
                  <span className="rounded bg-green-50 px-1.5 py-0.5 text-[10px] text-green-600">json</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {filtered.length === 0 && !loading && (
        <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
          <Cpu className="mx-auto mb-2 h-8 w-8 text-ink-300" />
          <p className="text-sm text-ink-500">No models match your search.</p>
        </div>
      )}

      {/* Model detail drawer */}
      {selected && (
        <ModelDetailDrawer
          model={selected}
          onClose={() => setSelected(null)}
          onCopy={copySnippet}
          copied={copied}
        />
      )}
    </div>
  );
}

function ModelDetailDrawer({
  model, onClose, onCopy, copied,
}: {
  model: ModelInfo;
  onClose: () => void;
  onCopy: (text: string) => void;
  copied: boolean;
}) {
  const snippetPython = `from openai import OpenAI

client = OpenAI(
    base_url="https://api.swiftgate.ai/v1",
    api_key="<your-api-key>",
)

response = client.chat.completions.create(
    model="${model.model_id}",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)`;

  const snippetCurl = `curl https://api.swiftgate.ai/v1/chat/completions \\
  -H "Authorization: Bearer <your-api-key>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${model.model_id}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`;

  const [tab, setTab] = useState<"python" | "curl">("python");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-ink-900">{model.display_name}</h2>
            <code className="text-sm text-ink-400">{model.model_id}</code>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-50">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Specs */}
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Spec label="Context" value={`${Math.round(model.context_window / 1000)}K`} />
          <Spec label="Quality" value={`★ ${model.quality_score.toFixed(1)}`} />
          <Spec label="Speed" value={`⚡ ${model.speed_score.toFixed(0)}`} />
          <Spec label="Category" value={model.category} />
        </div>

        {/* Pricing */}
        <div className="mb-4 rounded-lg bg-ink-50 p-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-ink-400">Input Price</p>
              <p className="font-mono text-sm font-semibold text-ink-900">
                ${model.pricing.prompt_per_mtok.toFixed(2)}/M tokens
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-400">Output Price</p>
              <p className="font-mono text-sm font-semibold text-ink-900">
                ${model.pricing.completion_per_mtok.toFixed(2)}/M tokens
              </p>
            </div>
          </div>
        </div>

        {/* Capabilities */}
        <div className="mb-4 flex flex-wrap gap-2">
          {model.supports_tools && <Badge color="brand" label="Tool Use" />}
          {model.supports_vision && <Badge color="pink" label="Vision" />}
          {model.supports_json && <Badge color="green" label="JSON Mode" />}
        </div>

        {/* Code snippet */}
        <div className="overflow-hidden rounded-lg border border-ink-200">
          <div className="flex items-center justify-between border-b border-ink-200 bg-ink-50 px-3 py-2">
            <div className="flex gap-1">
              <button
                onClick={() => setTab("python")}
                className={`rounded px-2 py-1 text-xs font-medium ${tab === "python" ? "bg-white text-ink-900 shadow-sm" : "text-ink-500"}`}
              >
                Python
              </button>
              <button
                onClick={() => setTab("curl")}
                className={`rounded px-2 py-1 text-xs font-medium ${tab === "curl" ? "bg-white text-ink-900 shadow-sm" : "text-ink-500"}`}
              >
                cURL
              </button>
            </div>
            <button
              onClick={() => onCopy(tab === "python" ? snippetPython : snippetCurl)}
              className="flex items-center gap-1 text-xs text-ink-500 hover:text-ink-900"
            >
              {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <pre className="overflow-x-auto bg-ink-900 p-4 text-sm text-green-400">
            <code>{tab === "python" ? snippetPython : snippetCurl}</code>
          </pre>
        </div>
      </div>
    </div>
  );
}

function Spec({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink-100 p-2 text-center">
      <p className="text-[10px] uppercase tracking-wider text-ink-400">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-ink-900">{value}</p>
    </div>
  );
}

function Badge({ color, label }: { color: string; label: string }) {
  const colors: Record<string, string> = {
    brand: "bg-brand-50 text-brand-600",
    pink: "bg-pink-50 text-pink-600",
    green: "bg-green-50 text-green-600",
  };
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${colors[color] || colors.brand}`}>
      {label}
    </span>
  );
}
