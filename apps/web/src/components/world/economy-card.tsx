"use client";

import React, { useState } from "react";

export interface MacroIndicator {
  key: string;
  name: string;
  alias: string;
  value: number;
  unit: string;
  prefix?: string;
  delta: string;
  deltaType: "positive" | "negative" | "neutral";
  benchmark: string;
  description: string;
  category: "Monetary Policy" | "Price Stability" | "Growth" | "Forex";
}

export interface EconomyCardProps {
  indicator: MacroIndicator;
  lastUpdated?: string;
  onSelectIndicator?: (indicator: MacroIndicator) => void;
}

export interface EconomyIndicatorGridProps {
  lastUpdated?: string;
  onIndicatorChange?: (key: string, newValue: number) => void;
  className?: string;
}

export const BASELINE_INDICATORS: MacroIndicator[] = [
  {
    key: "repo_rate_pct",
    name: "RBI Repo Rate",
    alias: "repo_rate",
    value: 6.5,
    unit: "%",
    delta: "0.0% unchanged",
    deltaType: "neutral",
    benchmark: "Neutral Stance",
    description: "Benchmark rate at which RBI lends short-term liquidity to commercial banks.",
    category: "Monetary Policy",
  },
  {
    key: "reverse_repo_rate_pct",
    name: "Reverse Repo Rate",
    alias: "reverse_repo_rate",
    value: 3.35,
    unit: "%",
    delta: "0.0% unchanged",
    deltaType: "neutral",
    benchmark: "SDF Floor: 6.25%",
    description: "Rate at which RBI absorbs surplus liquidity from domestic banks under LAF.",
    category: "Monetary Policy",
  },
  {
    key: "cpi_inflation_pct",
    name: "CPI Inflation",
    alias: "cpi_inflation",
    value: 5.1,
    unit: "%",
    delta: "-0.3% MoM",
    deltaType: "positive", // Easing inflation is positive
    benchmark: "Target: 4.0% ± 2%",
    description: "Consumer Price Index measuring retail basket price trajectory across urban/rural goods.",
    category: "Price Stability",
  },
  {
    key: "gdp_growth_pct",
    name: "Annual GDP Growth",
    alias: "gdp_growth",
    value: 7.2,
    unit: "%",
    delta: "+0.4% YoY",
    deltaType: "positive",
    benchmark: "RBI FY27 Est: 7.0%",
    description: "Real Gross Domestic Product expansion driven by capital formation and manufacturing.",
    category: "Growth",
  },
  {
    key: "usd_inr_rate",
    name: "USD / INR Exchange Rate",
    alias: "usd_inr",
    value: 84.0,
    unit: "",
    prefix: "₹",
    delta: "+₹0.15 MoM",
    deltaType: "neutral",
    benchmark: "FX Reserves: $692B",
    description: "Spot exchange rate between the United States Dollar and the Indian Rupee.",
    category: "Forex",
  },
];

export function EconomyCard({
  indicator,
  lastUpdated,
  onSelectIndicator,
}: EconomyCardProps) {
  const deltaBadgeClass =
    indicator.deltaType === "positive"
      ? "bg-emerald-950/70 text-emerald-400 border-emerald-500/40 shadow-[0_0_12px_rgba(16,185,129,0.15)]"
      : indicator.deltaType === "negative"
        ? "bg-rose-950/70 text-rose-400 border-rose-500/40"
        : "bg-zinc-900/80 text-zinc-400 border-zinc-700/60";

  return (
    <div
      data-testid={`economy-card-${indicator.alias}`}
      onClick={() => onSelectIndicator?.(indicator)}
      className="group relative rounded-xl border border-zinc-800/80 bg-[#090a0f]/90 p-5 backdrop-blur-md transition-all duration-300 hover:border-violet-500/50 hover:shadow-[0_0_25px_rgba(139,92,246,0.12)] cursor-pointer"
    >
      {/* Top Hairline Violet Accent */}
      <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-violet-500/30 to-transparent" />

      {/* Header: Category & Change Delta Tag */}
      <div className="flex items-center justify-between gap-2 mb-2 font-mono text-xs">
        <span className="text-[11px] text-zinc-500 uppercase tracking-wider">
          {indicator.category}
        </span>

        {/* Change Delta Tag */}
        <span
          data-testid="indicator-delta-tag"
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded font-mono text-[11px] font-semibold border ${deltaBadgeClass}`}
        >
          {indicator.deltaType === "positive" && <span>▼</span>}
          {indicator.deltaType === "negative" && <span>▲</span>}
          {indicator.delta}
        </span>
      </div>

      {/* Metric Name */}
      <h4 className="text-sm font-medium text-zinc-300 group-hover:text-violet-200 transition-colors">
        {indicator.name}
      </h4>

      {/* Metric Value */}
      <div className="mt-2 flex items-baseline gap-1.5">
        {indicator.prefix && (
          <span className="font-mono text-xl font-bold text-zinc-400">
            {indicator.prefix}
          </span>
        )}
        <span
          data-testid="indicator-value"
          className="font-mono text-3xl font-extrabold tracking-tight text-white group-hover:text-violet-300 transition-colors"
        >
          {indicator.value.toFixed(indicator.key === "usd_inr_rate" ? 2 : 2)}
        </span>
        {indicator.unit && (
          <span className="font-mono text-lg font-semibold text-zinc-400">
            {indicator.unit}
          </span>
        )}
      </div>

      {/* Benchmark & Target */}
      <div className="mt-3 pt-3 border-t border-zinc-900 flex items-center justify-between text-[11px] font-mono text-zinc-500">
        <span>{indicator.benchmark}</span>
        {lastUpdated && <span>Updated: {lastUpdated}</span>}
      </div>
    </div>
  );
}

export function EconomyCardGrid({
  lastUpdated = "2026-11-08 12:00:00 UTC",
  onIndicatorChange,
  className = "",
}: EconomyIndicatorGridProps) {
  const [indicators, setIndicators] = useState<MacroIndicator[]>(BASELINE_INDICATORS);
  const [activeModalIndicator, setActiveModalIndicator] = useState<MacroIndicator | null>(null);
  const [simulatedValue, setSimulatedValue] = useState<string>("");

  const handleOpenModal = (ind: MacroIndicator) => {
    setActiveModalIndicator(ind);
    setSimulatedValue(ind.value.toString());
  };

  const handleSaveSimulation = () => {
    if (!activeModalIndicator) return;
    const num = parseFloat(simulatedValue);
    if (!isNaN(num) && num >= 0) {
      setIndicators((prev) =>
        prev.map((ind) =>
          ind.key === activeModalIndicator.key ? { ...ind, value: num, delta: "Simulated" } : ind
        )
      );
      onIndicatorChange?.(activeModalIndicator.key, num);
      setActiveModalIndicator(null);
    }
  };

  return (
    <section className={`space-y-4 ${className}`} data-testid="economy-card-grid">
      {/* Section Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
          <h3 className="font-mono text-xs uppercase tracking-wider font-semibold text-zinc-300">
            Macroeconomic Indicator Dashboard
          </h3>
          <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
            RBI MPC Baseline
          </span>
        </div>

        {/* Timestamp */}
        <div
          data-testid="economy-timestamp"
          className="font-mono text-xs text-zinc-400 flex items-center gap-2"
        >
          <span className="text-zinc-600">Last Synced:</span>
          <span className="px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300">
            {lastUpdated}
          </span>
        </div>
      </div>

      {/* Grid of 5 Macroeconomic Indicator Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {indicators.map((ind) => (
          <EconomyCard
            key={ind.key}
            indicator={ind}
            lastUpdated={lastUpdated.split(" ")[0]}
            onSelectIndicator={handleOpenModal}
          />
        ))}
      </div>

      {/* Detail / Simulation Modal */}
      {activeModalIndicator && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
        >
          <div className="relative w-full max-w-md rounded-xl border border-zinc-700 bg-[#0c0d14] p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4 pb-2 border-b border-zinc-800">
              <h4 className="font-mono text-sm font-semibold text-violet-300">
                Macro Variable Inspector: {activeModalIndicator.name}
              </h4>
              <button
                type="button"
                onClick={() => setActiveModalIndicator(null)}
                className="text-zinc-500 hover:text-white font-mono text-sm"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-zinc-300 leading-relaxed mb-4">
              {activeModalIndicator.description}
            </p>

            <div className="space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between py-1.5 border-b border-zinc-800">
                <span className="text-zinc-500">Official Alias:</span>
                <span className="text-zinc-200">{activeModalIndicator.alias}</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-zinc-800">
                <span className="text-zinc-500">Benchmark Floor:</span>
                <span className="text-zinc-200">{activeModalIndicator.benchmark}</span>
              </div>
              <div className="flex items-center justify-between py-1.5 border-b border-zinc-800">
                <span className="text-zinc-500">Current Delta:</span>
                <span className="text-emerald-400">{activeModalIndicator.delta}</span>
              </div>

              {/* Simulation input */}
              <div className="pt-2">
                <label className="block text-zinc-400 mb-1">
                  Simulate Stress-Test Value ({activeModalIndicator.unit || activeModalIndicator.prefix}):
                </label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    step="0.05"
                    value={simulatedValue}
                    onChange={(e) => setSimulatedValue(e.target.value)}
                    className="w-full rounded bg-zinc-950 border border-zinc-700 px-3 py-1.5 text-zinc-100 font-mono text-sm focus:border-violet-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleSaveSimulation}
                    className="px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500 text-white font-mono text-xs font-semibold whitespace-nowrap"
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setActiveModalIndicator(null)}
                className="px-4 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700 font-mono text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
