import { useState, useEffect } from "react";
import { Trophy, Loader2, Star, MessageSquare, ThumbsUp, ThumbsDown } from "lucide-react";

interface QualityEntry {
  model_id: string;
  empirical_score: number;
  samples: number;
}

interface Pattern {
  type: string;
  description: string;
}

interface PiiResult {
  total_found: number;
  matches: { type: string; start: number; end: number }[];
  types_found: string[];
}

interface RedactResult {
  redacted_messages: { role: string; content: string }[];
  audit: { type: string; count: number }[];
  token_count: number;
}

export default function QualityPage() {
  const [tab, setTab] = useState<"leaderboard" | "pii">("leaderboard");

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <Trophy className="h-6 w-6 text-brand-500" />
          Quality & Privacy
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Quality-per-dollar rankings and PII redaction controls.
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-4 flex gap-2 border-b border-ink-200">
        <TabButton active={tab === "leaderboard"} onClick={() => setTab("leaderboard")}>
          <Trophy className="h-4 w-4" /> Quality Leaderboard
        </TabButton>
        <TabButton active={tab === "pii"} onClick={() => setTab("pii")}>
          <MessageSquare className="h-4 w-4" /> PII Redaction
        </TabButton>
      </div>

      {tab === "leaderboard" && <LeaderboardTab />}
      {tab === "pii" && <PiiTab />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition ${
        active
          ? "border-b-2 border-brand-600 text-brand-700"
          : "border-b-2 border-transparent text-ink-500 hover:text-ink-700"
      }`}
    >
      {children}
    </button>
  );
}

// ─── Quality Leaderboard Tab ───────────────────────────────────────────

function LeaderboardTab() {
  const [taskType, setTaskType] = useState("chat");
  const [entries, setEntries] = useState<QualityEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`/v1/quality/leaderboard?task_type=${taskType}`);
      const data = await resp.json();
      setEntries(data.leaderboard || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [taskType]);

  return (
    <div>
      {/* Task type filter */}
      <div className="mb-4 flex gap-2">
        {["chat", "code", "reasoning", "vision", "tool_use"].map((t) => (
          <button
            key={t}
            onClick={() => setTaskType(t)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              taskType === t
                ? "bg-brand-600 text-white"
                : "bg-ink-100 text-ink-600 hover:bg-ink-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-ink-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading...
        </div>
      ) : entries.length === 0 ? (
        <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
          <Trophy className="mx-auto mb-2 h-8 w-8 text-ink-300" />
          <p className="text-sm text-ink-400">No quality data yet for "{taskType}".</p>
          <p className="mt-1 text-xs text-ink-400">
            Quality scores accumulate as users provide feedback (thumbs up/down) and
            implicit signals (retries, conversation continuation).
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-ink-200 bg-white">
          <table className="w-full">
            <thead className="bg-ink-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-ink-500">Rank</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-ink-500">Model</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-ink-500">Score</th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-ink-500">Samples</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {entries.map((e, i) => (
                <tr key={e.model_id} className="hover:bg-ink-50">
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm font-bold text-ink-400">#{i + 1}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm font-medium text-ink-900">{e.model_id}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="inline-flex items-center gap-1 font-mono text-sm font-bold text-ink-900">
                      <Star className="h-3 w-3 text-amber-500" />
                      {e.empirical_score.toFixed(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-mono text-xs text-ink-500">{e.samples}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Feedback helper */}
      <div className="mt-4 rounded-lg bg-brand-50 p-4 text-xs text-brand-700">
        <p className="flex items-center gap-1.5 font-semibold">
          <ThumbsUp className="h-3.5 w-3.5" /> Providing feedback
        </p>
        <p className="mt-1">
          POST to <code className="rounded bg-white px-1 font-mono">/v1/quality/feedback</code> with
          a 1-10 rating. Or let SwiftGate detect implicit signals automatically — retries are negative,
          continued conversations are positive.
        </p>
      </div>
    </div>
  );
}

// ─── PII Redaction Tab ─────────────────────────────────────────────────

function PiiTab() {
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [testText, setTestText] = useState("");
  const [detectResult, setDetectResult] = useState<PiiResult | null>(null);
  const [redactResult, setRedactResult] = useState<RedactResult | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    fetch("/v1/pii/patterns")
      .then((r) => r.json())
      .then((d) => setPatterns(d.patterns || []));
  }, []);

  const runTest = async () => {
    if (!testText.trim()) return;
    setTesting(true);
    try {
      // Detect
      const dResp = await fetch("/v1/pii/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: testText }),
      });
      setDetectResult(await dResp.json());

      // Redact
      const rResp = await fetch("/v1/pii/redact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: testText }] }),
      });
      setRedactResult(await rResp.json());
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Pattern list */}
      <div className="rounded-xl border border-ink-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-ink-700">
          Active Detection Patterns ({patterns.length})
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {patterns.map((p) => (
            <div
              key={p.type}
              className="flex items-center gap-2 rounded-lg bg-ink-50 px-3 py-2 text-xs"
            >
              <span className="rounded bg-brand-100 px-1.5 py-0.5 font-mono font-semibold text-brand-700">
                {p.type}
              </span>
              <span className="text-ink-500">{p.description}</span>
            </div>
          ))}
        </div>
      </div>

      {/* PII tester */}
      <div className="rounded-xl border border-ink-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold text-ink-700">Try It</h3>
        <textarea
          value={testText}
          onChange={(e) => setTestText(e.target.value)}
          placeholder="Paste text with PII to test detection and redaction..."
          className="h-24 w-full rounded-lg border border-ink-200 p-3 font-mono text-sm"
        />
        <button
          onClick={runTest}
          disabled={testing || !testText.trim()}
          className="mt-2 flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
          Detect & Redact
        </button>

        {/* Results */}
        {detectResult && (
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-ink-200 p-3">
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink-500">
                <ThumbsDown className="h-3.5 w-3.5 text-red-500" />
                Detection ({detectResult.total_found} found)
              </p>
              {detectResult.types_found.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {detectResult.types_found.map((t) => (
                    <span
                      key={t}
                      className="rounded bg-red-100 px-2 py-0.5 font-mono text-xs text-red-700"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-ink-400">No PII detected.</p>
              )}
            </div>

            <div className="rounded-lg border border-ink-200 p-3">
              <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink-500">
                <ThumbsUp className="h-3.5 w-3.5 text-green-500" />
                Redacted Output
              </p>
              {redactResult && redactResult.token_count > 0 ? (
                <>
                  <p className="font-mono text-xs text-ink-700">
                    {redactResult.redacted_messages[0]?.content.slice(0, 200)}
                    {(redactResult.redacted_messages[0]?.content.length || 0) > 200 ? "..." : ""}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {redactResult.audit.map((a, i) => (
                      <span
                        key={i}
                        className="rounded bg-green-100 px-1.5 py-0.5 font-mono text-xs text-green-700"
                      >
                        {a.type} ×{a.count}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-xs text-ink-400">Nothing to redact.</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="rounded-lg bg-brand-50 p-4 text-xs text-brand-700">
        <p className="font-semibold">PII redaction in the gateway</p>
        <p className="mt-1">
          When <code className="rounded bg-white px-1 font-mono">PII_REDACTION_ENABLED=true</code>,
          SwiftGate strips PII from requests before forwarding to providers, then rehydrates
          original values in responses. PII never leaves your SwiftGate instance.
        </p>
      </div>
    </div>
  );
}
