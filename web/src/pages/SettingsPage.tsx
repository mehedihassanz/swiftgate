import { useState, useEffect } from "react";
import { useUserAuth, userFetch } from "../userAuth";
import {
  Settings as SettingsIcon, User, Mail, Save, Loader2, Check,
  CreditCard, Zap, Loader2 as Spinner, AlertCircle,
} from "lucide-react";

interface Package {
  id: string;
  label: string;
  credits_cents: number;
  price_usd: number;
}

export default function SettingsPage() {
  const { user, login } = useUserAuth();
  const [name, setName] = useState(user?.name || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [packages, setPackages] = useState<Package[]>([]);
  const [buying, setBuying] = useState<string | null>(null);
  const [customAmount, setCustomAmount] = useState("");
  const [buyingCustom, setBuyingCustom] = useState(false);
  const [error, setError] = useState("");
  const [justPaid, setJustPaid] = useState(false);

  useEffect(() => {
    userFetch("/user/billing/packages")
      .then((r) => r.json())
      .then((d) => setPackages(d.packages || []))
      .catch(() => {});

    // Check if redirected from Stripe success
    const params = new URLSearchParams(window.location.search);
    if (params.get("paid") === "1") {
      setJustPaid(true);
      // Reload user data to get new balance
      userFetch("/auth/me").then((r) => r.json()).then((data) => {
        if (user) login(localStorage.getItem("swiftgate_user_token") || "", data);
      });
      setTimeout(() => setJustPaid(false), 5000);
    }
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await userFetch("/user/settings", {
        method: "PUT",
        body: JSON.stringify({ name }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const buyPackage = async (pkgId: string) => {
    setBuying(pkgId);
    setError("");
    try {
      const resp = await userFetch("/user/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ package_id: pkgId }),
      });
      const data = await resp.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        setError(data.detail || "Failed to start checkout");
      }
    } catch {
      setError("Cannot reach billing server");
    } finally {
      setBuying(null);
    }
  };

  const buyCustom = async () => {
    const amount = parseFloat(customAmount);
    if (!amount || amount < 1) {
      setError("Enter at least $1");
      return;
    }
    setBuyingCustom(true);
    setError("");
    try {
      const resp = await userFetch("/user/billing/checkout/custom", {
        method: "POST",
        body: JSON.stringify({ amount_usd: amount }),
      });
      const data = await resp.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        setError(data.detail || "Failed to start checkout");
      }
    } catch {
      setError("Cannot reach billing server");
    } finally {
      setBuyingCustom(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <SettingsIcon className="h-6 w-6 text-brand-500" />
          Settings
        </h1>
        <p className="mt-1 text-sm text-ink-500">Manage your account, credits, and preferences.</p>
      </div>

      {/* Payment success banner */}
      {justPaid && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-green-300 bg-green-50 px-4 py-3">
          <Check className="h-5 w-5 text-green-600" />
          <span className="text-sm font-medium text-green-800">Payment successful! Credits added to your account.</span>
        </div>
      )}

      {/* Credits + Buy */}
      <div className="rounded-xl border border-ink-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-ink-700">Credits Balance</h2>
            <p className="mt-1 text-3xl font-bold text-ink-900">${(user?.credits_usd ?? 0).toFixed(2)}</p>
            <p className="text-xs text-ink-400">Available for API usage</p>
          </div>
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-green-100">
            <Zap className="h-6 w-6 text-green-600" />
          </div>
        </div>

        {/* Credit packages */}
        {packages.length > 0 && (
          <>
            <div className="mt-4 border-t border-ink-100 pt-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-400">Buy Credits</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {packages.map((pkg) => (
                  <button
                    key={pkg.id}
                    onClick={() => buyPackage(pkg.id)}
                    disabled={buying === pkg.id}
                    className="rounded-xl border border-ink-200 bg-white p-3 text-center transition hover:border-brand-400 hover:shadow-sm disabled:opacity-50"
                  >
                    <div className="text-lg font-bold text-ink-900">${pkg.price_usd}</div>
                    <div className="mt-0.5 text-xs text-ink-500">{pkg.label}</div>
                    {buying === pkg.id && <Spinner className="mx-auto mt-1 h-3 w-3 animate-spin text-brand-500" />}
                  </button>
                ))}
              </div>
            </div>

            {/* Custom amount */}
            <div className="mt-4 flex items-end gap-2">
              <div className="flex-1">
                <label className="mb-1 block text-xs font-medium text-ink-500">Custom Amount</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-ink-400">$</span>
                  <input
                    type="number"
                    value={customAmount}
                    onChange={(e) => setCustomAmount(e.target.value)}
                    placeholder="25"
                    min="1"
                    className="w-full rounded-lg border border-ink-300 py-2 pl-7 pr-3 text-sm focus:border-brand-500 focus:outline-none"
                  />
                </div>
              </div>
              <button
                onClick={buyCustom}
                disabled={buyingCustom || !customAmount}
                className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {buyingCustom ? <Spinner className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
                Buy
              </button>
            </div>
          </>
        )}

        {error && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}
      </div>

      {/* Profile */}
      <div className="mt-4 rounded-xl border border-ink-200 bg-white p-6">
        <h2 className="mb-4 text-sm font-semibold text-ink-700">Profile</h2>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">Name</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full rounded-lg border border-ink-300 py-2 pl-10 pr-3 text-sm text-ink-900 focus:border-brand-500 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-500">Email</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
              <input
                type="email"
                value={user?.email || ""}
                disabled
                className="w-full rounded-lg border border-ink-200 bg-ink-50 py-2 pl-10 pr-3 text-sm text-ink-500"
              />
            </div>
            <p className="mt-1 text-xs text-ink-400">Email cannot be changed.</p>
          </div>
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
            {saved ? "Saved!" : "Save Changes"}
          </button>
        </div>
      </div>

      {/* API Access */}
      <div className="mt-4 rounded-xl border border-ink-200 bg-white p-6">
        <h2 className="mb-2 text-sm font-semibold text-ink-700">API Access</h2>
        <p className="text-sm text-ink-500">Your API base URL:</p>
        <code className="mt-2 block rounded-lg bg-ink-900 px-3 py-2 font-mono text-sm text-green-400">
          https://api.swiftgate.ai/v1
        </code>
        <p className="mt-3 text-xs text-ink-400">
          Use this as your <code className="rounded bg-ink-100 px-1">base_url</code> in any OpenAI-compatible SDK.
        </p>
      </div>
    </div>
  );
}
