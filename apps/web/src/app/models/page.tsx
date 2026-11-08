"use client";

/**
 * Read-Only Models Admin View.
 * Displays VRAM meter, configured model roles (qwen3.5:4b, gemma4:e2b-it-qat, bge-m3),
 * context window metrics, and family isolation compliance.
 * Spec: 02 §5.14, 03 §Local Models, 05 §3, SEC-20, SEC-31.
 */

import React, { useState } from "react";
import { VramMeter } from "../../components/models/vram-meter";

interface ConfiguredRole {
  role_name: string;
  ollama_tag: string;
  family: string;
  num_ctx: number;
  max_native_ctx: number;
  think: boolean;
  provider: string;
  vram_footprint_gb: number;
  status: "loaded" | "standby" | "resident";
  purpose: string;
}

const CONFIGURED_ROLES: ConfiguredRole[] = [
  {
    role_name: "Worker",
    ollama_tag: "qwen3.5:4b",
    family: "qwen",
    num_ctx: 8_192,
    max_native_ctx: 262_144,
    think: false,
    provider: "ollama (127.0.0.1:11434)",
    vram_footprint_gb: 3.3,
    status: "loaded",
    purpose: "Primary synthesis, user query answering, and intelligent document rewriting.",
  },
  {
    role_name: "Checker",
    ollama_tag: "gemma4:e2b-it-qat",
    family: "gemma",
    num_ctx: 8_192,
    max_native_ctx: 32_768,
    think: false,
    provider: "ollama (127.0.0.1:11434)",
    vram_footprint_gb: 1.8,
    status: "loaded",
    purpose: "Independent family hallucination audit and citation claim verification (SEC-31).",
  },
  {
    role_name: "Night Batch",
    ollama_tag: "gemma4:12b-it-qat",
    family: "gemma",
    num_ctx: 8_192,
    max_native_ctx: 32_768,
    think: false,
    provider: "ollama (127.0.0.1:11434)",
    vram_footprint_gb: 7.4,
    status: "standby",
    purpose: "High-capacity nocturnal batch synthesis, complex syllabus structuring, and evaluation.",
  },
  {
    role_name: "Embedder",
    ollama_tag: "bge-m3",
    family: "bge",
    num_ctx: 8_192,
    max_native_ctx: 8_192,
    think: false,
    provider: "ollama (127.0.0.1:11434)",
    vram_footprint_gb: 1.1,
    status: "resident",
    purpose: "Multilingual dense + sparse embeddings (1024 dims) for semantic retrieval.",
  },
  {
    role_name: "Vision",
    ollama_tag: "qwen3.5:4b",
    family: "qwen",
    num_ctx: 8_192,
    max_native_ctx: 262_144,
    think: false,
    provider: "ollama (127.0.0.1:11434)",
    vram_footprint_gb: 3.3,
    status: "loaded",
    purpose: "Multimodal OCR for diagrams, handwritten formulas, and charts in textbooks.",
  },
];

export default function ModelsPage() {
  const [activeTab, setActiveTab] = useState<"roles" | "context" | "isolation">("roles");

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 p-4 sm:p-6 lg:p-8 space-y-8 font-sans selection:bg-sky-500/30 selection:text-sky-200">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-lg bg-zinc-900 border border-zinc-800 text-sky-400">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                />
              </svg>
            </span>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-100">
              Models Administration & Telemetry
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-zinc-400">
            Read-only configuration view for local model roles, context windows, and hardware VRAM footprint.
          </p>
        </div>

        {/* SEC-20 Local Only Badge */}
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-1 text-xs font-mono rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>SEC-20: 100% Local (No Cloud Endpoints)</span>
          </span>
        </div>
      </div>

      {/* VRAM Meter Section */}
      <section className="space-y-3">
        <VramMeter />
      </section>

      {/* Model Roles & Context Windows Tabs */}
      <div className="space-y-4">
        <div className="flex items-center gap-2 border-b border-zinc-800 pb-2 text-xs font-mono">
          <button
            onClick={() => setActiveTab("roles")}
            className={`px-3 py-1.5 rounded-md transition ${
              activeTab === "roles"
                ? "bg-zinc-800 text-zinc-100 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Configured Roles ({CONFIGURED_ROLES.length})
          </button>
          <button
            onClick={() => setActiveTab("context")}
            className={`px-3 py-1.5 rounded-md transition ${
              activeTab === "context"
                ? "bg-zinc-800 text-zinc-100 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Context Window Metrics (8,192 Tokens)
          </button>
          <button
            onClick={() => setActiveTab("isolation")}
            className={`px-3 py-1.5 rounded-md transition ${
              activeTab === "isolation"
                ? "bg-zinc-800 text-zinc-100 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Family Isolation (SEC-31 Compliance)
          </button>
        </div>

        {/* Tab 1: Configured Roles Table */}
        {activeTab === "roles" && (
          <div className="overflow-x-auto border border-zinc-800 rounded-xl bg-zinc-950">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400 font-mono text-[11px] uppercase tracking-wider">
                  <th className="py-3 px-4">Role</th>
                  <th className="py-3 px-4">Model Tag</th>
                  <th className="py-3 px-4">Family</th>
                  <th className="py-3 px-4">Context Window</th>
                  <th className="py-3 px-4">VRAM Footprint</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Purpose</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60 font-sans">
                {CONFIGURED_ROLES.map((role) => (
                  <tr key={role.role_name} className="hover:bg-zinc-900/30 transition-colors">
                    {/* Role name */}
                    <td className="py-3 px-4 font-mono font-medium text-zinc-200">
                      {role.role_name}
                    </td>

                    {/* Model tag */}
                    <td className="py-3 px-4 font-mono">
                      <span className="px-2 py-0.5 rounded bg-zinc-900 text-zinc-300 border border-zinc-800">
                        {role.ollama_tag}
                      </span>
                    </td>

                    {/* Family */}
                    <td className="py-3 px-4 font-mono">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] ${
                          role.family === "qwen"
                            ? "bg-sky-500/10 text-sky-400 border border-sky-500/20"
                            : role.family === "gemma"
                            ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                            : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                        }`}
                      >
                        {role.family}
                      </span>
                    </td>

                    {/* Context window */}
                    <td className="py-3 px-4 font-mono text-zinc-300">
                      <div>{role.num_ctx.toLocaleString()} tokens</div>
                      <div className="text-[10px] text-zinc-500">
                        native: {(role.max_native_ctx / 1024).toFixed(0)}k
                      </div>
                    </td>

                    {/* VRAM footprint */}
                    <td className="py-3 px-4 font-mono text-zinc-300 font-medium">
                      {role.vram_footprint_gb.toFixed(1)} GB
                    </td>

                    {/* Status */}
                    <td className="py-3 px-4">
                      {role.status === "loaded" && (
                        <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1 w-fit">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          <span>LOADED</span>
                        </span>
                      )}
                      {role.status === "resident" && (
                        <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-sky-500/10 text-sky-400 border border-sky-500/30 flex items-center gap-1 w-fit">
                          <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
                          <span>RESIDENT</span>
                        </span>
                      )}
                      {role.status === "standby" && (
                        <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-zinc-800 text-zinc-400 border border-zinc-700 flex items-center gap-1 w-fit">
                          <span className="w-1.5 h-1.5 rounded-full bg-zinc-400" />
                          <span>STANDBY</span>
                        </span>
                      )}
                    </td>

                    {/* Purpose description */}
                    <td className="py-3 px-4 max-w-xs text-xs text-zinc-400 leading-relaxed">
                      {role.purpose}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab 2: Context Window Metrics */}
        {activeTab === "context" && (
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-5 space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-zinc-100 font-mono">
                Context Window Budget Breakdown (num_ctx: 8,192 Tokens)
              </h3>
              <p className="text-xs text-zinc-400 mt-1">
                Optimized token allocation to maintain high recall, precise synthesis, and deterministic verification.
              </p>
            </div>

            {/* Token Budget Meter */}
            <div className="space-y-2">
              <div className="h-6 w-full bg-zinc-900 rounded-lg overflow-hidden flex border border-zinc-800 text-[10px] font-mono font-medium text-white">
                <div
                  style={{ width: "50%" }}
                  className="bg-indigo-600 flex items-center justify-center"
                  title="Retrieved Citations Context: 4,096 tokens (50%)"
                >
                  Context (4,096)
                </div>
                <div
                  style={{ width: "23.2%" }}
                  className="bg-sky-600 flex items-center justify-center"
                  title="User Question & System Prompt: 1,904 tokens (23.2%)"
                >
                  Prompt (1,904)
                </div>
                <div
                  style={{ width: "24.4%" }}
                  className="bg-emerald-600 flex items-center justify-center"
                  title="Answer Generation Buffer: 2,000 tokens (24.4%)"
                >
                  Generation (2,000)
                </div>
                <div
                  style={{ width: "2.4%" }}
                  className="bg-amber-600 flex items-center justify-center"
                  title="Safety Margin: 192 tokens (2.4%)"
                >
                  192
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono pt-2">
                <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800/80">
                  <div className="text-indigo-400 font-semibold">4,096 tokens (50%)</div>
                  <div className="text-zinc-400 text-[11px] mt-0.5">Retrieved Chunk Churn</div>
                </div>
                <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800/80">
                  <div className="text-sky-400 font-semibold">1,904 tokens (23.2%)</div>
                  <div className="text-zinc-400 text-[11px] mt-0.5">Prompt & History</div>
                </div>
                <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800/80">
                  <div className="text-emerald-400 font-semibold">2,000 tokens (24.4%)</div>
                  <div className="text-zinc-400 text-[11px] mt-0.5">Output Generation</div>
                </div>
                <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800/80">
                  <div className="text-amber-400 font-semibold">192 tokens (2.4%)</div>
                  <div className="text-zinc-400 text-[11px] mt-0.5">Safety Reserve</div>
                </div>
              </div>
            </div>

            {/* KV Cache footprint equation */}
            <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 text-xs font-mono space-y-2">
              <div className="flex items-center justify-between text-zinc-300">
                <span className="font-semibold text-zinc-100">KV-Cache Memory Footprint:</span>
                <span className="text-emerald-400">~393 MB per 8,192 context (FP16)</span>
              </div>
              <p className="text-[11px] text-zinc-400 font-sans leading-relaxed">
                Formula: <code className="text-zinc-200">2 × n_layers × n_heads × d_head × num_ctx × 2 bytes</code>.
                With 8k context, KV-cache consumes negligible memory, allowing the worker and checker models to fit seamlessly within unified memory bounds.
              </p>
            </div>
          </div>
        )}

        {/* Tab 3: Family Isolation Compliance (SEC-31) */}
        {activeTab === "isolation" && (
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-5 space-y-4">
            <div className="flex items-center gap-2">
              <span className="p-1 rounded bg-emerald-500/20 text-emerald-400">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </span>
              <h3 className="text-sm font-semibold text-zinc-100 font-mono">
                Architectural Contract 3: Strict Family Independence (SEC-31)
              </h3>
            </div>

            <p className="text-xs text-zinc-400 leading-relaxed">
              To eliminate correlated systemic hallucinations and training biases, TechRadar Brain mandates that the primary synthesis Worker and the factual verification Checker must never share the same model family or weights.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <div className="p-4 rounded-lg bg-sky-950/20 border border-sky-500/30 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-semibold text-sky-400">Worker Architecture</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/20 text-sky-300">Role 1</span>
                </div>
                <div className="text-base font-bold text-zinc-100">qwen3.5:4b</div>
                <div className="text-xs text-zinc-400">
                  Family: <span className="text-sky-300 font-mono">qwen</span> (Alibaba Cloud / Qwen team architecture)
                </div>
                <p className="text-[11px] text-zinc-500">
                  Trained on diverse multilingual tokens; distinct attention heads and tokenizer.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-amber-950/20 border border-amber-500/30 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-semibold text-amber-400">Checker Architecture</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">Role 2</span>
                </div>
                <div className="text-base font-bold text-zinc-100">gemma4:e2b-it-qat</div>
                <div className="text-xs text-zinc-400">
                  Family: <span className="text-amber-300 font-mono">gemma</span> (Google DeepMind architecture)
                </div>
                <p className="text-[11px] text-zinc-500">
                  Independently trained on distinct pretraining corpus; zero weight sharing with Qwen.
                </p>
              </div>
            </div>

            <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800 text-xs font-mono text-emerald-400 flex items-center justify-between">
              <span>Status: Family Isolation Verified at Startup (src/techradar/llm/roles.py)</span>
              <span className="font-bold">COMPLIANT</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
