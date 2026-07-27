import { useState, useEffect } from "react";
import { Activity, Loader2 } from "lucide-react";
import { userFetch } from "../userAuth";

interface RecentEntry {
  id: number;
  model_id: string;
  provider_name: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number;
  created_at: string;
}

export default function ActivityPage() {
  const [records, setRecords] = useState<RecentEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    userFetch("/user/usage/recent?limit=100")
      .then((r) => r.json())
      .then((d) => setRecords(d.records || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <Activity className="h-6 w-6 text-brand-500" />
          Activity
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Your recent API requests across all keys.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-ink-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : records.length === 0 ? (
        <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
          <Activity className="mx-auto mb-2 h-8 w-8 text-ink-300" />
          <p className="text-sm text-ink-500">No activity yet. Start making API requests to see usage here.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-ink-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-200 bg-ink-50 text-left text-xs font-medium text-ink-500">
              <tr>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3 text-right">Tokens (in/out)</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-right">Latency</th>
                <th className="px-4 py-3 text-right">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {records.map((r) => (
                <tr key={r.id} className="hover:bg-ink-50">
                  <td className="px-4 py-3 font-mono text-xs font-medium text-ink-900">{r.model_id}</td>
                  <td className="px-4 py-3 text-xs text-ink-500">{r.provider_name || "—"}</td>
                  <td className="px-4 py-3 text-right text-xs text-ink-600">
                    {r.prompt_tokens.toLocaleString()} → {r.completion_tokens.toLocaleString()}
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
  );
}
