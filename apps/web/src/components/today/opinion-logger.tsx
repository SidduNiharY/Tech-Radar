"use client";

import React, { useState, useId } from "react";

export interface OpinionLoggerProps {
  briefingId?: string;
  messageId?: number | string;
  headline?: string;
  activeBriefingStories?: Array<{ id: number | string; title: string }>;
  onTakeSubmitted?: (take: {
    briefingId: string;
    messageId: number | string;
    text: string;
    createdAt: string;
  }) => void;
  className?: string;
}

export type SubmissionStatus = "idle" | "submitting" | "submitted" | "error";

const MAX_CHARACTERS = 500;

export function OpinionLogger({
  briefingId = "briefing_live_today",
  messageId: initialMessageId,
  headline: initialHeadline,
  activeBriefingStories = [],
  onTakeSubmitted,
  className = "",
}: OpinionLoggerProps) {
  const inputId = useId();
  const [selectedMessageId, setSelectedMessageId] = useState<number | string>(
    initialMessageId ?? (activeBriefingStories[0]?.id ?? 101)
  );
  const [opinionText, setOpinionText] = useState<string>("");
  const [status, setStatus] = useState<SubmissionStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastSubmittedTake, setLastSubmittedTake] = useState<{
    text: string;
    messageId: number | string;
    createdAt: string;
  } | null>(null);

  // Sync if initialMessageId changes
  React.useEffect(() => {
    if (initialMessageId !== undefined) {
      setSelectedMessageId(initialMessageId);
    }
  }, [initialMessageId]);

  const charactersRemaining = MAX_CHARACTERS - opinionText.length;
  const isOverLimit = charactersRemaining < 0;
  const isSubmittable = opinionText.trim().length > 0 && !isOverLimit && status !== "submitting";

  const currentHeadline =
    initialHeadline ||
    activeBriefingStories.find((s) => String(s.id) === String(selectedMessageId))?.title ||
    `Briefing Intel Message #${selectedMessageId}`;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!opinionText.trim()) {
      setErrorMessage("Please enter your prediction before submitting.");
      setStatus("error");
      return;
    }

    if (opinionText.length > MAX_CHARACTERS) {
      setErrorMessage(
        `Prediction exceeds maximum allowed limit of ${MAX_CHARACTERS} characters (currently ${opinionText.length}).`
      );
      setStatus("error");
      return;
    }

    setStatus("submitting");
    setErrorMessage(null);

    try {
      // Simulate submission network call or ticket creation
      await new Promise((resolve) => setTimeout(resolve, 350));

      const submittedRecord = {
        briefingId,
        messageId: selectedMessageId,
        text: opinionText.trim(),
        createdAt: new Date().toISOString(),
      };

      setLastSubmittedTake(submittedRecord);
      setStatus("submitted");
      if (onTakeSubmitted) {
        onTakeSubmitted(submittedRecord);
      }
    } catch (err: unknown) {
      setStatus("error");
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to record prediction. Please retry."
      );
    }
  };

  const handleReset = () => {
    setOpinionText("");
    setStatus("idle");
    setErrorMessage(null);
  };

  return (
    <section
      data-testid="opinion-logger"
      className={`relative rounded-xl border border-zinc-800/80 bg-[#090a0f]/95 p-5 md:p-6 backdrop-blur-md shadow-2xl transition-all duration-300 hover:border-violet-500/30 ${className}`}
    >
      {/* Top Hairline Violet Accent */}
      <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-violet-500/40 to-transparent" />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pb-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-violet-400 shadow-[0_0_8px_rgba(167,139,250,0.8)]" />
          <h4 className="font-mono text-xs md:text-sm font-semibold uppercase tracking-wider text-violet-300">
            My Take // Prediction Ledger
          </h4>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-400">
          <span className="px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800">
            Tied: #{selectedMessageId}
          </span>
          <span className="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
            SEC-41 Auth
          </span>
        </div>
      </div>

      {/* Story Context Target */}
      <div className="mt-3.5 mb-3 rounded-lg border border-zinc-800/60 bg-zinc-950/60 p-3">
        <div className="text-[11px] font-mono text-zinc-500 mb-1 flex items-center justify-between">
          <span>Target Briefing Item:</span>
          {activeBriefingStories.length > 1 && (
            <label className="text-violet-400 hover:underline cursor-pointer">
              Switch Target
              <select
                aria-label="Target briefing story selector"
                value={selectedMessageId}
                onChange={(e) => setSelectedMessageId(e.target.value)}
                className="sr-only"
              >
                {activeBriefingStories.map((s) => (
                  <option key={s.id} value={s.id}>
                    #{s.id}: {s.title}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <p className="text-sm font-medium text-zinc-200 line-clamp-2">
          {currentHeadline}
        </p>
      </div>

      {/* Submission Form */}
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div>
          <div className="flex items-center justify-between text-xs font-mono mb-1.5">
            <label htmlFor={inputId} className="text-zinc-400">
              Your Thesis / Prediction (Max {MAX_CHARACTERS} chars):
            </label>

            {/* Countdown Display */}
            <span
              data-testid="char-countdown"
              className={`font-mono text-xs font-medium px-2 py-0.5 rounded ${
                isOverLimit
                  ? "bg-rose-950/80 text-rose-400 border border-rose-600/50"
                  : charactersRemaining <= 50
                    ? "bg-amber-950/80 text-amber-300 border border-amber-600/50"
                    : "bg-zinc-900 text-zinc-400 border border-zinc-800"
              }`}
            >
              {charactersRemaining} chars remaining
            </span>
          </div>

          <textarea
            id={inputId}
            data-testid="opinion-textarea"
            rows={4}
            maxLength={MAX_CHARACTERS + 20}
            value={opinionText}
            onChange={(e) => {
              setOpinionText(e.target.value);
              if (status === "error") setErrorMessage(null);
            }}
            placeholder="Record your falsifiable forecast, macro implication, or critique. Example: 'RBI repo rate will remain at 6.5% through Q1 before easing if CPI remains sub-5.0%'..."
            className="w-full rounded-lg border border-zinc-800 bg-[#06070a] p-3 text-sm text-zinc-100 placeholder-zinc-600 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 font-sans transition-all resize-none"
          />
        </div>

        {/* Error Notification */}
        {status === "error" && errorMessage && (
          <div
            data-testid="opinion-error"
            className="rounded-lg border border-rose-500/40 bg-rose-950/40 p-3 text-xs font-mono text-rose-300"
          >
            ⚠️ {errorMessage}
          </div>
        )}

        {/* Success Banner */}
        {status === "submitted" && lastSubmittedTake && (
          <div
            data-testid="opinion-success"
            className="rounded-lg border border-emerald-500/40 bg-emerald-950/50 p-3 text-xs font-mono text-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.1)]"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
                <span>✓</span> Take Logged to Active Prediction Ledger
              </span>
              <span className="text-[10px] text-zinc-500">
                {new Date(lastSubmittedTake.createdAt).toLocaleTimeString()}
              </span>
            </div>
            <p className="text-zinc-300 italic font-sans text-xs">
              &ldquo;{lastSubmittedTake.text}&rdquo;
            </p>
          </div>
        )}

        {/* Action Controls */}
        <div className="flex items-center justify-between pt-1">
          <div className="text-[11px] font-mono text-zinc-500">
            {status === "submitted" ? (
              <button
                type="button"
                onClick={handleReset}
                className="text-violet-400 hover:text-violet-300 transition-colors underline"
              >
                Log another prediction
              </button>
            ) : (
              <span>Immutable once verified against future outcomes</span>
            )}
          </div>

          <button
            type="submit"
            data-testid="submit-take-btn"
            disabled={!isSubmittable}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-mono font-semibold transition-all shadow-md ${
              isSubmittable
                ? "bg-violet-600 text-white hover:bg-violet-500 hover:shadow-[0_0_20px_rgba(139,92,246,0.3)] cursor-pointer"
                : "bg-zinc-800 text-zinc-500 cursor-not-allowed border border-zinc-700/50"
            }`}
          >
            {status === "submitting" ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Logging take...
              </>
            ) : (
              <>
                <span>⚡</span>
                Submit Prediction
              </>
            )}
          </button>
        </div>
      </form>
    </section>
  );
}
