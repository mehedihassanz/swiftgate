import { useState, useEffect } from "react";
import { useUserAuth, userFetch } from "../userAuth";
import { Settings as SettingsIcon, User, Mail, Save, Loader2, Check } from "lucide-react";

export default function SettingsPage() {
  const { user } = useUserAuth();
  const [name, setName] = useState(user?.name || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

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

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-ink-900">
          <SettingsIcon className="h-6 w-6 text-brand-500" />
          Settings
        </h1>
        <p className="mt-1 text-sm text-ink-500">Manage your account and preferences.</p>
      </div>

      {/* Profile */}
      <div className="rounded-xl border border-ink-200 bg-white p-6">
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

      {/* Credits */}
      <div className="mt-4 rounded-xl border border-ink-200 bg-white p-6">
        <h2 className="mb-4 text-sm font-semibold text-ink-700">Credits</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-3xl font-bold text-ink-900">${(user?.credits_usd ?? 0).toFixed(2)}</p>
            <p className="mt-1 text-xs text-ink-400">Available balance</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-ink-500">Need more credits?</p>
            <p className="mt-0.5 text-xs text-ink-400">Contact your account manager</p>
          </div>
        </div>
      </div>

      {/* Danger zone */}
      <div className="mt-4 rounded-xl border border-ink-200 bg-white p-6">
        <h2 className="mb-2 text-sm font-semibold text-ink-700">API Access</h2>
        <p className="text-sm text-ink-500">
          Your API base URL:
        </p>
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
