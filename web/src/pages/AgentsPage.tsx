import { useState, useEffect } from "react";
import { Bot, Plus, OctagonX, Pause, Play, RefreshCw, Loader2, Activity } from "lucide-react";

interface Agent {
  id: number;
  agent_id: string;
  name: string;
  status: string;
  budget_cents: number | null;
  spend_cents: number;
  budget_used_pct: number | null;
  request_count: number;
  created_at: string | null;
  last_active: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  killed: "bg-red-100 text-red-700",
  budget_exceeded: "bg-orange-100 text-orange-700",
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ agent_id: "", name: "", budget_cents: "" });

  const load = async () => {
    setLoading(true);
    try {
      const resp = await fetch("/v1/agents");
      const data = await resp.json();
      setAgents(data.agents || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    await fetch("/v1/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_id: form.agent_id,
        name: form.name || form.agent_id,
        budget_cents: form.budget_cents ? Number(form.budget_cents) : undefined,
      }),
    });
    setForm({ agent_id: "", name: "", budget_cents: "" });
    setShowCreate(false);
    load();
  };

  const action = async (agentId: string, actionType: string) => {
    await fetch(`/v1/agents/${agentId}/${actionType}`, { method: "POST" });
    load();
  };

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
            <Bot className="h-6 w-6 text-brand-500" />
            Agent Orchestration
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            Per-agent budgets, kill-switches, and execution tracing for multi-agent workflows.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          <Plus className="h-4 w-4" /> Register Agent
        </button>
      </div>

      {showCreate && (
        <div className="mb-4 rounded-xl border border-ink-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-ink-700">Register New Agent</h3>
          <div className="flex gap-3">
            <input type="text" placeholder="Agent ID (e.g. 'code-reviewer-1')" value={form.agent_id}
              onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
              className="flex-1 rounded-lg border border-ink-200 px-3 py-2 text-sm" />
            <input type="text" placeholder="Name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-40 rounded-lg border border-ink-200 px-3 py-2 text-sm" />
            <input type="number" placeholder="Budget (cents)" value={form.budget_cents}
              onChange={(e) => setForm({ ...form, budget_cents: e.target.value })}
              className="w-40 rounded-lg border border-ink-200 px-3 py-2 text-sm" />
            <button onClick={create} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">
              Create
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-ink-400"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>
      ) : agents.length === 0 ? (
        <div className="rounded-xl border border-dashed border-ink-300 bg-white p-12 text-center">
          <Bot className="mx-auto mb-2 h-8 w-8 text-ink-300" />
          <p className="text-sm text-ink-400">No agents registered yet.</p>
          <p className="mt-1 text-xs text-ink-400">
            Register an agent to set per-agent budgets, kill-switches, and trace execution.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {agents.map((a) => (
            <div key={a.id} className="rounded-xl border border-ink-200 bg-white p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-ink-900">{a.name}</h3>
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[a.status] || "bg-ink-100"}`}>
                      {a.status}
                    </span>
                  </div>
                  <p className="font-mono text-xs text-ink-400">{a.agent_id}</p>
                </div>
                <div className="flex gap-1">
                  {a.status === "active" && (
                    <>
                      <button onClick={() => action(a.agent_id, "pause")} title="Pause"
                        className="rounded p-1 text-ink-400 hover:bg-yellow-50 hover:text-yellow-600">
                        <Pause className="h-3.5 w-3.5" />
                      </button>
                      <button onClick={() => action(a.agent_id, "kill")} title="Kill"
                        className="rounded p-1 text-ink-400 hover:bg-red-50 hover:text-red-600">
                        <OctagonX className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                  {(a.status === "paused" || a.status === "killed") && (
                    <button onClick={() => action(a.agent_id, "resume")} title="Resume"
                      className="rounded p-1 text-ink-400 hover:bg-green-50 hover:text-green-600">
                      <Play className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button onClick={() => action(a.agent_id, "reset")} title="Reset budget"
                    className="rounded p-1 text-ink-400 hover:bg-brand-50 hover:text-brand-600">
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
                <div>
                  <p className="text-ink-400">Spend</p>
                  <p className="font-mono font-medium text-ink-700">${(a.spend_cents / 10000).toFixed(4)}</p>
                </div>
                <div>
                  <p className="text-ink-400">Budget</p>
                  <p className="font-mono font-medium text-ink-700">
                    {a.budget_cents ? `$${(a.budget_cents / 10000).toFixed(2)}` : "∞"}
                  </p>
                </div>
                <div>
                  <p className="text-ink-400">Requests</p>
                  <p className="font-mono font-medium text-ink-700">{a.request_count}</p>
                </div>
              </div>

              {a.budget_used_pct !== null && (
                <div className="mt-3">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
                    <div
                      className={`h-full rounded-full ${
                        a.budget_used_pct >= 100 ? "bg-red-500"
                        : a.budget_used_pct >= 80 ? "bg-orange-500"
                        : a.budget_used_pct >= 50 ? "bg-yellow-500"
                        : "bg-green-500"
                      }`}
                      style={{ width: `${Math.min(100, a.budget_used_pct)}%` }}
                    />
                  </div>
                  <p className="mt-0.5 text-right text-xs text-ink-400">{a.budget_used_pct.toFixed(1)}% used</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Info banner */}
      <div className="mt-4 rounded-lg bg-brand-50 p-4 text-xs text-brand-700">
        <p className="flex items-center gap-1.5 font-semibold"><Activity className="h-3.5 w-3.5" /> How agent budgets work</p>
        <p className="mt-1">
          Pass <code className="rounded bg-white px-1 font-mono">agent_id</code> in your API request body to attribute spend to an agent.
          SwiftGate will automatically block requests when the agent's budget is exceeded or if the kill-switch is activated.
        </p>
      </div>
    </div>
  );
}
