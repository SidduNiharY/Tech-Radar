"use client";

/**
 * Visual VRAM allocation meter for local model orchestration.
 * Displays concurrent memory footprints vs GPU budget with headroom and overflow alerts.
 * Spec: 02 §5.14, 03 §Local Models, 05 §3.
 */

import React, { useState, useMemo } from "react";

export interface HardwarePreset {
  id: string;
  name: string;
  category: "laptop" | "apple" | "workstation";
  budget_mb: number;
  description: string;
}

export const HARDWARE_PRESETS: HardwarePreset[] = [
  {
    id: "laptop_6gb",
    name: "6 GB Laptop GPU",
    category: "laptop",
    budget_mb: 6_144,
    description: "NVIDIA RTX 3060 / 4050 Mobile (6GB VRAM)",
  },
  {
    id: "apple_16gb",
    name: "16 GB Apple Silicon",
    category: "apple",
    budget_mb: 16_384,
    description: "MacBook Pro M2 / M3 / M4 Unified Memory (16GB)",
  },
  {
    id: "workstation_24gb",
    name: "24 GB Workstation",
    category: "workstation",
    budget_mb: 24_576,
    description: "RTX 3090 / 4090 / Mac Studio (24GB VRAM)",
  },
];

export interface ModelFootprint {
  role: "worker" | "checker" | "embedder" | "overhead";
  name: string;
  model_tag: string;
  family: string;
  footprint_mb: number;
  color_class: string;
  hex_color: string;
  description: string;
}

export const DEFAULT_FOOTPRINTS: ModelFootprint[] = [
  {
    role: "worker",
    name: "Worker Agent",
    model_tag: "qwen3.5:4b",
    family: "qwen",
    footprint_mb: 3_380, // ~3.3 GB
    color_class: "bg-sky-500",
    hex_color: "#0ea5e9",
    description: "Primary reasoning, answer drafting, and query rewriting",
  },
  {
    role: "checker",
    name: "Fact Checker",
    model_tag: "gemma4:e2b-it-qat",
    family: "gemma",
    footprint_mb: 1_840, // ~1.8 GB
    color_class: "bg-amber-500",
    hex_color: "#f59e0b",
    description: "Independent family verification and citation hallucination auditor",
  },
  {
    role: "embedder",
    name: "Dense Embedder",
    model_tag: "bge-m3",
    family: "bge",
    footprint_mb: 1_120, // ~1.1 GB
    color_class: "bg-purple-500",
    hex_color: "#a855f7",
    description: "1024-dim dense vector representations and chunk indexing",
  },
  {
    role: "overhead",
    name: "KV-Cache & System",
    model_tag: "8k-context-kv",
    family: "system",
    footprint_mb: 450, // ~0.45 GB
    color_class: "bg-emerald-500",
    hex_color: "#10b981",
    description: "Active context window KV-cache and CUDA/Metal runtime buffers",
  },
];

export function VramMeter() {
  const [selectedPresetId, setSelectedPresetId] = useState<string>("laptop_6gb");
  const [isConcurrent, setIsConcurrent] = useState<boolean>(true);

  const currentPreset = useMemo(
    () =>
      HARDWARE_PRESETS.find((p) => p.id === selectedPresetId) ||
      HARDWARE_PRESETS[0],
    [selectedPresetId]
  );

  const budgetMb = currentPreset.budget_mb;

  // Compute memory footprints based on execution mode
  const { totalUsedMb, activeFootprints, isOverflow, overflowMb, headroomMb } =
    useMemo(() => {
      let used = 0;
      let activeList: ModelFootprint[] = [];

      if (isConcurrent) {
        // All models resident simultaneously
        used = DEFAULT_FOOTPRINTS.reduce((sum, f) => sum + f.footprint_mb, 0);
        activeList = [...DEFAULT_FOOTPRINTS];
      } else {
        // Sequential offloading: worker runs, then checker runs
        const worker = DEFAULT_FOOTPRINTS.find((f) => f.role === "worker")!;
        const checker = DEFAULT_FOOTPRINTS.find((f) => f.role === "checker")!;
        const embedder = DEFAULT_FOOTPRINTS.find((f) => f.role === "embedder")!;
        const overhead = DEFAULT_FOOTPRINTS.find((f) => f.role === "overhead")!;

        const peakLlm = Math.max(worker.footprint_mb, checker.footprint_mb);
        used = peakLlm + embedder.footprint_mb + overhead.footprint_mb;

        activeList = [
          {
            ...worker,
            name: "Worker (Sequential Peak)",
            footprint_mb: peakLlm,
          },
          embedder,
          overhead,
        ];
      }

      const overflow = used > budgetMb;
      const overflowVal = overflow ? used - budgetMb : 0;
      const headroomVal = overflow ? 0 : budgetMb - used;

      return {
        totalUsedMb: used,
        activeFootprints: activeList,
        isOverflow: overflow,
        overflowMb: overflowVal,
        headroomMb: headroomVal,
      };
    }, [isConcurrent, budgetMb]);

  const usedPercentage = Math.min((totalUsedMb / budgetMb) * 100, 100);
  const overflowPercentage = isOverflow
    ? Math.min((overflowMb / budgetMb) * 100, 40)
    : 0;

  return (
    <div className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-5 space-y-6">
      {/* Top Header & Mode Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-md bg-zinc-900 border border-zinc-800 text-sky-400">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
            </span>
            <h3 className="text-sm font-semibold text-zinc-100 uppercase tracking-wider font-mono">
              VRAM Allocation & Budget Telemetry
            </h3>
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Real-time memory footprints of local SLMs against GPU / Unified Memory budget.
          </p>
        </div>

        {/* Execution Mode Selector */}
        <div className="flex items-center gap-1.5 bg-zinc-900/80 p-1 rounded-lg border border-zinc-800 shrink-0 text-xs font-mono">
          <button
            type="button"
            onClick={() => setIsConcurrent(true)}
            className={`px-3 py-1 rounded transition ${
              isConcurrent
                ? "bg-zinc-800 text-zinc-100 font-medium shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Concurrent Mode
          </button>
          <button
            type="button"
            onClick={() => setIsConcurrent(false)}
            className={`px-3 py-1 rounded transition ${
              !isConcurrent
                ? "bg-zinc-800 text-zinc-100 font-medium shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Sequential Offload
          </button>
        </div>
      </div>

      {/* Hardware Budget Presets */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {HARDWARE_PRESETS.map((preset) => {
          const isSelected = preset.id === selectedPresetId;
          return (
            <button
              key={preset.id}
              type="button"
              onClick={() => setSelectedPresetId(preset.id)}
              className={`p-3 rounded-lg border text-left transition-all ${
                isSelected
                  ? "bg-zinc-900 border-zinc-700 ring-1 ring-zinc-600 shadow-md"
                  : "bg-zinc-950/60 border-zinc-800/80 hover:bg-zinc-900/40 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-200">
                  {preset.name}
                </span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                    isSelected
                      ? "bg-sky-500/20 text-sky-400 border border-sky-500/30"
                      : "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {(preset.budget_mb / 1024).toFixed(0)} GB
                </span>
              </div>
              <p className="text-[11px] text-zinc-500 mt-1 line-clamp-1">
                {preset.description}
              </p>
            </button>
          );
        })}
      </div>

      {/* Visual Segmented Progress Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="text-zinc-400">Total Allocation:</span>
            <span
              className={`font-semibold ${
                isOverflow ? "text-rose-400" : "text-emerald-400"
              }`}
            >
              {(totalUsedMb / 1024).toFixed(2)} GB / {(budgetMb / 1024).toFixed(1)} GB
            </span>
            <span className="text-zinc-500">
              ({((totalUsedMb / budgetMb) * 100).toFixed(1)}%)
            </span>
          </div>

          <div className="flex items-center gap-2">
            {isOverflow ? (
              <span className="text-rose-400 font-semibold flex items-center gap-1">
                <svg className="w-3.5 h-3.5 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                Overflow: +{(overflowMb / 1024).toFixed(2)} GB
              </span>
            ) : (
              <span className="text-emerald-400 font-semibold flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Headroom: {(headroomMb / 1024).toFixed(2)} GB free
              </span>
            )}
          </div>
        </div>

        {/* Progress Track */}
        <div className="h-4 w-full bg-zinc-900 rounded-full overflow-hidden flex border border-zinc-800 relative">
          {activeFootprints.map((item) => {
            const widthPct = Math.min((item.footprint_mb / budgetMb) * 100, 100);
            return (
              <div
                key={item.role}
                style={{ width: `${widthPct}%` }}
                className={`h-full ${item.color_class} transition-all duration-300 relative group`}
                title={`${item.name} (${item.model_tag}): ${(item.footprint_mb / 1024).toFixed(2)} GB`}
              />
            );
          })}

          {/* Overflow Bar Segment if exceeding 100% */}
          {isOverflow && (
            <div
              style={{ width: `${overflowPercentage}%` }}
              className="h-full bg-rose-500 animate-pulse transition-all duration-300"
              title={`Overflow: +${(overflowMb / 1024).toFixed(2)} GB exceeding budget!`}
            />
          )}
        </div>
      </div>

      {/* Overflow Alert or Headroom Banner */}
      {isOverflow ? (
        <div className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 space-y-1 animate-fadeIn">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-rose-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="text-xs font-semibold uppercase tracking-wider font-mono">
              VRAM Overflow Alert: {(overflowMb / 1024).toFixed(2)} GB Deficit
            </span>
          </div>
          <p className="text-xs text-rose-400/90 leading-relaxed pl-6 font-sans">
            Concurrent memory footprint ({(totalUsedMb / 1024).toFixed(2)} GB) exceeds the {currentPreset.name} limit ({(budgetMb / 1024).toFixed(1)} GB).
            Concurrent worker + checker execution will cause out-of-memory paging or inference termination.
            Toggle <span className="font-semibold text-rose-200">Sequential Offload</span> to keep memory bounded at {(4950 / 1024).toFixed(2)} GB, or select the 16 GB Apple Silicon preset.
          </p>
        </div>
      ) : (
        <div className="p-3.5 rounded-lg bg-emerald-950/20 border border-emerald-500/30 text-emerald-300 space-y-1">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-xs font-semibold uppercase tracking-wider font-mono">
              Safe Headroom Margin: {(headroomMb / 1024).toFixed(2)} GB Available
            </span>
          </div>
          <p className="text-xs text-emerald-400/80 leading-relaxed pl-6 font-sans">
            Footprint is safely within hardware budget with {((headroomMb / budgetMb) * 100).toFixed(1)}% free buffer.
            Comfortably accommodates 8k context window KV-caches and multi-candidate generation without host RAM spillover.
          </p>
        </div>
      )}

      {/* Footprint Breakdown Legend Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-2">
        {DEFAULT_FOOTPRINTS.map((footprint) => {
          return (
            <div
              key={footprint.role}
              className="p-3 rounded-lg bg-zinc-900/40 border border-zinc-800/80 space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${footprint.color_class}`} />
                  <span className="text-xs font-medium text-zinc-300">
                    {footprint.name}
                  </span>
                </div>
                <span className="text-[11px] font-mono text-zinc-400">
                  {(footprint.footprint_mb / 1024).toFixed(2)} GB
                </span>
              </div>
              <div className="text-[11px] font-mono text-zinc-500">
                tag: <span className="text-zinc-300">{footprint.model_tag}</span>
              </div>
              <p className="text-[10px] text-zinc-500 leading-tight">
                {footprint.description}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default VramMeter;
