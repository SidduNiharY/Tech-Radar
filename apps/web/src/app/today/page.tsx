"use client";

import React, { useState } from "react";
import { BriefingCard, type BriefingStory } from "@/components/today/briefing-card";
import { OpinionLogger } from "@/components/today/opinion-logger";

const SAMPLE_BRIEFINGS: BriefingStory[] = [
  {
    id: 101,
    cluster_id: "cluster_tech_001",
    title: "DeepSeek V3 Open Weights and Speculative Decoding Breakthroughs",
    section: "Tech",
    domains: ["huggingface.co", "arxiv.org", "github.com", "semiengineering.com"],
    domain_count: 4,
    verified_headline: true,
    why: "Dual-pipe parallelism and multi-token prediction lower inference VRAM requirements by 3.2x, enabling 671B MoE reasoning models on commodity workstation nodes.",
    how_it_affects_me: "Local Ollama host cluster can run quantized teacher models with high throughput without cloud GPU API egress charges.",
    exam_tags: ["AI Infra", "CS Systems"],
    relevance: 0.94,
    summary: "New architecture demonstrates competitive MMLU and coding benchmarks against frontier closed labs with pure open-weights inference recipes.",
  },
  {
    id: 102,
    cluster_id: "cluster_india_002",
    title: "RBI Monetary Policy Committee Maintains Repo Rate at 6.50% Amid Food Price Stabalization",
    section: "India",
    domains: ["rbi.org.in", "thehindu.com", "reuters.com"],
    domain_count: 3,
    verified_headline: true,
    why: "Inflation projection for FY27 anchored around 4.5% while robust 7.2% GDP growth trajectory offers policy space to maintain neutral stance.",
    how_it_affects_me: "Fixed income yields and mortgage interest expense rates remain locked at current plateaus through upcoming quarter.",
    exam_tags: ["UPSC GS-3", "Macroeconomics"],
    relevance: 0.88,
    summary: "Governor highlights resilient domestic demand dynamics while remaining vigilant on geopolitical energy transmission and food supply volatility.",
  },
  {
    id: 103,
    cluster_id: "cluster_world_003",
    title: "Global Semiconductor Supply Alliance Finalizes Advanced Packaging Standards",
    section: "World",
    domains: ["eetimes.com", "nikkei.com", "ft.com"],
    domain_count: 3,
    verified_headline: true,
    why: "Chiplet interconnect standard UCIe 2.0 harmonizes die-to-die interfaces across TSMC, Intel, and Samsung foundries.",
    how_it_affects_me: "Heterogeneous multi-vendor system-on-package architectures will lower the entry barrier for custom accelerator silicon.",
    exam_tags: ["Geopolitics", "Semiconductors"],
    relevance: 0.82,
    summary: "Standardization reduces packaging lead times by 28% and guarantees cross-foundry modular interoperability for next-gen datacenter accelerators.",
  },
  {
    id: 104,
    cluster_id: "cluster_econ_004",
    title: "India Q2 GDP Growth Accelerates to 7.2% Driven by Manufacturing & Capital Formation",
    section: "Economy",
    domains: ["mospi.gov.in", "bloomberg.com", "livemint.com"],
    domain_count: 3,
    verified_headline: true,
    why: "Gross fixed capital formation expanded by 9.4% year-on-year, confirming sustained private capex turnaround and public infrastructure push.",
    how_it_affects_me: "Broadened corporate earnings resilience bolsters domestic investment confidence and tech engineering hiring pipelines.",
    exam_tags: ["UPSC GS-3", "Indian Economy"],
    relevance: 0.91,
    summary: "Manufacturing value-add rose 8.1% with structural expansion in electronic components, automotive, and capital goods export segments.",
  },
  {
    id: 105,
    cluster_id: "cluster_sci_005",
    title: "ISRO Gaganyaan Environmental Control Life Support Testing Crosses Key Benchmark",
    section: "Science",
    domains: ["isro.gov.in", "pib.gov.in", "nature.com"],
    domain_count: 3,
    verified_headline: true,
    why: "Human crew module cabin pressure, thermal loop redundancy, and carbon dioxide scrubbers operated continuously without telemetry drift for 72 hours.",
    how_it_affects_me: "Validates indigenous aerospace life support supply chain readiness for planned uncrewed test flight.",
    exam_tags: ["Space Tech", "Science & Tech"],
    relevance: 0.79,
    summary: "Successful milestone clears integration path for final integrated air-drop recovery test before orbital human-rated launch certification.",
  },
];

type EnergyLevel = "high" | "medium" | "low";

const ENERGY_OPTIONS: Record<
  EnergyLevel,
  { label: string; icon: string; focus: string; time: string; badge: string }
> = {
  high: {
    label: "High Energy",
    icon: "⚡",
    focus: "Deep Dive Architecture // 90m RAG Practice & Complex MCQs",
    time: "90 min target",
    badge: "bg-violet-950/70 text-violet-300 border-violet-500/40",
  },
  medium: {
    label: "Moderate Energy",
    icon: "🔋",
    focus: "Core Review // 45m Macroeconomics & 20 Active Flashcards",
    time: "45 min target",
    badge: "bg-emerald-950/70 text-emerald-300 border-emerald-500/40",
  },
  low: {
    label: "Recharge Energy",
    icon: "🌙",
    focus: "Rapid Briefing Scan // 15m Audio Briefing & Terminology Check",
    time: "15 min target",
    badge: "bg-amber-950/70 text-amber-300 border-amber-500/40",
  },
};

export default function TodayScreenPage() {
  const [selectedSection, setSelectedSection] = useState<string>("All");
  const [energy, setEnergy] = useState<EnergyLevel>("high");
  const [activeStoryForTake, setActiveStoryForTake] = useState<BriefingStory>(SAMPLE_BRIEFINGS[0]);
  const [submittedTakesCount, setSubmittedTakesCount] = useState<number>(0);

  const sections = ["All", "Tech", "India", "World", "Economy", "Science"];

  const filteredItems =
    selectedSection === "All"
      ? SAMPLE_BRIEFINGS
      : SAMPLE_BRIEFINGS.filter(
          (item) => item.section.toLowerCase() === selectedSection.toLowerCase()
        );

  const handleSelectTake = (item: BriefingStory) => {
    setActiveStoryForTake(item);
    // Smooth scroll down to the opinion logger
    if (typeof document !== "undefined") {
      const el = document.getElementById("opinion-logger-section");
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  const handleTakeSubmitted = () => {
    setSubmittedTakesCount((c) => c + 1);
  };

  return (
    <div className="min-h-screen bg-[#07080c] text-zinc-100 font-sans antialiased pb-20 selection:bg-violet-600/30 selection:text-violet-200">
      {/* Background ambient gradient glow */}
      <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(120,119,198,0.12),rgba(255,255,255,0))]" />

      <div className="relative mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 pt-8 md:pt-12">
        {/* Top Cyber-Academic HUD Header */}
        <header className="mb-8 border-b border-zinc-800/80 pb-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1.5 font-mono text-xs">
                <span className="flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                <span className="text-zinc-400">TECHRADAR BRAIN</span>
                <span className="text-zinc-600">//</span>
                <span className="text-violet-400">SEC-27 VERIFIED FEED</span>
              </div>
              <h1 className="text-2xl sm:text-3xl md:text-4xl font-extrabold tracking-tight text-white">
                Today&apos;s Intelligence Briefing
              </h1>
              <p className="mt-1 font-mono text-xs sm:text-sm text-zinc-400">
                Sunday, November 8, 2026 · Cycle 06:00 IST · 5 Domains Synced
              </p>
            </div>

            {/* Live Status Tag */}
            <div className="flex flex-wrap items-center gap-2.5 font-mono text-xs">
              <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/80 px-3 py-1.5 backdrop-blur-md">
                <span className="text-zinc-500">Domains: </span>
                <span className="text-emerald-400 font-semibold">16 Verified</span>
              </div>
              <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/80 px-3 py-1.5 backdrop-blur-md">
                <span className="text-zinc-500">Takes: </span>
                <span className="text-violet-400 font-semibold">{submittedTakesCount} Logged</span>
              </div>
            </div>
          </div>

          {/* Daily Study Energy Prompt */}
          <section
            data-testid="energy-prompt"
            className="mt-6 rounded-xl border border-zinc-800/80 bg-[#0c0d14]/90 p-4 md:p-5 backdrop-blur-md"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-base">{ENERGY_OPTIONS[energy].icon}</span>
                  <h3 className="font-mono text-xs uppercase tracking-wider font-semibold text-zinc-300">
                    Daily Study Energy Calibration
                  </h3>
                </div>
                <p className="text-xs sm:text-sm text-zinc-400">
                  <span className="font-semibold text-zinc-200">Optimal Plan: </span>
                  {ENERGY_OPTIONS[energy].focus}
                </p>
              </div>

              {/* Energy Selector Buttons */}
              <div className="flex items-center gap-1.5 bg-zinc-900/90 p-1 rounded-lg border border-zinc-800">
                {(["high", "medium", "low"] as EnergyLevel[]).map((level) => {
                  const opt = ENERGY_OPTIONS[level];
                  const isSelected = energy === level;
                  return (
                    <button
                      key={level}
                      type="button"
                      onClick={() => setEnergy(level)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-mono transition-all ${
                        isSelected
                          ? "bg-violet-600 text-white shadow-md shadow-violet-950 font-medium"
                          : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
                      }`}
                    >
                      <span>{opt.icon}</span>
                      <span className="hidden md:inline">{opt.label.split(" ")[0]}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </section>
        </header>

        {/* Section Navigation Tabs */}
        <nav className="mb-6 flex items-center justify-between gap-4 overflow-x-auto pb-2 scrollbar-none border-b border-zinc-900">
          <div className="flex items-center gap-2">
            {sections.map((sec) => {
              const active = selectedSection === sec;
              return (
                <button
                  key={sec}
                  type="button"
                  onClick={() => setSelectedSection(sec)}
                  className={`rounded-lg px-3.5 py-1.5 font-mono text-xs transition-all whitespace-nowrap ${
                    active
                      ? "bg-violet-600/30 text-violet-300 border border-violet-500/50 shadow-[0_0_15px_rgba(139,92,246,0.2)] font-semibold"
                      : "bg-zinc-900/70 text-zinc-400 border border-zinc-800/60 hover:text-zinc-200 hover:border-zinc-700"
                  }`}
                >
                  {sec}
                </button>
              );
            })}
          </div>

          <span className="font-mono text-xs text-zinc-500 whitespace-nowrap hidden sm:inline">
            Showing {filteredItems.length} of {SAMPLE_BRIEFINGS.length} briefings
          </span>
        </nav>

        {/* Main Content Layout: Two-Column on Desktop */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Morning Briefing Cards List */}
          <main className="lg:col-span-7 space-y-5">
            {filteredItems.map((story) => (
              <BriefingCard
                key={story.id}
                item={story}
                defaultExpanded={true}
                onSelectTake={handleSelectTake}
              />
            ))}

            {filteredItems.length === 0 && (
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/60 p-8 text-center">
                <p className="font-mono text-sm text-zinc-400">
                  No briefing items found in section &ldquo;{selectedSection}&rdquo;.
                </p>
              </div>
            )}
          </main>

          {/* Right Column: Prediction Logger Sticky Sidebar */}
          <aside className="lg:col-span-5 space-y-6 lg:sticky lg:top-8">
            <div id="opinion-logger-section">
              <OpinionLogger
                briefingId="briefing_2026_11_08"
                messageId={activeStoryForTake.id}
                headline={activeStoryForTake.title}
                activeBriefingStories={SAMPLE_BRIEFINGS.map((s) => ({
                  id: s.id ?? 0,
                  title: s.title,
                }))}
                onTakeSubmitted={handleTakeSubmitted}
              />
            </div>

            {/* Quick Micro-HUD stats */}
            <div className="rounded-xl border border-zinc-800/80 bg-[#090a0f]/80 p-5 backdrop-blur-md">
              <h4 className="font-mono text-xs uppercase tracking-wider text-zinc-400 mb-3 font-semibold">
                Intelligence Verification Specs
              </h4>
              <ul className="space-y-2 text-xs font-mono text-zinc-400">
                <li className="flex items-center justify-between">
                  <span>Source Verification Protocol:</span>
                  <span className="text-emerald-400">SEC-20 / D20 Active</span>
                </li>
                <li className="flex items-center justify-between">
                  <span>India / Politics Min Threshold:</span>
                  <span className="text-zinc-200">3 Distinct Domains</span>
                </li>
                <li className="flex items-center justify-between">
                  <span>Max Forecast Buffer:</span>
                  <span className="text-violet-400">500 Characters Max</span>
                </li>
                <li className="flex items-center justify-between">
                  <span>Audit Trail Hash:</span>
                  <span className="text-zinc-500 truncate max-w-[120px]">sha256:d8a94e...</span>
                </li>
              </ul>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
