import { useState, useEffect } from "react";
import { Zap, TrendingDown, Clock, DollarSign, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

interface Stats {
  total_requests: number;
  total_cost_cents: number;
  total_cost_usd: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
}

interface ModelInfo {
  model_id: string;
  display_name: string;
  category: string;
  quality_score: number;
  speed_score: number;
  pricing: { prompt_per_mtok: number; completion_per_mtok: number };
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/v1/stats").then((r) => r.json()),
      fetch("/v1/models").then((r) => r.json()),
    ])
      .then(([s, m]) => {
        setStats(s);
        setModels(m.models || []);
      })
      .finally(() => setLoading(false));
  }, []);

  const cheapestModel = [...models].sort(
    (a, b) => a.pricing.prompt_per_mtok + a.pricing.completion_per_mtok - (b.pricing.prompt_per_mtok + b.pricing.completion_per_mtok)
  )[0];

  const bestQuality = [...models].sort((a, b) => b.quality_score - a.quality_score)[0];

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <Zap className="h-6 w-6 text-brand-500" />
          NeuralWatt Dashboard
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Cost intelligence for AI APIs. See the cost before you pay it.
        </p>
      </div>

      {loading ? (
        <div className="text-ink-400">Loading...</div>
      ) : (
        <>
          {/* Stats grid */}
          <div className="mb-8 grid grid-cols-4 gap-4">
            <StatCard
              icon={DollarSign}
              label="Total Spend"
              value={stats ? `$${stats.total_cost_usd.toFixed(4)}` : "$0"}
              sub={stats ? `${stats.total_requests} requests` : ""}
            />
            <StatCard
              icon={TrendingDown}
              label="vs OpenRouter"
              value={stats ? `$${(stats.total_cost_cents * 0.045 / 10000).toFixed(4)}` : "$0"}
              sub="saved (4.5% lower margin)"
              color="green"
            />
            <StatCard
              icon={Clock}
              label="Tokens Processed"
              value={stats ? `${((stats.total_prompt_tokens + stats.total_completion_tokens) / 1000).toFixed(1)}K` : "0"}
              sub="prompt + completion"
            />
            <StatCard
              icon={Zap}
              label="Models Available"
              value={String(models.length)}
              sub="across 7 providers"
            />
          </div>

          {/* Model highlights */}
          <div className="grid grid-cols-2 gap-6">
            <div className="rounded-xl border border-ink-200 bg-white p-6">
              <h2 className="mb-4 text-sm font-semibold text-ink-700">🏆 Best Quality</h2>
              {bestQuality && (
                <div>
                  <div className="text-lg font-bold text-ink-900">{bestQuality.display_name}</div>
                  <div className="mt-1 text-sm text-ink-500">
                    Quality: {bestQuality.quality_score}/10 · {bestQuality.category}
                  </div>
                  <div className="mt-2 text-xs text-ink-400">
                    ${bestQuality.pricing.prompt_per_mtok.toFixed(2)}/Mtok in · $
                    {bestQuality.pricing.completion_per_mtok.toFixed(2)}/Mtok out
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-ink-200 bg-white p-6">
              <h2 className="mb-4 text-sm font-semibold text-ink-700">💰 Cheapest Model</h2>
              {cheapestModel && (
                <div>
                  <div className="text-lg font-bold text-ink-900">{cheapestModel.display_name}</div>
                  <div className="mt-1 text-sm text-ink-500">
                    ${cheapestModel.pricing.prompt_per_mtok.toFixed(2)}/Mtok in · $
                    {cheapestModel.pricing.completion_per_mtok.toFixed(2)}/Mtok out
                  </div>
                  <div className="mt-2 text-xs text-ink-400">
                    Quality: {cheapestModel.quality_score}/10 · {cheapestModel.category}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* CTA */}
          <div className="mt-6 rounded-xl border border-brand-200 bg-brand-50 p-6">
            <h3 className="text-base font-semibold text-brand-900">
              Try the Cost Predictor
            </h3>
            <p className="mt-1 text-sm text-brand-700">
              Enter any prompt and instantly see the exact token count and predicted cost across all models.
            </p>
            <Link
              to="/predict"
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              Predict Cost <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = "default",
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
  color?: "default" | "green";
}) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${color === "green" ? "text-green-500" : "text-brand-500"}`} />
        <span className="text-xs font-medium text-ink-500">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold text-ink-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-ink-400">{sub}</p>}
    </div>
  );
}
