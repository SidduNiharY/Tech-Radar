"use client";

import React, { useState, useMemo, ChangeEvent } from "react";

export interface MistakeItem {
  id: string;
  question: string;
  chosen: string;
  correct: string;
  explanation: string;
  topic: string;
  tags?: string[];
  source?: string;
  createdAt: string;
  resolved: boolean;
  resolvedAt?: string | null;
}

export interface MistakesNotebookProps {
  mistakes?: MistakeItem[];
  onResolveMistake?: (id: string) => void;
  onReopenMistake?: (id: string) => void;
}

const DEFAULT_MISTAKES: MistakeItem[] = [
  {
    id: "mstk-001",
    question:
      "Under the Flexible Inflation Targeting Framework (FITF), what constitutes a statutory failure by the Monetary Policy Committee (MPC) to maintain the inflation target?",
    chosen: "Headline CPI inflation exceeds 6% or falls below 2% for any two consecutive quarters.",
    correct: "Headline CPI inflation exceeds 6% or falls below 2% for three consecutive quarters.",
    explanation:
      "Section 45ZN of the RBI Act 1934 specifies that the failure to maintain the inflation target occurs when average headline inflation is greater than the upper tolerance level (6%) or less than the lower tolerance level (2%) for any three consecutive quarters.",
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
      "What condition triggers a Translation Lookaside Buffer (TLB) shootdown across multiple cores?",
    chosen: "A thread reads a page that is already cached in the L1 data cache of another core.",
    correct: "One CPU core modifies or invalidates a page table entry that might be cached in other cores' TLBs.",
    explanation:
      "When a page table entry is modified or unmapped on one core, other cores might hold obsolete virtual-to-physical address translations in their local hardware TLBs. The initiating core must broadcast an Inter-Processor Interrupt (IPI) to invalidate those entries.",
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
    chosen: "Mandatory bail application within 48 hours and judicial immunity from police interrogation.",
    correct: "Right to be informed of grounds of arrest, right to legal counsel, and production before magistrate within 24 hours.",
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

export function MistakesNotebook({
  mistakes = DEFAULT_MISTAKES,
  onResolveMistake,
  onReopenMistake,
}: MistakesNotebookProps) {
  const [items, setItems] = useState<MistakeItem[]>(mistakes);
  const [filterTab, setFilterTab] = useState<"active" | "all" | "resolved">("active");
  const [selectedTopic, setSelectedTopic] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Sync internal state if prop updates
  React.useEffect(() => {
    setItems(mistakes);
  }, [mistakes]);

  // Handle Mark Resolved
  const handleToggleResolve = (id: string, currentResolved: boolean) => {
    const updated = items.map((item) => {
      if (item.id === id) {
        const nextResolved = !currentResolved;
        return {
          ...item,
          resolved: nextResolved,
          resolvedAt: nextResolved ? new Date().toISOString() : null,
        };
      }
      return item;
    });

    setItems(updated);

    if (currentResolved) {
      if (onReopenMistake) onReopenMistake(id);
    } else {
      if (onResolveMistake) onResolveMistake(id);
    }
  };

  // Derive unique topics
  const topics = useMemo(() => {
    const set = new Set<string>();
    items.forEach((item) => set.add(item.topic));
    return Array.from(set);
  }, [items]);

  // Filtered items
  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      // Tab filter
      if (filterTab === "active" && item.resolved) return false;
      if (filterTab === "resolved" && !item.resolved) return false;

      // Topic filter
      if (selectedTopic !== "all" && item.topic !== selectedTopic) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesQ = item.question.toLowerCase().includes(q);
        const matchesExplanation = item.explanation.toLowerCase().includes(q);
        const matchesTopic = item.topic.toLowerCase().includes(q);
        const matchesTags = item.tags?.some((t) => t.toLowerCase().includes(q));
        if (!matchesQ && !matchesExplanation && !matchesTopic && !matchesTags) {
          return false;
        }
      }

      return true;
    });
  }, [filterTab, items, searchQuery, selectedTopic]);

  const activeCount = items.filter((i) => !i.resolved).length;
  const resolvedCount = items.filter((i) => i.resolved).length;

  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col gap-6 font-sans text-zinc-100">
      {/* Top Header & Telemetry HUD */}
      <div className="rounded-xl border border-zinc-800 bg-[#09090b] p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl shadow-black/60">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center font-mono text-zinc-300">
            <svg
              className="w-5 h-5 text-rose-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold font-mono tracking-wide text-zinc-200">
                ACTIVE MISTAKES NOTEBOOK
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                Targeted Spaced Review
              </span>
            </div>
            <p className="text-xs text-zinc-500">
              Auto-populated from quiz misses and FSRS "Again" ratings
            </p>
          </div>
        </div>

        {/* Counter Badges HUD */}
        <div className="flex items-center gap-2 font-mono text-xs">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            <span className="text-zinc-400">Active:</span>
            <span className="text-rose-400 font-bold">{activeCount}</span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-zinc-400">Resolved:</span>
            <span className="text-emerald-400 font-bold">{resolvedCount}</span>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        {/* Tab Switcher: Active / All / Resolved */}
        <div className="flex items-center p-1 rounded-xl bg-zinc-900 border border-zinc-800 text-xs font-mono w-full sm:w-auto">
          <button
            type="button"
            onClick={() => setFilterTab("active")}
            className={`flex-1 sm:flex-initial px-4 py-1.5 rounded-lg transition-all ${
              filterTab === "active"
                ? "bg-zinc-800 text-zinc-100 font-semibold shadow-sm border border-zinc-700"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Active ({activeCount})
          </button>
          <button
            type="button"
            onClick={() => setFilterTab("all")}
            className={`flex-1 sm:flex-initial px-4 py-1.5 rounded-lg transition-all ${
              filterTab === "all"
                ? "bg-zinc-800 text-zinc-100 font-semibold shadow-sm border border-zinc-700"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            All ({items.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterTab("resolved")}
            className={`flex-1 sm:flex-initial px-4 py-1.5 rounded-lg transition-all ${
              filterTab === "resolved"
                ? "bg-zinc-800 text-zinc-100 font-semibold shadow-sm border border-zinc-700"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Resolved ({resolvedCount})
          </button>
        </div>

        {/* Search Input */}
        <div className="w-full sm:w-72 relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              setSearchQuery(e.target.value)
            }
            placeholder="Search questions or topics..."
            className="w-full bg-[#09090b] border border-zinc-800 rounded-xl px-3.5 py-1.5 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors font-mono"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 text-xs"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Topic Filter Chips */}
      {topics.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
          <span className="text-zinc-500 text-[11px] mr-1">Topics:</span>
          <button
            type="button"
            onClick={() => setSelectedTopic("all")}
            className={`px-2.5 py-1 rounded-md text-[11px] transition-all ${
              selectedTopic === "all"
                ? "bg-zinc-800 text-zinc-100 border border-zinc-700"
                : "bg-zinc-950 text-zinc-400 border border-zinc-850 hover:border-zinc-750"
            }`}
          >
            All Topics
          </button>
          {topics.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setSelectedTopic(t)}
              className={`px-2.5 py-1 rounded-md text-[11px] transition-all ${
                selectedTopic === t
                  ? "bg-zinc-800 text-zinc-100 border border-zinc-700"
                  : "bg-zinc-950 text-zinc-400 border border-zinc-850 hover:border-zinc-750"
              }`}
            >
              #{t}
            </button>
          ))}
        </div>
      )}

      {/* Mistakes Card List */}
      {filteredItems.length > 0 ? (
        <div className="flex flex-col gap-4">
          {filteredItems.map((item) => {
            const formattedDate = new Date(item.createdAt).toLocaleDateString(
              undefined,
              {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              }
            );

            return (
              <div
                key={item.id}
                className={`rounded-2xl border transition-all duration-200 p-5 sm:p-6 flex flex-col gap-4 bg-[#09090b] shadow-xl shadow-black/60 ${
                  item.resolved
                    ? "border-zinc-850 opacity-75 hover:opacity-100 hover:border-zinc-800"
                    : "border-zinc-800 hover:border-zinc-700"
                }`}
              >
                {/* Card Header: Topic, Tags & Status */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/80 pb-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-zinc-900 border border-zinc-800 text-zinc-300">
                      {item.topic}
                    </span>
                    {item.tags?.map((tag) => (
                      <span
                        key={tag}
                        className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-950 text-zinc-500 border border-zinc-850"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>

                  <div className="flex items-center gap-3 font-mono text-[11px]">
                    <span className="text-zinc-500">{formattedDate}</span>
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded font-semibold text-[10px] ${
                        item.resolved
                          ? "bg-emerald-950/60 text-emerald-400 border border-emerald-800/60"
                          : "bg-rose-950/60 text-rose-400 border border-rose-800/60"
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          item.resolved ? "bg-emerald-400" : "bg-rose-400 animate-pulse"
                        }`}
                      />
                      {item.resolved ? "RESOLVED" : "ACTIVE REVIEW"}
                    </span>
                  </div>
                </div>

                {/* Question Text */}
                <div>
                  <p className="text-sm sm:text-base font-medium text-zinc-100 leading-relaxed font-sans">
                    {item.question}
                  </p>
                </div>

                {/* Answer Comparison Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                  {/* Your Answer */}
                  <div className="p-3 rounded-xl border border-rose-900/40 bg-rose-950/15 flex flex-col gap-1">
                    <span className="text-[10px] font-mono uppercase font-bold text-rose-400 tracking-wider">
                      Your Missed Choice
                    </span>
                    <p className="text-xs text-rose-200 font-sans leading-relaxed">
                      {item.chosen}
                    </p>
                  </div>

                  {/* Correct Key */}
                  <div className="p-3 rounded-xl border border-emerald-900/40 bg-emerald-950/15 flex flex-col gap-1">
                    <span className="text-[10px] font-mono uppercase font-bold text-emerald-400 tracking-wider">
                      Correct Key
                    </span>
                    <p className="text-xs text-emerald-200 font-sans leading-relaxed">
                      {item.correct}
                    </p>
                  </div>
                </div>

                {/* Explanation Callout */}
                <div className="p-3.5 rounded-xl bg-zinc-900/50 border border-zinc-800 text-xs text-zinc-300 leading-relaxed font-sans">
                  <span className="text-[10px] font-mono uppercase text-zinc-500 block mb-1">
                    Retention Note & Context
                  </span>
                  {item.explanation}
                </div>

                {/* Card Action Footer */}
                <div className="pt-2 border-t border-zinc-800/80 flex items-center justify-between">
                  <span className="text-[11px] font-mono text-zinc-500">
                    {item.source ? `Logged from: ${item.source}` : `ID: ${item.id}`}
                  </span>

                  {/* Mark Resolved Button */}
                  <button
                    type="button"
                    onClick={() => handleToggleResolve(item.id, item.resolved)}
                    className={`px-4 py-2 rounded-xl text-xs font-mono font-medium flex items-center gap-2 active:scale-95 transition-all shadow-md ${
                      item.resolved
                        ? "bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300"
                        : "bg-emerald-950/50 hover:bg-emerald-900/60 border border-emerald-700 text-emerald-300 hover:text-emerald-200"
                    }`}
                  >
                    {item.resolved ? (
                      <>
                        <svg
                          className="w-3.5 h-3.5 text-zinc-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                          />
                        </svg>
                        <span>Re-open Mistake</span>
                      </>
                    ) : (
                      <>
                        <svg
                          className="w-3.5 h-3.5 text-emerald-400"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2.5"
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                        <span>Mark Resolved</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty State */
        <div className="rounded-2xl border border-zinc-800 bg-[#09090b] p-8 sm:p-12 text-center flex flex-col items-center justify-center gap-4 shadow-xl shadow-black/60">
          <div className="w-14 h-14 rounded-full bg-emerald-950/50 border border-emerald-700/60 flex items-center justify-center text-emerald-400">
            <svg
              className="w-7 h-7"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>

          <div className="flex flex-col gap-1 max-w-sm">
            <h3 className="text-lg font-medium text-zinc-100">
              No Mistakes in this View
            </h3>
            <p className="text-xs text-zinc-400">
              {filterTab === "active"
                ? "All recorded mistakes have been resolved and mastered."
                : "No matching question items found for the current search filter."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default MistakesNotebook;
