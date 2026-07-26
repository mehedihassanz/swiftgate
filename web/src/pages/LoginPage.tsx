import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Zap, Key, ArrowRight, Shield } from "lucide-react";

export default function LoginPage() {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Validate the key against the backend
    try {
      const resp = await fetch("/admin/stats", {
        headers: { "X-Admin-Key": key.trim() },
      });
      if (resp.ok) {
        login(key.trim());
        navigate("/");
      } else {
        setError("Invalid admin key. Please check and try again.");
      }
    } catch {
      // In development mode with no ADMIN_KEY set, allow login anyway
      if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
        login(key.trim() || "dev");
        navigate("/");
      } else {
        setError("Cannot reach server. Is the backend running?");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="mb-8 flex items-center justify-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <span className="text-xl font-bold tracking-tight text-white">
            SwiftGate
          </span>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-ink-800 bg-ink-900/50 p-8 backdrop-blur">
          <div className="mb-6 text-center">
            <div className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-brand-500/10">
              <Shield className="h-6 w-6 text-brand-400" />
            </div>
            <h1 className="text-lg font-semibold text-white">Admin Login</h1>
            <p className="mt-1 text-sm text-ink-400">
              Enter your admin key to access the dashboard
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-ink-300">
                Admin Key
              </label>
              <div className="relative">
                <Key className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500" />
                <input
                  type="password"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder="Enter your admin key"
                  className="w-full rounded-lg border border-ink-700 bg-ink-800/50 py-2.5 pl-10 pr-3 text-sm text-white placeholder:text-ink-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  autoFocus
                />
              </div>
            </div>

            {error && (
              <div className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-brand-700"
            >
              Login
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>

          <div className="mt-6 rounded-lg bg-ink-800/30 px-3 py-2.5 text-xs text-ink-500">
            <p>
              The admin key is set via the <code className="text-ink-300">ADMIN_KEY</code> environment variable
              on the backend. In development mode, any key works.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
