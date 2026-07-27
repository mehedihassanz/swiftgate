import { useState, useEffect } from "react";
import { Zap, DollarSign, ArrowRight, Activity, Cpu, TrendingUp, Key } from "lucide-react";
import { Link } from "react-router-dom";
import { useUserAuth, userFetch } from "../userAuth";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

interface UsageData {
  total_requests: number;
  total_spend_usd: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  credits_remaining_usd: number;
}

interface DailyEntry { date: string; cost_cents: number; requests: number; }

const BRAND = "#0A6CFF";

export default function DashboardPage() {
  const { user } = useUserAuth();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [daily, setDaily] = useState<DailyEntry[]>([]);
  const [modelCount, setModelCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      userFetch("/user/usage").then((r) => r.json()).catch(() => null),
      userFetch("/user/usage/daily?days=30").then((r) => r.json()).catch(() => null),
      userFetch("/v1/models").then((r) => r.json()).catch(() => null),
    ])
      .then(([u, d, m]) => {
        if (u) setUsage(u);
        if (d?.daily) setDaily(d.daily);
        if (m?.models) setModelCount(m.models.length);
      })
      .finally(() => setLoading(false));
  }, []);

  const chartData = daily.map((d) => ({
    date: d.date.slice(5),
    cost: d.cost_cents / 10000,
  }));

  if (loading) {
    return <div className="text-ink-400">Loading...</div>;
  }

  return (
    <div className="mx-auto max-w-6xl">
      {/* Welcome */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-ink-900">
          Welcome{user?.name ? `, ${user.name}` : ""} 👋
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Cost intelligence for AI APIs. See the cost before you pay it.
        </p>
      </div>

      {/* Stats */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={DollarSign}
          label="Credits"
          value={usage ? `$${usage.credits_remaining_usd.toFixed(2)}` : "$0"}
          sub="available balance"
          color="green"
        />
        <StatCard
          icon={Activity}
          label="Requests"
          value={usage ? usage.total_requests.toLocaleString() : "0"}
          sub="all-time"
        />
        <StatCard
          icon={TrendingUp}
          label="Total Spend"
          value={usage ? `$${usage.total_spend_usd.toFixed(4)}` : "$0"}
          sub="all-time"
        />
        <StatCard
          icon={Cpu}
          label="Models"
          value={String(modelCount)}
          sub="available"
        />
      </div>

      {/* Usage chart */}
      <div className="mb-6 rounded-xl border border-ink-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-semibold text-ink-700">Spend (last 30 days)</h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={BRAND} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={BRAND} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false}
                tickFormatter={(v) => `$${v.toFixed(4)}`} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                formatter={(v: any) => [`$${Number(v).toFixed(6)}`, "Cost"]}
              />
              <Area type="monotone" dataKey="cost" stroke={BRAND} strokeWidth={2} fill="url(#costGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-[200px] items-center justify-center text-sm text-ink-400">
            No usage data yet. Start making API requests to see your spend chart.
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <QuickAction
          to="/keys"
          icon={Key}
          title="Get API Key"
          desc="Create a key and start building"
        />
        <QuickAction
          to="/models"
          icon={Cpu}
          title="Browse Models"
          desc={`${modelCount} models with live pricing`}
        />
        <QuickAction
          to="/predict"
          icon={Zap}
          title="Cost Predictor"
          desc="See exact cost before you send"
        />
      </div>

      {/* Quickstart */}
      <div className="mt-6 rounded-xl border border-ink-200 bg-white p-5">
        <h3 className="mb-3 font-semibold text-ink-900">Quickstart</h3>
        <div className="overflow-hidden rounded-lg bg-ink-900">
          <div className="flex items-center gap-2 border-b border-ink-700 px-4 py-2">
            <div className="flex gap-1.5">
              <span className="h-3 w-3 rounded-full bg-red-500" />
              <span className="h-3 w-3 rounded-full bg-yellow-500" />
              <span className="h-3 w-3 rounded-full bg-green-500" />
            </div>
            <span className="ml-2 text-xs text-ink-400">quickstart.py</span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm text-green-400"><code>{`from openai import OpenAI

client = OpenAI(
    base_url="https://api.swiftgate.ai/v1",
    api_key="<your-key>",
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)`}</code></pre>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon, label, value, sub, color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string; value: string; sub: string; color?: string;
}) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4">
      <div className="mb-2 flex items-center gap-2">
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${
          color === "green" ? "bg-green-100 text-green-600" : "bg-brand-100 text-brand-600"
        }`}>
          <Icon className="h-4 w-4" />
        </div>
        <span className="text-sm text-ink-500">{label}</span>
      </div>
      <div className="text-2xl font-bold text-ink-900">{value}</div>
      <div className="mt-0.5 text-xs text-ink-400">{sub}</div>
    </div>
  );
}

function QuickAction({
  to, icon: Icon, title, desc,
}: {
  to: string; icon: React.ElementType; title: string; desc: string;
}) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-3 rounded-xl border border-ink-200 bg-white p-4 hover:border-brand-300 hover:shadow-sm transition"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600 group-hover:bg-brand-100">
        <Icon className="h-5 w-5" />
      </div>
      <div className="flex-1">
        <div className="text-sm font-semibold text-ink-900">{title}</div>
        <div className="text-xs text-ink-400">{desc}</div>
      </div>
      <ArrowRight className="h-4 w-4 text-ink-300 group-hover:text-brand-500" />
    </Link>
  );
}
