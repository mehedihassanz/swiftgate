import { useState, useEffect } from "react";
import { Calculator, Loader2, TrendingDown, CheckCircle, AlertCircle } from "lucide-react";
import { authFetch } from "../auth";

interface Prediction {
  model: string;
  display_name: string;
  input_tokens: number;
  estimated_output_tokens: number;
  max_possible_output_tokens: number;
  task_type: string;
  costs: {
    input_cents: number;
    estimated_output_cents: number;
    estimated_total_cents: number;
    worst_case_cents: number;
  };
  formatted: {
    input: string;
    estimated_output: string;
    estimated_total: string;
    worst_case: string;
  };
  pricing_reference: {
    prompt_per_mtok: string;
    completion_per_mtok: string;
    margin_applied: string;
  };
  confidence: string;
  routing_suggestion?: {
    model_id: string;
    display_name: string;
    estimated_savings_pct: number;
    quality_difference: number;
    reason: string;
  };
}

interface ModelInfo {
  model_id: string;
  display_name: string;
}

const DEFAULT_PROMPT = `You are a helpful coding assistant. Write a Python function that scrapes a webpage, extracts all links, and follows robots.txt rules. Include error handling and rate limiting.`;

export default function PredictPage() {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [modelId, setModelId] = useState("claude-opus-5");
  const [maxTokens, setMaxTokens] = useState(2000);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load models on mount
  useEffect(() => {
    authFetch("/v1/models")
      .then((r) => r.json())
      .then((d) => setModels(d.models || []))
      .catch(() => {});
  }, []);

  const predict = async () => {
    setLoading(true);
    setError("");
    setPrediction(null);
    try {
      const resp = await authFetch("/v1/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: modelId,
          messages: [{ role: "user", content: prompt }],
          max_tokens: maxTokens,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setPrediction(await resp.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <Calculator className="h-6 w-6 text-brand-500" />
          Cost Predictor
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Enter a prompt and instantly see the exact token count and predicted cost — before you send a single API request.
        </p>
      </div>

      <div className="space-y-4">
        {/* Model selector */}
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-ink-500">Model</label>
            <select
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm"
            >
              {models.length === 0 && <option value="claude-opus-5">Claude Opus 5</option>}
              {models.map((m) => (
                <option key={m.model_id} value={m.model_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="w-40">
            <label className="mb-1 block text-xs font-medium text-ink-500">Max Tokens</label>
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-sm"
            />
          </div>
        </div>

        {/* Prompt input */}
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-500">Prompt</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="h-40 w-full rounded-lg border border-ink-200 bg-white p-3 font-mono text-sm text-ink-800"
          />
        </div>

        <button
          onClick={predict}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
          Predict Cost
        </button>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle className="mr-1 inline h-4 w-4" />
            {error}
          </div>
        )}

        {/* Results */}
        {prediction && (
          <div className="space-y-4">
            {/* Main cost display */}
            <div className="overflow-hidden rounded-xl border border-ink-200 bg-white">
              <div className="border-b border-ink-100 bg-ink-50 px-5 py-3">
                <h3 className="text-sm font-semibold text-ink-700">
                  Prediction for {prediction.display_name}
                </h3>
              </div>
              <div className="grid grid-cols-4 divide-x divide-ink-100">
                <CostCell label="Input Tokens" value={String(prediction.input_tokens)} />
                <CostCell
                  label="Est. Output"
                  value={String(prediction.estimated_output_tokens)}
                  sub="tokens"
                />
                <CostCell
                  label="Estimated Cost"
                  value={prediction.formatted.estimated_total}
                  highlight
                />
                <CostCell label="Worst Case" value={prediction.formatted.worst_case} sub="if max_tokens used" />
              </div>
              <div className="border-t border-ink-100 bg-ink-50 px-5 py-2 text-xs text-ink-500">
                Task type: <span className="font-medium text-ink-700">{prediction.task_type}</span>
                {" · "}
                Confidence: <span className="font-medium text-ink-700">{prediction.confidence}</span>
                {" · "}
                Margin: <span className="font-medium text-ink-700">{prediction.pricing_reference.margin_applied}</span>
                {" · "}
                Pricing: {prediction.pricing_reference.prompt_per_mtok}/Mtok in,{" "}
                {prediction.pricing_reference.completion_per_mtok}/Mtok out
              </div>
            </div>

            {/* Routing suggestion */}
            {prediction.routing_suggestion && (
              <div className="flex items-start gap-3 rounded-xl border border-green-200 bg-green-50 p-4">
                <TrendingDown className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-600" />
                <div>
                  <div className="text-sm font-semibold text-green-900">
                    Save {prediction.routing_suggestion.estimated_savings_pct}% with{" "}
                    {prediction.routing_suggestion.display_name}
                  </div>
                  <p className="mt-0.5 text-xs text-green-700">
                    {prediction.routing_suggestion.reason}. Quality difference:{" "}
                    {prediction.routing_suggestion.quality_difference > 0 ? "+" : ""}
                    {prediction.routing_suggestion.quality_difference} points.
                  </p>
                </div>
              </div>
            )}

            {/* No suggestion = already optimal */}
            {!prediction.routing_suggestion && (
              <div className="flex items-center gap-2 rounded-xl border border-ink-200 bg-white p-4">
                <CheckCircle className="h-5 w-5 text-green-500" />
                <span className="text-sm text-ink-600">
                  This model is cost-optimal for your prompt. No cheaper alternative with similar quality.
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CostCell({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs font-medium text-ink-500">{label}</p>
      <p
        className={`mt-1 text-xl font-bold ${
          highlight ? "text-brand-600" : "text-ink-900"
        }`}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-ink-400">{sub}</p>}
    </div>
  );
}
