import { Zap, Calculator, GitCompare, BarChart3, TrendingDown, Shield, Check, Code2, ArrowRight, DollarSign } from "lucide-react";

// Links to the web service (different Railway service)
const PORTAL_URL = "https://web-production-8fa1c.up.railway.app/portal/signup";
const DASHBOARD_URL = "https://web-production-8fa1c.up.railway.app/login";

export default function App() {
  return (
    <div className="min-h-screen bg-white text-ink-900">
      {/* Nav */}
      <nav className="border-b border-ink-100">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700">
              <Zap className="h-4 w-4 text-white" />
            </div>
            <span className="text-base font-bold tracking-tight">SwiftGate</span>
          </div>
          <div className="flex items-center gap-6 text-sm">
            <a href="#features" className="text-ink-600 hover:text-ink-900">Features</a>
            <a href="#how" className="text-ink-600 hover:text-ink-900">How it Works</a>
            <a href="#pricing" className="text-ink-600 hover:text-ink-900">Pricing</a>
            <a href={PORTAL_URL} className="rounded-lg border border-ink-200 px-4 py-1.5 font-medium text-ink-700 hover:bg-ink-50">
              Sign Up
            </a>
            <a href={DASHBOARD_URL} className="rounded-lg bg-brand-600 px-4 py-1.5 font-medium text-white hover:bg-brand-700">
              Dashboard
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-brand-50 via-white to-purple-50" />
        <div className="relative mx-auto max-w-4xl px-6 py-24 text-center">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-4 py-1.5 text-xs font-medium text-brand-700">
            <TrendingDown className="h-3.5 w-3.5" />
            1% margin · vs OpenRouter's 5.5%
          </div>
          <h1 className="text-5xl font-bold tracking-tight text-ink-900">
            See the cost <span className="text-brand-600">before</span> you pay it
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-ink-600">
            SwiftGate is an AI model gateway that predicts exact request costs before sending.
            Compare 34+ models across 18 providers. Route intelligently. Never get a surprise bill again.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <a href={PORTAL_URL} className="flex items-center gap-2 rounded-lg bg-brand-600 px-6 py-3 text-sm font-medium text-white hover:bg-brand-700">
              Get Your API Key <ArrowRight className="h-4 w-4" />
            </a>
            <a href="#features" className="rounded-lg border border-ink-200 px-6 py-3 text-sm font-medium text-ink-700 hover:bg-ink-50">
              See Features
            </a>
          </div>
          <p className="mt-4 text-xs text-ink-400">Free signup · No credit card · OpenAI-compatible API</p>
        </div>
      </section>

      {/* Stats bar */}
      <section className="border-y border-ink-100 bg-ink-50">
        <div className="mx-auto grid max-w-4xl grid-cols-4 gap-4 px-6 py-8">
          <Stat value="34+" label="Models" />
          <Stat value="18" label="Providers" />
          <Stat value="1%" label="Token margin" sub="vs OpenRouter 5.5%" />
          <Stat value="Exact" label="Token counting" sub="tiktoken + HF" />
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20">
        <div className="mx-auto max-w-5xl px-6">
          <h2 className="text-center text-3xl font-bold tracking-tight">Cost intelligence for AI APIs</h2>
          <p className="mx-auto mt-3 max-w-2xl text-center text-ink-500">
            The only gateway that tells you what a request will cost <em>before</em> you send it.
          </p>
          <div className="mt-12 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Feature
              icon={Calculator}
              title="Cost Prediction"
              desc="Enter a prompt, instantly see exact token counts and predicted cost — including worst-case scenario. Uses the right tokenizer for each model family."
            />
            <Feature
              icon={GitCompare}
              title="Pareto-Optimal Routing"
              desc="Compare all models on quality vs cost. We mark Pareto-optimal choices — models nobody else beats on both axes. Route to the best value automatically."
            />
            <Feature
              icon={BarChart3}
              title="Spend Analytics"
              desc="Per-model cost breakdowns, token tracking, latency stats. See exactly where your money goes. Budget caps and alerts included."
            />
            <Feature
              icon={DollarSign}
              title="1% Token Margin"
              desc="We charge 1% — not OpenRouter's 5.5% credit fee. Same providers, same models, 80% less overhead. For $1,000/mo in API spend, that's $45/mo saved."
            />
            <Feature
              icon={Shield}
              title="Budget Enforcement"
              desc="Set per-key and per-agent monthly budgets. Requests that would exceed your budget are blocked before they're sent. No surprise bills."
            />
            <Feature
              icon={Code2}
              title="OpenAI-Compatible"
              desc="Drop-in replacement for api.openai.com. Change one URL in your SDK, get cost intelligence for free. Works with Cursor, LangChain, and any OpenAI-compatible tool."
            />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="border-t border-ink-100 bg-ink-50 py-20">
        <div className="mx-auto max-w-3xl px-6">
          <h2 className="text-center text-3xl font-bold tracking-tight">How it works</h2>
          <div className="mt-10 space-y-6">
            <Step num="1" title="Predict" desc="Before forwarding your request, SwiftGate counts tokens using the exact tokenizer for your model and computes the estimated cost." />
            <Step num="2" title="Route" desc="If a cheaper model with similar quality exists, we suggest it. Or auto-route based on your preference: cheapest, fastest, balanced, or highest quality." />
            <Step num="3" title="Track" desc="After completion, we record actual token usage and compare it to the prediction — making future predictions more accurate." />
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20">
        <div className="mx-auto max-w-4xl px-6">
          <h2 className="text-center text-3xl font-bold tracking-tight">Simple pricing</h2>
          <p className="mt-3 text-center text-ink-500">1% margin on tokens. No hidden fees. No credit surcharge.</p>
          <div className="mt-10 grid grid-cols-3 gap-6">
            <PriceCard name="Free" price="$0" desc="For trying it out" features={["1,000 req/month", "Cost prediction", "All models", "Community support"]} />
            <PriceCard name="Pro" price="1%" desc="margin on tokens" features={["Unlimited requests", "Budget enforcement", "Usage analytics", "Auto-routing", "Priority support"]} highlight />
            <PriceCard name="Enterprise" price="Custom" desc="For production" features={["Everything in Pro", "Self-host option", "SSO + audit logs", "SLA guarantees", "Dedicated support"]} />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-ink-100 bg-gradient-to-br from-brand-600 to-brand-800 py-16">
        <div className="mx-auto max-w-2xl px-6 text-center">
          <h2 className="text-3xl font-bold text-white">Stop guessing. Start predicting.</h2>
          <p className="mt-3 text-brand-100">Sign up free and get your API key in seconds.</p>
          <a href={PORTAL_URL} className="mt-6 inline-flex items-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-semibold text-brand-700 hover:bg-brand-50">
            Get Your API Key <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-ink-100 py-8 text-center text-sm text-ink-400">
        <div className="mx-auto max-w-6xl px-6">
          SwiftGate — See the cost before you pay it · Built with ⚡
        </div>
      </footer>
    </div>
  );
}

function Stat({ value, label, sub }: { value: string; label: string; sub?: string }) {
  return (
    <div className="text-center">
      <p className="text-3xl font-bold text-brand-600">{value}</p>
      <p className="mt-1 text-sm font-medium text-ink-600">{label}</p>
      {sub && <p className="text-xs text-ink-400">{sub}</p>}
    </div>
  );
}

function Feature({ icon: Icon, title, desc }: { icon: React.ElementType; title: string; desc: string }) {
  return (
    <div className="rounded-xl border border-ink-200 p-6">
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50">
        <Icon className="h-5 w-5 text-brand-600" />
      </div>
      <h3 className="text-base font-semibold text-ink-900">{title}</h3>
      <p className="mt-2 text-sm text-ink-600">{desc}</p>
    </div>
  );
}

function Step({ num, title, desc }: { num: string; title: string; desc: string }) {
  return (
    <div className="flex gap-4">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white">
        {num}
      </div>
      <div>
        <h3 className="font-semibold text-ink-900">{title}</h3>
        <p className="mt-1 text-sm text-ink-600">{desc}</p>
      </div>
    </div>
  );
}

function PriceCard({
  name,
  price,
  desc,
  features,
  highlight,
}: {
  name: string;
  price: string;
  desc: string;
  features: string[];
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-6 ${highlight ? "border-brand-300 bg-brand-50" : "border-ink-200 bg-white"}`}>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500">{name}</h3>
      <p className="mt-2 text-3xl font-bold text-ink-900">{price}</p>
      <p className="text-xs text-ink-400">{desc}</p>
      <ul className="mt-4 space-y-2">
        {features.map((f) => (
          <li key={f} className="flex items-center gap-2 text-sm text-ink-700">
            <Check className="h-4 w-4 text-green-500" /> {f}
          </li>
        ))}
      </ul>
    </div>
  );
}
