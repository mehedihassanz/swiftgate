import { useState, useEffect } from "react";
import { Cpu, Search, Loader2 } from "lucide-react";
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

  useEffect(() => {
    authFetch("/v1/models")
      .then((r) => r.json())
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

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <Cpu className="h-6 w-6 text-brand-500" />
          Models
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Browse {models.length} models across all providers. Find the right model for your use case.
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
        <div className="flex gap-1">
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
            <div key={m.model_id} className="rounded-xl border border-ink-200 bg-white p-4 hover:border-brand-300 hover:shadow-sm transition">
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

              {/* Pricing */}
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

              {/* Badges */}
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
            </div>
          ))}
        </div>
      )}

      {filtered.length === 0 && !loading && (
        <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
          <Cpu className="mx-auto mb-2 h-8 w-8 text-ink-300" />
          <p className="text-sm text-ink-500">No models match your search.</p>
        </div>
      )}
    </div>
  );
}
