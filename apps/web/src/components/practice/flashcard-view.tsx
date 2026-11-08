"use client";

import React, { useState, useEffect, useCallback, MouseEvent } from "react";

export type FSRSRating = 1 | 2 | 3 | 4; // 1: Again, 2: Hard, 3: Good, 4: Easy

export interface FlashcardItem {
  id: string;
  topic: string;
  chapter?: string;
  question: string;
  answer: string;
  excerpt?: string;
  source?: string;
  state: "new" | "learning" | "review" | "relearning";
  stability?: number;
  difficulty?: number;
  reps?: number;
  lapses?: number;
}

export interface DailyCaps {
  newCount: number;
  maxNew: number;
  reviewCount: number;
  maxReviews: number;
}

export interface FlashcardViewProps {
  cards?: FlashcardItem[];
  dailyCaps?: DailyCaps;
  onRateCard?: (cardId: string, rating: FSRSRating) => void;
  onRecordMistake?: (mistake: {
    question: string;
    chosen: string;
    correct: string;
    explanation: string;
    topic: string;
  }) => void;
}

const DEFAULT_CARDS: FlashcardItem[] = [
  {
    id: "card-fsrs-01",
    topic: "Macroeconomics",
    chapter: "RBI & Monetary Transmission",
    question:
      "Explain the External Benchmark Lending Rate (EBLR) mechanism introduced by the RBI and why it replaced the Marginal Cost of Funds based Lending Rate (MCLR).",
    answer:
      "Under the EBLR framework (effective October 2019), banks are mandated to link all new floating-rate personal, retail, and MSME loans to an external benchmark (such as the RBI Policy Repo Rate or 3-Month / 6-Month T-bill yields) plus a fixed spread. This solved the sluggish monetary transmission problem under MCLR, where internal cost calculations delayed repo cut passthroughs to retail borrowers.",
    excerpt:
      "The transmission of monetary policy under MCLR was asymmetric and slow. Under EBLR, changes in policy repo rates are mandated to reflect in retail lending rates within the same reset quarter.",
    source: "RBI Bulletin · Monetary Policy Report 2024 §3.2",
    state: "review",
    stability: 3.4,
    difficulty: 5.2,
    reps: 3,
    lapses: 0,
  },
  {
    id: "card-fsrs-02",
    topic: "Computer Architecture",
    chapter: "Memory Hierarchy & Caching",
    question:
      "What is the difference between Write-Through with No-Write-Allocate and Write-Back with Write-Allocate cache write policies?",
    answer:
      "In Write-Through, every cache write immediately updates the backing lower-level memory; on a write miss with No-Write-Allocate, the block is written directly to main memory without loading into cache. In Write-Back, updates are written only to the cache line (setting a 'dirty bit'); main memory is updated only upon block eviction. Write-Allocate fetches the block into cache on a write miss.",
    excerpt:
      "Write-back caches preserve internal bandwidth by filtering repeated writes to the same cache block before flushing dirty lines during cache eviction.",
    source: "Patterson & Hennessy · Computer Organization and Design 6th Ed.",
    state: "review",
    stability: 5.1,
    difficulty: 4.8,
    reps: 4,
    lapses: 1,
  },
  {
    id: "card-fsrs-03",
    topic: "Indian Polity",
    chapter: "Constitutional Safeguards",
    question:
      "What are the specific procedural safeguards provided under Article 22(1) and 22(2) of the Indian Constitution against arbitrary arrest?",
    answer:
      "Article 22(1) guarantees: (1) the right to be informed as soon as may be of the grounds of arrest, and (2) the right to consult and be defended by a legal practitioner of one's choice. Article 22(2) mandates that every person arrested must be produced before the nearest magistrate within 24 hours of arrest (excluding travel time), and cannot be detained beyond that period without judicial authorization.",
    excerpt:
      "No person who is arrested shall be detained in custody without being informed, as soon as may be, of the grounds for such arrest nor shall he be denied the right to consult a legal practitioner.",
    source: "Constitution of India · Part III Fundamental Rights Art. 22",
    state: "new",
    stability: 0.0,
    difficulty: 5.0,
    reps: 0,
    lapses: 0,
  },
  {
    id: "card-fsrs-04",
    topic: "Distributed Systems",
    chapter: "Consensus Protocols",
    question:
      "In the Raft consensus algorithm, how does a leader enforce safety during log replication when a term change occurs?",
    answer:
      "A Raft leader never commits an entry from an older term by counting replicas alone. It only commits an entry from its current term by counting replicas; once a current-term entry is committed, earlier entries preceding it are indirectly committed by the Log Matching Property.",
    excerpt:
      "Raft never commits log entries from previous terms simply by counting replicas; only current-term entries trigger commit markers.",
    source: "Ongaro & Ousterhout · In Search of an Understandable Consensus Algorithm (USENIX ATC '14)",
    state: "review",
    stability: 8.2,
    difficulty: 6.4,
    reps: 5,
    lapses: 0,
  },
];

const DEFAULT_CAPS: DailyCaps = {
  newCount: 4,
  maxNew: 10,
  reviewCount: 18,
  maxReviews: 40,
};

export function FlashcardView({
  cards = DEFAULT_CARDS,
  dailyCaps = DEFAULT_CAPS,
  onRateCard,
  onRecordMistake,
}: FlashcardViewProps) {
  const [deck, setDeck] = useState<FlashcardItem[]>(cards);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [isFlipped, setIsFlipped] = useState<boolean>(false);
  const [caps, setCaps] = useState<DailyCaps>(dailyCaps);
  const [ratedHistory, setRatedHistory] = useState<
    Array<{ cardId: string; rating: FSRSRating; at: string }>
  >([]);
  const [isCompleted, setIsCompleted] = useState<boolean>(false);
  const [lastActionFeedback, setLastActionFeedback] = useState<string | null>(null);

  const currentCard = deck[currentIndex];

  const handleFlip = useCallback(() => {
    setIsFlipped((prev) => !prev);
  }, []);

  const handleRate = useCallback(
    (rating: FSRSRating) => {
      if (!currentCard) return;

      const cardId = currentCard.id;
      const isNew = currentCard.state === "new";

      // Update local caps
      setCaps((prev) => ({
        ...prev,
        newCount: isNew ? Math.min(prev.newCount + 1, prev.maxNew) : prev.newCount,
        reviewCount: !isNew ? Math.min(prev.reviewCount + 1, prev.maxReviews) : prev.reviewCount,
      }));

      // Record history
      const ratingLabels: Record<FSRSRating, string> = {
        1: "Again (Reset to Learning)",
        2: "Hard (+1.2d)",
        3: "Good (+3.5d)",
        4: "Easy (+8.0d)",
      };
      setLastActionFeedback(`Rated "${ratingLabels[rating]}" on Card #${currentIndex + 1}`);

      // If Again (1), log mistake to parent handler
      if (rating === 1 && onRecordMistake) {
        onRecordMistake({
          question: currentCard.question,
          chosen: "Incorrect / Again Rating",
          correct: currentCard.answer,
          explanation: currentCard.excerpt || "Review required under FSRS v5 spaced repetition schedule.",
          topic: currentCard.topic,
        });
      }

      if (onRateCard) {
        onRateCard(cardId, rating);
      }

      setRatedHistory((prev) => [
        ...prev,
        { cardId, rating, at: new Date().toLocaleTimeString() },
      ]);

      // Move to next card with smooth transition
      setTimeout(() => {
        if (currentIndex + 1 < deck.length) {
          setIsFlipped(false);
          setCurrentIndex((prev) => prev + 1);
        } else {
          setIsCompleted(true);
        }
      }, 200);
    },
    [currentCard, currentIndex, deck.length, onRateCard, onRecordMistake]
  );

  // Keyboard shortcut listener: Space to flip, 1-4 to rate
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept if focus is inside an input, textarea or contentEditable
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }

      if (e.code === "Space") {
        e.preventDefault();
        handleFlip();
      } else if (isFlipped) {
        if (e.key === "1") {
          e.preventDefault();
          handleRate(1);
        } else if (e.key === "2") {
          e.preventDefault();
          handleRate(2);
        } else if (e.key === "3") {
          e.preventDefault();
          handleRate(3);
        } else if (e.key === "4") {
          e.preventDefault();
          handleRate(4);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleFlip, handleRate, isFlipped]);

  const handleRestart = () => {
    setCurrentIndex(0);
    setIsFlipped(false);
    setIsCompleted(false);
    setRatedHistory([]);
    setLastActionFeedback(null);
  };

  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col gap-6 font-sans text-zinc-100">
      {/* Top HUD: Daily Caps & Spaced Repetition Limits */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4 sm:p-5 backdrop-blur-md flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-lg shadow-black/40">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-300">
              FSRS v5 Spaced Repetition Deck
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/60">
              Retention Target: 90%
            </span>
          </div>
          <p className="text-xs text-zinc-400">
            Daily limit enforcement:{" "}
            <span className="font-mono text-zinc-200 font-medium">
              10 new / 40 reviews daily limit
            </span>
          </p>
        </div>

        {/* Daily Cap Progress Readout */}
        <div className="flex items-center gap-4 sm:gap-6 font-mono text-xs">
          {/* New Cards Progress */}
          <div className="flex flex-col gap-1 min-w-[120px]">
            <div className="flex justify-between text-[11px] text-zinc-400">
              <span>New Cards</span>
              <span className="text-cyan-400 font-semibold">
                {caps.newCount}/{caps.maxNew}
              </span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-zinc-800 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-300"
                style={{
                  width: `${Math.min((caps.newCount / caps.maxNew) * 100, 100)}%`,
                }}
              />
            </div>
          </div>

          {/* Review Cards Progress */}
          <div className="flex flex-col gap-1 min-w-[130px]">
            <div className="flex justify-between text-[11px] text-zinc-400">
              <span>Reviews</span>
              <span className="text-emerald-400 font-semibold">
                {caps.reviewCount}/{caps.maxReviews}
              </span>
            </div>
            <div className="w-full h-1.5 rounded-full bg-zinc-800 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-300"
                style={{
                  width: `${Math.min((caps.reviewCount / caps.maxReviews) * 100, 100)}%`,
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Main Flashcard Container */}
      {!isCompleted && currentCard ? (
        <div className="flex flex-col gap-4">
          {/* Deck Navigation and Status Header */}
          <div className="flex items-center justify-between text-xs text-zinc-400 px-1 font-mono">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-300">
                Card {currentIndex + 1} of {deck.length}
              </span>
              <span className="text-zinc-500">|</span>
              <span className="text-zinc-400">{currentCard.topic}</span>
            </div>

            <div className="flex items-center gap-2">
              <span className="hidden sm:inline text-zinc-500">Keyboard shortcuts:</span>
              <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-700/80 text-[10px] text-zinc-300">
                Space
              </kbd>
              <span className="text-zinc-500">flip</span>
              {isFlipped && (
                <>
                  <span className="text-zinc-500">|</span>
                  <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-700/80 text-[10px] text-zinc-300">
                    1-4
                  </kbd>
                  <span className="text-zinc-500">rate</span>
                </>
              )}
            </div>
          </div>

          {/* 3D Perspective Card Wrapper */}
          <div
            className="w-full min-h-[380px] sm:min-h-[420px] relative cursor-pointer select-none"
            style={{ perspective: "1200px" }}
            onClick={handleFlip}
          >
            <div
              className="w-full h-full min-h-[380px] sm:min-h-[420px] transition-transform duration-500 ease-out"
              style={{
                transformStyle: "preserve-3d",
                transform: isFlipped ? "rotateY(180deg)" : "rotateY(0deg)",
              }}
            >
              {/* FRONT FACE */}
              <div
                className="absolute inset-0 w-full h-full rounded-2xl border border-zinc-800 bg-[#09090b] p-6 sm:p-8 flex flex-col justify-between shadow-2xl shadow-black/80 hover:border-zinc-700 transition-colors"
                style={{ backfaceVisibility: "hidden" }}
              >
                {/* Front Top Bar */}
                <div className="flex items-center justify-between gap-2 border-b border-zinc-800/80 pb-4">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-zinc-900 border border-zinc-700 text-zinc-200">
                      {currentCard.chapter || currentCard.topic}
                    </span>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded uppercase font-semibold ${
                        currentCard.state === "new"
                          ? "bg-cyan-950/60 text-cyan-300 border border-cyan-800/60"
                          : "bg-emerald-950/60 text-emerald-300 border border-emerald-800/60"
                      }`}
                    >
                      {currentCard.state}
                    </span>
                  </div>

                  <span className="text-[11px] font-mono text-zinc-500">
                    Front • Question
                  </span>
                </div>

                {/* Front Content: Question */}
                <div className="my-auto py-6">
                  <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 block mb-2">
                    Recall Prompt
                  </span>
                  <p className="text-lg sm:text-2xl font-medium text-zinc-100 leading-relaxed sm:leading-relaxed">
                    {currentCard.question}
                  </p>
                </div>

                {/* Front Bottom Action */}
                <div className="pt-4 border-t border-zinc-800/80 flex items-center justify-between">
                  <span className="text-xs text-zinc-400 flex items-center gap-1.5 font-mono">
                    <svg
                      className="w-4 h-4 text-zinc-500"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"
                      />
                    </svg>
                    Click card or press <kbd className="text-zinc-200 font-semibold">Space</kbd>
                  </span>

                  <button
                    type="button"
                    onClick={(e: MouseEvent) => {
                      e.stopPropagation();
                      handleFlip();
                    }}
                    className="px-4 py-2 rounded-lg bg-zinc-900 hover:bg-zinc-800 active:scale-95 border border-zinc-700 text-xs font-mono font-medium text-zinc-200 flex items-center gap-2 transition-all shadow-md hover:border-zinc-500"
                  >
                    <span>Flip / Show Answer</span>
                    <svg
                      className="w-3.5 h-3.5"
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
                  </button>
                </div>
              </div>

              {/* BACK FACE */}
              <div
                className="absolute inset-0 w-full h-full rounded-2xl border border-zinc-800 bg-[#09090b] p-6 sm:p-8 flex flex-col justify-between shadow-2xl shadow-black/80 hover:border-zinc-700 transition-colors"
                style={{
                  backfaceVisibility: "hidden",
                  transform: "rotateY(180deg)",
                }}
                onClick={(e: MouseEvent) => {
                  // Prevent card flip when clicking buttons on back
                  const target = e.target as HTMLElement;
                  if (target.closest("button")) {
                    e.stopPropagation();
                  }
                }}
              >
                {/* Back Top Bar */}
                <div className="flex items-center justify-between gap-2 border-b border-zinc-800/80 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-zinc-900 border border-zinc-800 text-zinc-300">
                      {currentCard.topic}
                    </span>
                    <span className="text-[10px] font-mono text-zinc-400">
                      S: {(currentCard.stability || 0).toFixed(1)}d • D:{" "}
                      {(currentCard.difficulty || 0).toFixed(1)} • Reps:{" "}
                      {currentCard.reps || 0}
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={(e: MouseEvent) => {
                      e.stopPropagation();
                      handleFlip();
                    }}
                    className="text-xs font-mono text-zinc-400 hover:text-zinc-200 flex items-center gap-1"
                  >
                    <svg
                      className="w-3.5 h-3.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"
                      />
                    </svg>
                    Flip Back
                  </button>
                </div>

                {/* Back Content: Answer & Excerpt */}
                <div className="my-auto py-3 flex flex-col gap-3 overflow-y-auto max-h-[220px] pr-1">
                  <div>
                    <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-400 block mb-1">
                      Correct Key & Solution
                    </span>
                    <p className="text-sm sm:text-base text-zinc-200 leading-relaxed font-sans">
                      {currentCard.answer}
                    </p>
                  </div>

                  {currentCard.excerpt && (
                    <div className="p-3 rounded-lg bg-zinc-900/70 border-l-2 border-amber-500/80 border-y border-r border-zinc-800/60 text-xs text-zinc-300 italic font-serif">
                      <span>&ldquo;{currentCard.excerpt}&rdquo;</span>
                      {currentCard.source && (
                        <span className="block mt-1 text-[11px] font-sans font-normal text-zinc-500 not-italic">
                          — {currentCard.source}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Back Bottom Action: 4 FSRS Rating Buttons */}
                <div className="pt-4 border-t border-zinc-800/80 flex flex-col gap-2">
                  <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400">
                    <span>Rate Recall Precision (FSRS v5):</span>
                    <span>Keys: 1, 2, 3, 4</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                    {/* AGAIN BUTTON (Red) */}
                    <button
                      type="button"
                      onClick={(e: MouseEvent) => {
                        e.stopPropagation();
                        handleRate(1);
                      }}
                      className="px-3 py-2.5 rounded-xl border border-rose-900/60 bg-rose-950/25 hover:bg-rose-900/40 text-rose-300 hover:border-rose-600 active:scale-95 transition-all flex flex-col items-center justify-center gap-0.5 shadow-sm group"
                    >
                      <div className="flex items-center gap-1.5 font-semibold text-xs">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                        <span>Again</span>
                        <kbd className="px-1 py-0.2 rounded bg-rose-900/60 border border-rose-700/60 text-[9px] text-rose-200">
                          1
                        </kbd>
                      </div>
                      <span className="text-[10px] font-mono text-rose-400/80">&lt; 10m</span>
                    </button>

                    {/* HARD BUTTON (Amber) */}
                    <button
                      type="button"
                      onClick={(e: MouseEvent) => {
                        e.stopPropagation();
                        handleRate(2);
                      }}
                      className="px-3 py-2.5 rounded-xl border border-amber-900/60 bg-amber-950/25 hover:bg-amber-900/40 text-amber-300 hover:border-amber-600 active:scale-95 transition-all flex flex-col items-center justify-center gap-0.5 shadow-sm group"
                    >
                      <div className="flex items-center gap-1.5 font-semibold text-xs">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                        <span>Hard</span>
                        <kbd className="px-1 py-0.2 rounded bg-amber-900/60 border border-amber-700/60 text-[9px] text-amber-200">
                          2
                        </kbd>
                      </div>
                      <span className="text-[10px] font-mono text-amber-400/80">+1.2d</span>
                    </button>

                    {/* GOOD BUTTON (Blue) */}
                    <button
                      type="button"
                      onClick={(e: MouseEvent) => {
                        e.stopPropagation();
                        handleRate(3);
                      }}
                      className="px-3 py-2.5 rounded-xl border border-sky-900/60 bg-sky-950/25 hover:bg-sky-900/40 text-sky-300 hover:border-sky-600 active:scale-95 transition-all flex flex-col items-center justify-center gap-0.5 shadow-sm group"
                    >
                      <div className="flex items-center gap-1.5 font-semibold text-xs">
                        <span className="w-1.5 h-1.5 rounded-full bg-sky-500" />
                        <span>Good</span>
                        <kbd className="px-1 py-0.2 rounded bg-sky-900/60 border border-sky-700/60 text-[9px] text-sky-200">
                          3
                        </kbd>
                      </div>
                      <span className="text-[10px] font-mono text-sky-400/80">+3.5d</span>
                    </button>

                    {/* EASY BUTTON (Emerald) */}
                    <button
                      type="button"
                      onClick={(e: MouseEvent) => {
                        e.stopPropagation();
                        handleRate(4);
                      }}
                      className="px-3 py-2.5 rounded-xl border border-emerald-900/60 bg-emerald-950/25 hover:bg-emerald-900/40 text-emerald-300 hover:border-emerald-600 active:scale-95 transition-all flex flex-col items-center justify-center gap-0.5 shadow-sm group"
                    >
                      <div className="flex items-center gap-1.5 font-semibold text-xs">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        <span>Easy</span>
                        <kbd className="px-1 py-0.2 rounded bg-emerald-900/60 border border-emerald-700/60 text-[9px] text-emerald-200">
                          4
                        </kbd>
                      </div>
                      <span className="text-[10px] font-mono text-emerald-400/80">+8.0d</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Real-time Status / Feedback Note */}
          {lastActionFeedback && (
            <div className="text-center font-mono text-xs text-zinc-500 animate-fade-in">
              {lastActionFeedback}
            </div>
          )}
        </div>
      ) : (
        /* Completed State */
        <div className="rounded-2xl border border-zinc-800 bg-[#09090b] p-8 sm:p-12 text-center flex flex-col items-center justify-center gap-5 shadow-2xl shadow-black/80">
          <div className="w-16 h-16 rounded-full bg-emerald-950/60 border border-emerald-600/60 flex items-center justify-center text-emerald-400">
            <svg
              className="w-8 h-8"
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

          <div className="flex flex-col gap-2 max-w-md">
            <h3 className="text-xl font-medium text-zinc-100">
              Deck Session Completed
            </h3>
            <p className="text-sm text-zinc-400">
              All {deck.length} flashcards in this queue have been rated under FSRS v5.
              Next interval recalculation scheduled for tomorrow's briefing cycle.
            </p>
          </div>

          {/* Session Summary Pills */}
          <div className="flex flex-wrap items-center justify-center gap-3 font-mono text-xs">
            <span className="px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300">
              Cards Processed: {ratedHistory.length}
            </span>
            <span className="px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300">
              Review Cap: {caps.reviewCount}/{caps.maxReviews}
            </span>
          </div>

          <div className="pt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={handleRestart}
              className="px-5 py-2.5 rounded-xl bg-zinc-100 text-zinc-950 hover:bg-zinc-200 active:scale-95 font-medium text-sm transition-all shadow-md font-mono"
            >
              Review Deck Again
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default FlashcardView;
