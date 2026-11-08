"use client";

import React, { useState, useMemo, useCallback } from "react";
import { FlashcardView } from "../../components/practice/flashcard-view";
import { MCQDrill } from "../../components/practice/mcq-drill";
import {
  MistakesNotebook,
  MistakeItem,
} from "../../components/practice/mistakes-notebook";

type PracticeTab = "flashcards" | "mcq" | "mistakes";

const INITIAL_MISTAKES: MistakeItem[] = [
  {
    id: "mstk-001",
    question:
      "Under the Flexible Inflation Targeting Framework (FITF), what constitutes a statutory failure by the Monetary Policy Committee (MPC) to maintain the inflation target?",
    chosen:
      "Headline CPI inflation exceeds 6% or falls below 2% for any two consecutive quarters.",
    correct:
      "Headline CPI inflation exceeds 6% or falls below 2% for three consecutive quarters.",
    explanation:
      "Section 45ZN of the RBI Act 1934 specifies that failure occurs when average headline inflation is greater than the upper tolerance level (6%) or less than the lower tolerance level (2%) for three consecutive quarters.",
    topic: "Macroeconomics",
    tags: ["Monetary Policy", "RBI Act", "UPSC GS-III"],
    source: "MCQ Drill · RBI Regulations 2016",
    createdAt: "2026-11-08T16:20:00Z",
    resolved: false,
    resolvedAt: null,
  },
  {
    id: "mstk-002",
    question:
      "What condition triggers a Translation Lookaside Buffer (TLB) shootdown across multiple CPU cores in an SMP kernel?",
    chosen:
      "A thread reads a page that is already cached in the L1 data cache of another core.",
    correct:
      "One CPU core modifies or invalidates a page table entry that might be cached in other cores' TLBs.",
    explanation:
      "When a core alters or unmaps a page table entry, other cores can hold stale virtual-to-physical address translations. The initiating core must broadcast Inter-Processor Interrupts (IPIs) to force other cores to flush matching TLB lines.",
    topic: "Computer Systems",
    tags: ["Virtual Memory", "SMP", "Kernel"],
    source: "MCQ Drill · OS Concepts Ch. 9",
    createdAt: "2026-11-08T15:45:00Z",
    resolved: false,
    resolvedAt: null,
  },
  {
    id: "mstk-003",
    question:
      "What are the specific procedural safeguards provided under Article 22(1) and 22(2) of the Indian Constitution against arbitrary arrest?",
    chosen:
      "Mandatory bail application within 48 hours and judicial immunity from police interrogation.",
    correct:
      "Right to be informed of grounds of arrest, right to legal counsel, and production before magistrate within 24 hours.",
    explanation:
      "Article 22 protects against arbitrary detention by establishing the fundamental right to legal defense and mandatory judicial presentation within 24 hours of apprehension.",
    topic: "Indian Polity",
    tags: ["Constitutional Law", "Fundamental Rights", "Article 22"],
    source: "Flashcard FSRS Again Rating",
    createdAt: "2026-11-08T14:10:00Z",
    resolved: true,
    resolvedAt: "2026-11-08T17:00:00Z",
  },
];

export default function PracticePage() {
  const [activeTab, setActiveTab] = useState<PracticeTab>("flashcards");
  const [mistakes, setMistakes] = useState<MistakeItem[]>(INITIAL_MISTAKES);
  const [dailyCaps, setDailyCaps] = useState({
    newCount: 4,
    maxNew: 10,
    reviewCount: 18,
    maxReviews: 40,
  });

  // Calculate active mistakes count
  const activeMistakesCount = useMemo(
    () => mistakes.filter((m) => !m.resolved).length,
    [mistakes]
  );

  // Shared mistake recording hook: receives failures from MCQ Drill or FSRS Again ratings
  const handleRecordMistake = useCallback(
    (item: {
      question: string;
      chosen: string;
      correct: string;
      explanation: string;
      topic: string;
    }) => {
      const newMistake: MistakeItem = {
        id: `mstk-${Date.now()}`,
        question: item.question,
        chosen: item.chosen,
        correct: item.correct,
        explanation: item.explanation,
        topic: item.topic,
        tags: [item.topic],
        source: activeTab === "mcq" ? "MCQ Drill Session" : "Flashcard Review (Again)",
        createdAt: new Date().toISOString(),
        resolved: false,
        resolvedAt: null,
      };

      setMistakes((prev) => [newMistake, ...prev]);
    },
    [activeTab]
  );

  const handleResolveMistake = useCallback((id: string) => {
    setMistakes((prev) =>
      prev.map((m) =>
        m.id === id
          ? { ...m, resolved: true, resolvedAt: new Date().toISOString() }
          : m
      )
    );
  }, []);

  const handleReopenMistake = useCallback((id: string) => {
    setMistakes((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, resolved: false, resolvedAt: null } : m
      )
    );
  }, []);

  const handleRateCard = useCallback((cardId: string, rating: number) => {
    // If rated, increment review count if not at cap
    setDailyCaps((prev) => ({
      ...prev,
      reviewCount: Math.min(prev.reviewCount + 1, prev.maxReviews),
    }));
  }, []);

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 flex flex-col font-sans selection:bg-emerald-500/30 selection:text-emerald-200">
      {/* Top Banner / Breadcrumb & Cyber-Academic Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2 text-xs font-mono text-zinc-500">
              <span>TECHRADAR BRAIN</span>
              <span>/</span>
              <span className="text-zinc-300">RETRIEVAL & PRACTICE ENGINE</span>
            </div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-100 font-mono">
                PRACTICE & DRILLS
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                FSRS v5 ACTIVE
              </span>
            </div>
          </div>

          {/* Telemetry pill */}
          <div className="flex items-center gap-3 font-mono text-xs">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              <span className="text-zinc-400">Daily Cap:</span>
              <span className="text-zinc-200 font-bold">10 New / 40 Reviews</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8 flex flex-col gap-8">
        {/* 4-Stat Telemetry Summary Strip */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 font-mono">
          {/* Due Cards */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/90 p-4 flex flex-col gap-1 shadow-lg shadow-black/40">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>Cards Due</span>
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
            </div>
            <div className="text-2xl font-bold text-zinc-100 font-mono">14</div>
            <span className="text-[11px] text-zinc-500 font-sans">
              4 new • 10 reviews in queue
            </span>
          </div>

          {/* Drills Completed */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/90 p-4 flex flex-col gap-1 shadow-lg shadow-black/40">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>MCQ Drills</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-emerald-400 font-mono">3 / 5</div>
            <span className="text-[11px] text-zinc-500 font-sans">
              82% avg accuracy today
            </span>
          </div>

          {/* Active Mistakes */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/90 p-4 flex flex-col gap-1 shadow-lg shadow-black/40">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>Active Mistakes</span>
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
            </div>
            <div className="text-2xl font-bold text-rose-400 font-mono">
              {activeMistakesCount}
            </div>
            <span className="text-[11px] text-zinc-500 font-sans">
              Targeted priority review
            </span>
          </div>

          {/* Current Retention Streak */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/90 p-4 flex flex-col gap-1 shadow-lg shadow-black/40">
            <div className="flex items-center justify-between text-zinc-400 text-xs">
              <span>Study Streak</span>
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            </div>
            <div className="text-2xl font-bold text-amber-400 font-mono">7 Days</div>
            <span className="text-[11px] text-zinc-500 font-sans">
              90.4% target retention
            </span>
          </div>
        </section>

        {/* Tab Navigation Hub */}
        <section className="flex flex-col gap-6">
          <div className="flex items-center justify-start border-b border-zinc-800 pb-1">
            <nav className="flex items-center gap-2 sm:gap-3 font-mono text-xs overflow-x-auto no-scrollbar">
              {/* Tab 1: Flashcards (FSRS v5) */}
              <button
                type="button"
                onClick={() => setActiveTab("flashcards")}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border transition-all duration-150 active:scale-95 ${
                  activeTab === "flashcards"
                    ? "bg-zinc-900 border-zinc-700 text-zinc-100 shadow-md shadow-black/60 font-semibold"
                    : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40"
                }`}
              >
                <svg
                  className="w-4 h-4 text-cyan-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                  />
                </svg>
                <span>Flashcards (FSRS v5)</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-800">
                  14 Due
                </span>
              </button>

              {/* Tab 2: MCQ Drills */}
              <button
                type="button"
                onClick={() => setActiveTab("mcq")}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border transition-all duration-150 active:scale-95 ${
                  activeTab === "mcq"
                    ? "bg-zinc-900 border-zinc-700 text-zinc-100 shadow-md shadow-black/60 font-semibold"
                    : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40"
                }`}
              >
                <svg
                  className="w-4 h-4 text-emerald-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>MCQ Drills</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800">
                  60s Timer
                </span>
              </button>

              {/* Tab 3: Mistakes Notebook */}
              <button
                type="button"
                onClick={() => setActiveTab("mistakes")}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border transition-all duration-150 active:scale-95 ${
                  activeTab === "mistakes"
                    ? "bg-zinc-900 border-zinc-700 text-zinc-100 shadow-md shadow-black/60 font-semibold"
                    : "border-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40"
                }`}
              >
                <svg
                  className="w-4 h-4 text-rose-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                  />
                </svg>
                <span>Mistakes Notebook</span>
                {activeMistakesCount > 0 && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-rose-950 text-rose-300 border border-rose-800">
                    {activeMistakesCount} Active
                  </span>
                )}
              </button>
            </nav>
          </div>

          {/* Active Tab Component Container */}
          <div className="w-full">
            {activeTab === "flashcards" && (
              <FlashcardView
                dailyCaps={dailyCaps}
                onRateCard={handleRateCard}
                onRecordMistake={handleRecordMistake}
              />
            )}

            {activeTab === "mcq" && (
              <MCQDrill
                timeLimitSeconds={60}
                onRecordMistake={handleRecordMistake}
              />
            )}

            {activeTab === "mistakes" && (
              <MistakesNotebook
                mistakes={mistakes}
                onResolveMistake={handleResolveMistake}
                onReopenMistake={handleReopenMistake}
              />
            )}
          </div>
        </section>
      </main>

      {/* Cyber-Academic Footer */}
      <footer className="border-t border-zinc-800/80 bg-zinc-950/60 py-4 mt-auto">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs font-mono text-zinc-500">
          <div>TechRadar Brain Spaced Retrieval Subsystem · FSRS v5 & MCQ Gateway</div>
          <div className="flex items-center gap-3">
            <span>Obsidian Noir HUD</span>
            <span>•</span>
            <span className="text-zinc-400">Tailscale Encrypted</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
