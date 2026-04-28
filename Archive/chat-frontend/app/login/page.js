"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [armyNumber, setArmyNumber] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(armyNumber, password);
      router.push("/chat");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-chat">
      <div className="w-full max-w-sm rounded-xl bg-input border border-border p-8 shadow-2xl">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white text-xl font-bold">
            A
          </div>
          <h1 className="text-xl font-semibold text-[#ececf1]">Army AI Chat</h1>
          <p className="mt-1 text-sm text-[#8e8ea0]">Sign in to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-[#c5c5d2]">Army Number</label>
            <input
              type="text"
              value={armyNumber}
              onChange={(e) => setArmyNumber(e.target.value)}
              required
              autoFocus
              className="w-full rounded-lg border border-border bg-chat px-3 py-2 text-sm text-[#ececf1] placeholder-[#565869] outline-none focus:border-accent focus:ring-1 focus:ring-accent"
              placeholder="e.g. IC-12345"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-[#c5c5d2]">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-border bg-chat px-3 py-2 text-sm text-[#ececf1] placeholder-[#565869] outline-none focus:border-accent focus:ring-1 focus:ring-accent"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-red-900/30 border border-red-700 px-3 py-2 text-sm text-red-400">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#0d8a6c] disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
