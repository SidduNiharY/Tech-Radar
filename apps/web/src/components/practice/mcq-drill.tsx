"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";

export interface MCQQuestion {
  id: string;
  subject: string;
  chapter?: string;
  question: string;
  options: [string, string, string, string]; // exactly 4 options
  answerIndex: number; // 0, 1, 2, or 3
  explanation: string;
  source?: string;
}

export interface MCQDrillProps {
  questions?: MCQQuestion[];
  timeLimitSeconds?: number;
  onQuestionComplete?: (
    questionId: string,
    isCorrect: boolean,
    chosenIndex: number
  ) => void;
  onRecordMistake?: (mistake: {
    question: string;
    chosen: string;
    correct: string;
    explanation: string;
    topic: string;
  }) => void;
}

const DEFAULT_QUESTIONS: MCQQuestion[] = [
  {
    id: "mcq-econ-01",
    subject: "Macroeconomics",
    chapter: "Monetary Policy & Inflation Targeting",
    question:
      "Under the Flexible Inflation Targeting Framework (FITF) in India, what constitutes a 'failure' to maintain the inflation target by the Monetary Policy Committee (MPC)?",
    options: [
      "Headline CPI inflation exceeds 6% or falls below 2% for any two consecutive quarters.",
      "Headline CPI inflation exceeds 6% or falls below 2% for three consecutive quarters.",
      "Core CPI inflation exceeds 5% for six consecutive months.",
      "Wholesale Price Index (WPI) inflation breaches the 4% median target for more than four quarters.",
    ],
    answerIndex: 1,
    explanation:
      "Under Section 45ZN of the RBI Act 1934 read with RBI Regulations 2016, failure occurs if headline CPI inflation breaches the tolerance band (2% to 6%) for any three consecutive quarters.",
    source: "RBI Act 1934 Section 45ZN · Gazette Notification 2016",
  },
  {
    id: "mcq-sys-02",
    subject: "Computer Systems",
    chapter: "Operating Systems & Virtual Memory",
    question:
      "Which condition causes a Translation Lookaside Buffer (TLB) shootdown in a symmetric multiprocessing (SMP) operating system?",
    options: [
      "A thread reads a page that is already cached in the L1 data cache of another core.",
      "An unprivileged user process initiates a synchronous read syscall to an open file descriptor.",
      "One CPU core modifies or invalidates a page table entry that might be cached in other cores' TLBs.",
      "The kernel switches between two threads belonging to the exact same thread group (process).",
    ],
    answerIndex: 2,
    explanation:
      "When a core alters or unmaps a page table entry, other CPU cores may hold stale translations in their local TLBs. The initiating core sends inter-processor interrupts (IPIs) to force other cores to flush their matching TLB lines, termed a TLB shootdown.",
    source: "Silberschatz, Galvin & Gagne · Operating System Concepts 10th Ed.",
  },
  {
    id: "mcq-polity-03",
    subject: "Indian Polity",
    chapter: "Constitutional Amendments",
    question:
      "Which constitutional amendment act inserted Article 21A, guaranteeing free and compulsory education as a Fundamental Right for children aged 6 to 14 years?",
    options: [
      "44th Constitutional Amendment Act, 1978",
      "86th Constitutional Amendment Act, 2002",
      "91st Constitutional Amendment Act, 2003",
      "73rd Constitutional Amendment Act, 1992",
    ],
    answerIndex: 1,
    explanation:
      "The 86th Constitutional Amendment Act of 2002 inserted Article 21A into Part III, substituted Article 45 in Part IV (DPSP), and added Fundamental Duty 51A(k).",
    source: "Constitution of India · 86th Amendment Act (2002)",
  },
  {
    id: "mcq-dist-04",
    subject: "Distributed Systems",
    chapter: "CAP & PACELC Theorem",
    question:
      "In the PACELC theorem, what does the 'E-L-C' portion specify when network partitions are absent?",
    options: [
      "Else (under normal operation), trade-off between Latency and Consistency.",
      "Eventual Log Consensus across all non-faulty quorum nodes.",
      "Epoch-based Lease Coordination during leader elections.",
      "Error Logging and Checkpointing before socket write operations.",
    ],
    answerIndex: 0,
    explanation:
      "The PACELC theorem extends CAP: if there is a Partition (P), trade-off Availability (A) vs Consistency (C); Else (E), trade-off Latency (L) vs Consistency (C).",
    source: "Daniel Abadi · Consistency Tradeoffs in Modern Distributed Database System Design (Computer 2012)",
  },
];

const OPTION_LABELS = ["A", "B", "C", "D"] as const;

export function MCQDrill({
  questions = DEFAULT_QUESTIONS,
  timeLimitSeconds = 60,
  onQuestionComplete,
  onRecordMistake,
}: MCQDrillProps) {
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [isAnswered, setIsAnswered] = useState<boolean>(false);
  const [timeLeft, setTimeLeft] = useState<number>(timeLimitSeconds);
  const [isTimerPaused, setIsTimerPaused] = useState<boolean>(false);
  const [drillFinished, setDrillFinished] = useState<boolean>(false);
  const [scoreHistory, setScoreHistory] = useState<
    Array<{
      questionId: string;
      chosen: number | null;
      correct: number;
      isCorrect: boolean;
      timeSpent: number;
    }>
  >([]);

  const currentQ = questions[currentIndex];
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Countdown timer logic
  useEffect(() => {
    if (isAnswered || drillFinished || isTimerPaused) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          handleTimeExpire();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [currentIndex, isAnswered, drillFinished, isTimerPaused]);

  // When timer hits 0: mark timeout
  const handleTimeExpire = useCallback(() => {
    if (isAnswered || !currentQ) return;
    setIsAnswered(true);
    setSelectedOption(null); // Unanswered

    const record = {
      questionId: currentQ.id,
      chosen: null,
      correct: currentQ.answerIndex,
      isCorrect: false,
      timeSpent: timeLimitSeconds,
    };
    setScoreHistory((prev) => [...prev, record]);

    if (onRecordMistake) {
      onRecordMistake({
        question: currentQ.question,
        chosen: "Timed Out (No Option Selected)",
        correct: `${OPTION_LABELS[currentQ.answerIndex]}: ${currentQ.options[currentQ.answerIndex]}`,
        explanation: currentQ.explanation,
        topic: currentQ.subject,
      });
    }

    if (onQuestionComplete) {
      onQuestionComplete(currentQ.id, false, -1);
    }
  }, [currentQ, isAnswered, onQuestionComplete, onRecordMistake, timeLimitSeconds]);

  // Handle option selection
  const handleSelectOption = useCallback(
    (index: number) => {
      if (isAnswered || !currentQ) return;

      setIsAnswered(true);
      setSelectedOption(index);

      const isCorrect = index === currentQ.answerIndex;
      const timeSpent = timeLimitSeconds - timeLeft;

      const record = {
        questionId: currentQ.id,
        chosen: index,
        correct: currentQ.answerIndex,
        isCorrect,
        timeSpent,
      };
      setScoreHistory((prev) => [...prev, record]);

      if (!isCorrect && onRecordMistake) {
        onRecordMistake({
          question: currentQ.question,
          chosen: `${OPTION_LABELS[index]}: ${currentQ.options[index]}`,
          correct: `${OPTION_LABELS[currentQ.answerIndex]}: ${currentQ.options[currentQ.answerIndex]}`,
          explanation: currentQ.explanation,
          topic: currentQ.subject,
        });
      }

      if (onQuestionComplete) {
        onQuestionComplete(currentQ.id, isCorrect, index);
      }
    },
    [currentQ, isAnswered, onQuestionComplete, onRecordMistake, timeLeft, timeLimitSeconds]
  );

  // Keyboard navigation for A, B, C, D (or 1, 2, 3, 4)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }

      if (!isAnswered) {
        const key = e.key.toLowerCase();
        if (key === "a" || key === "1") {
          e.preventDefault();
          handleSelectOption(0);
        } else if (key === "b" || key === "2") {
          e.preventDefault();
          handleSelectOption(1);
        } else if (key === "c" || key === "3") {
          e.preventDefault();
          handleSelectOption(2);
        } else if (key === "d" || key === "4") {
          e.preventDefault();
          handleSelectOption(3);
        }
      } else if (e.code === "Enter" || e.code === "Space") {
        e.preventDefault();
        handleNextQuestion();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleSelectOption, isAnswered]);

  const handleNextQuestion = () => {
    if (currentIndex + 1 < questions.length) {
      setCurrentIndex((prev) => prev + 1);
      setSelectedOption(null);
      setIsAnswered(false);
      setTimeLeft(timeLimitSeconds);
    } else {
      setDrillFinished(true);
    }
  };

  const handleRestart = () => {
    setCurrentIndex(0);
    setSelectedOption(null);
    setIsAnswered(false);
    setTimeLeft(timeLimitSeconds);
    setDrillFinished(false);
    setScoreHistory([]);
  };

  const totalCorrect = scoreHistory.filter((item) => item.isCorrect).length;

  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col gap-6 font-sans text-zinc-100">
      {/* Top HUD: Quiz Metrics & 60s Countdown Timer */}
      <div className="rounded-xl border border-zinc-800 bg-[#09090b] p-4 sm:p-5 flex flex-col sm:flex-row items-center justify-between gap-4 shadow-xl shadow-black/60">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center font-mono text-zinc-300">
            <svg
              className="w-5 h-5 text-cyan-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"
              />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold font-mono tracking-wide text-zinc-200">
                MCQ TIMED RETRIEVAL DRILL
              </h2>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                4-Option Strict
              </span>
            </div>
            <p className="text-xs text-zinc-500">
              Instant verification key checker • Dual-model verified pool (SEC-20)
            </p>
          </div>
        </div>

        {/* 60s Countdown Timer Display */}
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => setIsTimerPaused((prev) => !prev)}
            className="text-[11px] font-mono px-2.5 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            {isTimerPaused ? "Resume" : "Pause"}
          </button>

          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-zinc-900/90 border border-zinc-800">
            <svg
              className={`w-4 h-4 ${
                timeLeft <= 10
                  ? "text-rose-500 animate-spin"
                  : timeLeft <= 20
                    ? "text-amber-400"
                    : "text-cyan-400"
              }`}
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

            <span
              className={`font-mono text-sm font-bold tracking-wider ${
                timeLeft <= 10
                  ? "text-rose-400 animate-pulse"
                  : timeLeft <= 20
                    ? "text-amber-400"
                    : "text-cyan-300"
              }`}
            >
              00:{timeLeft < 10 ? `0${timeLeft}` : timeLeft}
            </span>
          </div>
        </div>
      </div>

      {!drillFinished && currentQ ? (
        <div className="flex flex-col gap-5">
          {/* Question Card Container */}
          <div className="rounded-2xl border border-zinc-800 bg-[#09090b] p-6 sm:p-8 flex flex-col gap-6 shadow-2xl shadow-black/80">
            {/* Question Meta Header */}
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-4">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 rounded-full text-xs font-mono font-medium bg-zinc-900 border border-zinc-700 text-zinc-300">
                  {currentQ.subject}
                </span>
                {currentQ.chapter && (
                  <span className="hidden sm:inline text-xs font-mono text-zinc-500">
                    {currentQ.chapter}
                  </span>
                )}
              </div>

              <span className="text-xs font-mono text-zinc-400">
                Question {currentIndex + 1} of {questions.length}
              </span>
            </div>

            {/* Question Statement */}
            <div>
              <p className="text-lg sm:text-xl font-medium text-zinc-100 leading-relaxed font-sans">
                {currentQ.question}
              </p>
            </div>

            {/* 4 Labeled Option Buttons */}
            <div className="grid grid-cols-1 gap-3 pt-2">
              {currentQ.options.map((optionText, optIndex) => {
                const label = OPTION_LABELS[optIndex];
                const isSelected = selectedOption === optIndex;
                const isCorrectAnswer = optIndex === currentQ.answerIndex;

                // Determine dynamic classes based on instant feedback state
                let buttonStyle =
                  "border-zinc-800 bg-zinc-900/40 hover:bg-zinc-850 hover:border-zinc-700 text-zinc-200";
                let badgeStyle = "bg-zinc-800 border-zinc-700 text-zinc-300";

                if (isAnswered) {
                  if (isSelected && isCorrectAnswer) {
                    // Selected correct option turns green
                    buttonStyle =
                      "border-emerald-500 bg-emerald-950/40 text-emerald-100 shadow-[0_0_20px_rgba(16,185,129,0.25)] ring-1 ring-emerald-500";
                    badgeStyle =
                      "bg-emerald-500 text-zinc-950 border-emerald-400 font-bold";
                  } else if (isSelected && !isCorrectAnswer) {
                    // Selected wrong option turns red
                    buttonStyle =
                      "border-rose-500 bg-rose-950/40 text-rose-100 shadow-[0_0_20px_rgba(244,63,94,0.25)] ring-1 ring-rose-500";
                    badgeStyle =
                      "bg-rose-500 text-zinc-950 border-rose-400 font-bold";
                  } else if (!isSelected && isCorrectAnswer) {
                    // Reveal correct answer in green outline when user missed it
                    buttonStyle =
                      "border-emerald-600/80 bg-emerald-950/20 text-emerald-200 border-dashed";
                    badgeStyle =
                      "bg-emerald-900/80 text-emerald-300 border-emerald-600";
                  } else {
                    // Other unselected options muted
                    buttonStyle = "border-zinc-850 bg-zinc-950/50 text-zinc-500 opacity-50";
                    badgeStyle = "bg-zinc-900 border-zinc-800 text-zinc-600";
                  }
                }

                return (
                  <button
                    key={`${currentQ.id}-opt-${label}`}
                    type="button"
                    disabled={isAnswered}
                    onClick={() => handleSelectOption(optIndex)}
                    className={`w-full p-4 rounded-xl border text-left transition-all duration-150 flex items-start gap-3.5 group active:scale-[0.99] ${buttonStyle}`}
                  >
                    {/* Option Label Badge (A, B, C, D) */}
                    <span
                      className={`inline-flex items-center justify-center w-7 h-7 rounded-lg text-xs font-mono font-bold border transition-colors shrink-0 ${badgeStyle}`}
                    >
                      {label}
                    </span>

                    <span className="text-sm sm:text-base leading-relaxed pt-0.5 flex-1 font-sans">
                      {optionText}
                    </span>

                    {/* Instant Feedback Status Icon */}
                    {isAnswered && (
                      <span className="shrink-0 pt-1">
                        {isCorrectAnswer ? (
                          <svg
                            className="w-5 h-5 text-emerald-400"
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
                        ) : isSelected ? (
                          <svg
                            className="w-5 h-5 text-rose-400"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2.5"
                              d="M6 18L18 6M6 6l12 12"
                            />
                          </svg>
                        ) : null}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Instant Feedback & Explanation Drawer */}
            {isAnswered && (
              <div className="mt-4 p-5 rounded-xl border border-zinc-800 bg-zinc-900/70 flex flex-col gap-3 animate-fade-in">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {selectedOption === currentQ.answerIndex ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-emerald-400">
                        <span className="w-2 h-2 rounded-full bg-emerald-400" />
                        CORRECT VERIFICATION
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold text-rose-400">
                        <span className="w-2 h-2 rounded-full bg-rose-400" />
                        {selectedOption === null
                          ? "TIMEOUT EXPIRED • LOGGED TO NOTEBOOK"
                          : "INCORRECT SELECTION • LOGGED TO NOTEBOOK"}
                      </span>
                    )}
                  </div>

                  <span className="text-[11px] font-mono text-zinc-500">
                    Press <kbd className="text-zinc-300 font-bold">Enter</kbd> to continue
                  </span>
                </div>

                <div className="text-sm text-zinc-300 leading-relaxed font-sans">
                  {currentQ.explanation}
                </div>

                {currentQ.source && (
                  <div className="text-xs font-mono text-zinc-500 border-t border-zinc-800/80 pt-2">
                    Source: {currentQ.source}
                  </div>
                )}
              </div>
            )}

            {/* Bottom Actions */}
            <div className="border-t border-zinc-800/80 pt-4 flex items-center justify-between">
              <span className="text-xs font-mono text-zinc-500">
                {!isAnswered
                  ? "Select option via keys A-D or 1-4"
                  : `Answered in ${timeLimitSeconds - timeLeft}s`}
              </span>

              {isAnswered && (
                <button
                  type="button"
                  onClick={handleNextQuestion}
                  className="px-5 py-2.5 rounded-xl bg-zinc-100 hover:bg-zinc-200 text-zinc-950 font-mono font-semibold text-xs active:scale-95 transition-all flex items-center gap-2 shadow-lg"
                >
                  <span>
                    {currentIndex + 1 < questions.length
                      ? "Next Question"
                      : "Finish Drill"}
                  </span>
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M13 7l5 5m0 0l-5 5m5-5H6"
                    />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* Drill Results Summary */
        <div className="rounded-2xl border border-zinc-800 bg-[#09090b] p-8 sm:p-12 text-center flex flex-col items-center justify-center gap-6 shadow-2xl shadow-black/80">
          <div className="w-16 h-16 rounded-full bg-cyan-950/60 border border-cyan-600/60 flex items-center justify-center text-cyan-400">
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
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </div>

          <div className="flex flex-col gap-2 max-w-md">
            <h3 className="text-2xl font-semibold text-zinc-100">
              Drill Completed
            </h3>
            <p className="text-sm text-zinc-400">
              Scored{" "}
              <span className="font-mono text-emerald-400 font-bold">
                {totalCorrect}/{questions.length} (
                {Math.round((totalCorrect / questions.length) * 100)}%)
              </span>{" "}
              accuracy on timed retrieval drill.
            </p>
          </div>

          {/* Detailed Question Outcomes */}
          <div className="w-full max-w-md flex flex-col gap-2 font-mono text-xs">
            {scoreHistory.map((item, idx) => (
              <div
                key={`score-item-${idx}`}
                className="flex items-center justify-between p-3 rounded-lg bg-zinc-900 border border-zinc-800"
              >
                <div className="flex items-center gap-2">
                  <span className="text-zinc-500">Q{idx + 1}</span>
                  <span className="text-zinc-300">
                    {questions[idx]?.subject || "Item"}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-zinc-500">{item.timeSpent}s</span>
                  {item.isCorrect ? (
                    <span className="text-emerald-400 font-bold">✓ CORRECT</span>
                  ) : (
                    <span className="text-rose-400 font-bold">✕ MISSED</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="pt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={handleRestart}
              className="px-6 py-2.5 rounded-xl bg-zinc-100 text-zinc-950 hover:bg-zinc-200 active:scale-95 font-medium text-xs font-mono transition-all shadow-md"
            >
              Restart MCQ Drill
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default MCQDrill;
