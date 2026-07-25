import { useState, useEffect } from "react";
import { BarChart3 } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const COLORS = ["#33a8ff", "#1a87f5", "#156de1", "#1857b6", "#59c3ff", "#8ed9ff", "#bce7ff"];

interface UsageData {
  period_days: number;
  total_requests: number;
  total_cost_cents: number;
  total_cost_usd: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  per_model: {
    model: string;
    requests: number;
    cost_cents: number;
    prompt_tokens: number;
    completion_tokens: number;
    avg_latency_ms: number;
  }[];
  recent_requests: any[];
}

export default function UsagePage() {
  const [data, setData] = useState<UsageData | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/v1/usage?days=${days}`)
      .then((r) => r.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, [days]);

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
            <BarChart3 className="h-6 w-6 text-brand-500" />
            Usage Analytics
          </h1>
          <p className="mt-1 text-sm text-ink-500">Track spend, tokens, and per-model breakdowns.</p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-sm"
        >
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
        </select>
      </div>

      {loading ? (
        <div className="text-ink-400">Loading...</div>
      ) : data ? (
        <>
          {/* Summary cards */}
          <div className="mb-6 grid grid-cols-4 gap-4">
            <div className="rounded-xl border border-ink-200 bg-white p-4">
              <p className="text-xs font-medium text-ink-500">Total Spend</p>
              <p className="mt-1 text-2xl font-bold text-ink-900">${data.total_cost_usd.toFixed(4)}</p>
            </div>
            <div className="rounded-xl border border-ink-200 bg-white p-4">
              <p className="text-xs font-medium text-ink-500">Requests</p>
              <p className="mt-1 text-2xl font-bold text-ink-900">{data.total_requests}</p>
            </div>
            <div className="rounded-xl border border-ink-200 bg-white p-4">
              <p className="text-xs font-medium text-ink-500">Prompt Tokens</p>
              <p className="mt-1 text-2xl font-bold text-ink-900">
                {(data.total_prompt_tokens / 1000).toFixed(1)}K
              </p>
            </div>
            <div className="rounded-xl border border-ink-200 bg-white p-4">
              <p className="text-xs font-medium text-ink-500">Output Tokens</p>
              <p className="mt-1 text-2xl font-bold text-ink-900">
                {(data.total_completion_tokens / 1000).toFixed(1)}K
              </p>
            </div>
          </div>

          {/* Charts */}
          {data.per_model.length > 0 ? (
            <div className="grid grid-cols-2 gap-6">
              {/* Bar chart: cost per model */}
              <div className="rounded-xl border border-ink-200 bg-white p-5">
                <h3 className="mb-4 text-sm font-semibold text-ink-700">Cost by Model</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={data.per_model.map((m) => ({ name: m.model.split("-")[0], cost: m.cost_cents / 10000 }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(v: any) => `$${Number(v).toFixed(6)}`} />
                    <Bar dataKey="cost" fill="#33a8ff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Pie chart: request distribution */}
              <div className="rounded-xl border border-ink-200 bg-white p-5">
                <h3 className="mb-4 text-sm font-semibold text-ink-700">Request Distribution</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={data.per_model.map((m) => ({ name: m.model, value: m.requests }))}
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      dataKey="value"
                      label={(entry: any) => entry.name.split("-")[0]}
                    >
                      {data.per_model.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
              <p className="text-sm text-ink-400">
                No usage data yet. Start routing requests through NeuralWatt to see analytics here.
              </p>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
