import { useState } from "react";
import { GitCompare, Loader2, Star } from "lucide-react";
import { authFetch } from "../auth";

interface ComparisonModel {
  model_id: string;
  display_name: string;
  provider: string;
  category: string;
  input_tokens: number;
  estimated_output_tokens: number;
  total_cost_cents: number;
  total_cost_usd: number;
  quality_score: number;
  speed_score: number;
  pareto_optimal: boolean;
}

const SAMPLE_PROMPTS: Record<string, string> = {
  chat: "Explain how authentication works in web applications.",
  code: "Write a Python function that merges two sorted lists efficiently.",
  reasoning: "Analyze the trade-offs between microservices and monolithic architecture.",
};

type OptimizeFor = "cheapest" | "fastest" | "balanced" | "quality";

export default function ComparePage() {
  const [prompt, setPrompt] = useState(SAMPLE_PROMPTS.code);
  const [optimizeFor, setOptimizeFor] = useState<OptimizeFor>("balanced");
  const [results, setResults] = useState<ComparisonModel[]>([]);
  const [loading, setLoading] = useState(false);

  const compare = async () => {
    setLoading(true);
    try {
      const resp = await authFetch("/v1/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{ role: "user", content: prompt }],
          max_tokens: 1000,
          optimize_for: optimizeFor,
        }),
      });
      const data = await resp.json();
      setResults(data.models || []);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <GitCompare className="h-6 w-6 text-brand-500" />
          Compare Models
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          See which model gives you the best quality per dollar. ★ = Pareto optimal (not beaten on both cost AND quality).
        </p>
      </div>

      {/* Controls */}
      <div className="mb-4 flex gap-3">
        <select
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="flex-1 rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm"
        >
          {Object.entries(SAMPLE_PROMPTS).map(([key, val]) => (
            <option key={key} value={val}>
              {key.toUpperCase()} — {val.slice(0, 60)}...
            </option>
          ))}
        </select>
        <select
          value={optimizeFor}
          onChange={(e) => setOptimizeFor(e.target.value as OptimizeFor)}
          className="w-40 rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm"
        >
          <option value="balanced">Balanced</option>
          <option value="cheapest">Cheapest</option>
          <option value="fastest">Fastest</option>
          <option value="quality">Highest Quality</option>
        </select>
        <button
          onClick={compare}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitCompare className="h-4 w-4" />}
          Compare
        </button>
      </div>

      {/* Results table */}
      {results.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-ink-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-200 bg-ink-50">
              <tr className="text-left text-xs font-medium text-ink-500">
                <th className="px-4 py-3"></th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-right">Quality</th>
                <th className="px-4 py-3 text-right">Speed</th>
                <th className="px-4 py-3 text-right">Tokens</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {results.map((m) => (
                <tr
                  key={m.model_id}
                  className={m.pareto_optimal ? "bg-green-50/50" : "hover:bg-ink-50"}
                >
                  <td className="px-4 py-3 text-center">
                    {m.pareto_optimal && <Star className="h-4 w-4 fill-green-500 text-green-500" />}
                  </td>
                  <td className="px-4 py-3 font-medium text-ink-900">{m.display_name}</td>
                  <td className="px-4 py-3 text-ink-500">{m.provider}</td>
                  <td className="px-4 py-3 text-right font-mono text-ink-700">
                    ${m.total_cost_usd.toFixed(6)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span
                      className={`font-medium ${
                        m.quality_score >= 8.5
                          ? "text-green-600"
                          : m.quality_score >= 7.5
                          ? "text-ink-700"
                          : "text-ink-400"
                      }`}
                    >
                      {m.quality_score.toFixed(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-ink-500">{m.speed_score.toFixed(0)}</td>
                  <td className="px-4 py-3 text-right text-xs text-ink-400">
                    {m.input_tokens}→{m.estimated_output_tokens}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {results.length > 0 && (
        <p className="mt-3 text-xs text-ink-400">
          {results.filter((m) => m.pareto_optimal).length} of {results.length} models are Pareto optimal (★). These are the
          best value — no other model is both cheaper AND higher quality.
        </p>
      )}
    </div>
  );
}
