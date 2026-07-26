import { useState, useEffect } from "react";
import { Database, Trash2, Loader2, TrendingDown, Zap, Clock } from "lucide-react";
import { authFetch } from "../auth";

interface CacheStats {
  total_entries: number;
  active_entries: number;
  expired_entries: number;
  total_hits: number;
  estimated_hit_rate: number;
  total_saved_cents: number;
  total_saved_usd: number;
}

export default function CachePage() {
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [invalidating, setInvalidating] = useState(false);
  const [modelFilter, setModelFilter] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const resp = await authFetch("/v1/cache/stats");
      const data = await resp.json();
      setStats(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  const invalidate = async (expiredOnly: boolean = false) => {
    setInvalidating(true);
    try {
      const url = expiredOnly
        ? "/v1/cache/expired"
        : modelFilter
        ? `/v1/cache?model_id=${encodeURIComponent(modelFilter)}`
        : "/v1/cache";
      await authFetch(url, { method: "DELETE" });
      await load();
    } finally {
      setInvalidating(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <Database className="h-6 w-6 text-brand-500" />
          Semantic Cache
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Cross-provider response caching. Saves 20-40% on repeat queries with zero provider cost.
        </p>
      </div>

      {/* Stats Cards */}
      {loading ? (
        <div className="flex items-center gap-2 text-ink-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : stats ? (
        <>
          <div className="grid grid-cols-4 gap-4">
            <StatCard
              icon={<Zap className="h-4 w-4 text-amber-500" />}
              label="Cache Hits"
              value={stats.total_hits.toLocaleString()}
              sub={`${(stats.estimated_hit_rate * 100).toFixed(1)}% hit rate`}
            />
            <StatCard
              icon={<TrendingDown className="h-4 w-4 text-green-500" />}
              label="Cost Saved"
              value={`$${stats.total_saved_usd.toFixed(4)}`}
              sub={`${stats.total_saved_cents.toLocaleString()} cents`}
            />
            <StatCard
              icon={<Database className="h-4 w-4 text-brand-500" />}
              label="Active Entries"
              value={stats.active_entries.toLocaleString()}
              sub={`${stats.total_entries} total`}
            />
            <StatCard
              icon={<Clock className="h-4 w-4 text-ink-400" />}
              label="Expired"
              value={stats.expired_entries.toLocaleString()}
              sub="Awaiting cleanup"
            />
          </div>

          {/* Actions */}
          <div className="mt-6 rounded-xl border border-ink-200 bg-white p-4">
            <h3 className="mb-3 text-sm font-semibold text-ink-700">Cache Management</h3>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="text"
                placeholder="Filter by model ID (optional)"
                value={modelFilter}
                onChange={(e) => setModelFilter(e.target.value)}
                className="flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm"
              />
              <button
                onClick={() => invalidate(false)}
                disabled={invalidating}
                className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4" />
                {invalidating ? "Working..." : "Invalidate"}
              </button>
              <button
                onClick={() => invalidate(true)}
                disabled={invalidating}
                className="flex items-center gap-1.5 rounded-lg border border-ink-200 bg-ink-50 px-4 py-2 text-sm font-medium text-ink-600 hover:bg-ink-100 disabled:opacity-50"
              >
                <Clock className="h-4 w-4" />
                Cleanup Expired
              </button>
            </div>
          </div>

          {/* Info */}
          <div className="mt-4 rounded-lg bg-brand-50 p-4 text-xs text-brand-700">
            <p className="font-semibold">How semantic caching works</p>
            <ul className="mt-1 space-y-0.5">
              <li>• <b>Exact match</b>: SHA-256 hash of normalized prompt — zero false positives</li>
              <li>• <b>Semantic match</b>: Jaccard token similarity ≥ 0.85 — catches reworded queries</li>
              <li>• <b>Privacy-scoped</b>: Cache entries are per-API-key by default. Shared mode is opt-in.</li>
              <li>• <b>TTL by task type</b>: Code (7d), Chat (24h), Reasoning (12h), Embeddings (30d)</li>
              <li>• Pass <code className="rounded bg-white px-1 font-mono">"cache": false</code> in request body to bypass</li>
            </ul>
          </div>
        </>
      ) : (
        <p className="text-sm text-ink-400">Failed to load cache stats.</p>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4">
      <div className="flex items-center gap-1.5 text-xs font-medium text-ink-400">
        {icon}
        {label}
      </div>
      <p className="mt-1.5 font-mono text-xl font-bold text-ink-900">{value}</p>
      <p className="text-xs text-ink-400">{sub}</p>
    </div>
  );
}
