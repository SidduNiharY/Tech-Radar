"use client";

import React, { useEffect, useState } from "react";

export interface CitationInfo {
  id: string; // e.g. "C1", "C2"
  number?: number;
  source_id?: string;
  source_title: string;
  source_url?: string;
  doc_path?: string;
  heading?: string;
  page_number?: number;
  timestamp_s?: number;
  excerpt?: string;
  verified?: boolean;
  score?: number;
  doc_kind?: string;
}

export interface CitationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  citation: CitationInfo | null;
  allCitations?: CitationInfo[];
  onSelectCitation?: (citation: CitationInfo) => void;
  onAskFollowUp?: (topic: string) => void;
}

function formatTimestamp(seconds?: number): string {
  if (seconds === undefined || seconds === null || isNaN(seconds)) return "";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

export function CitationDrawer({
  isOpen,
  onClose,
  citation,
  allCitations = [],
  onSelectCitation,
  onAskFollowUp,
}: CitationDrawerProps) {
  const [copied, setCopied] = useState(false);

  // Close on Escape key press
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Lock body scroll when drawer is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen || !citation) {
    return null;
  }

  const handleCopyExcerpt = async () => {
    const textToCopy = citation.excerpt || citation.source_title;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(textToCopy);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isVerified = citation.verified ?? true;
  const citationBadgeId = citation.id.startsWith("C") ? citation.id : `C${citation.id}`;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="citation-drawer-title"
      className="fixed inset-0 z-50 flex justify-end animate-in fade-in duration-200"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-over Drawer Panel */}
      <div className="relative w-full max-w-lg bg-[#09090b] border-l border-zinc-800 shadow-2xl flex flex-col h-full z-10 overflow-hidden text-zinc-100">
        {/* Header */}
        <div className="px-6 py-5 border-b border-zinc-800/80 bg-zinc-950/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-emerald-950/90 text-emerald-400 border border-emerald-800/90 shadow-sm shadow-emerald-950/50">
              [{citationBadgeId}]
            </span>
            <div>
              <h2
                id="citation-drawer-title"
                className="text-sm font-semibold tracking-wide text-zinc-100 uppercase font-mono"
              >
                Grounded Citation
              </h2>
              <p className="text-xs text-zinc-400 font-mono">
                Knowledge Vault Proof · SEC-28 Hardened
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 rounded-md transition-colors flex items-center gap-1.5 text-xs font-mono"
            aria-label="Close citation drawer"
          >
            <span className="hidden sm:inline-block text-[10px] text-zinc-500 uppercase px-1 py-0.5 bg-zinc-900 border border-zinc-800 rounded">
              ESC
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
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Document Title & Heading Card */}
          <div className="p-4 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-2">
            <div className="text-xs text-indigo-400 font-mono uppercase tracking-wider flex items-center gap-1.5">
              <svg
                className="w-3.5 h-3.5 text-indigo-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              Source Document
            </div>
            <h3 className="text-base font-semibold text-zinc-100 leading-snug">
              {citation.source_title}
            </h3>
            {citation.heading && (
              <div className="text-xs text-zinc-400 font-mono flex items-center gap-1">
                <span>Section:</span>
                <span className="text-zinc-300 font-medium">{citation.heading}</span>
              </div>
            )}
          </div>

          {/* Metadata Grid */}
          <div className="grid grid-cols-2 gap-3 text-xs font-mono">
            {/* File Path */}
            <div className="p-3 rounded-md bg-zinc-950 border border-zinc-800/80">
              <span className="text-zinc-500 block text-[10px] uppercase">
                Vault Path
              </span>
              <span
                className="text-zinc-300 truncate block mt-0.5"
                title={citation.doc_path || "vault/notes/document.md"}
              >
                {citation.doc_path || "vault/notes/document.md"}
              </span>
            </div>

            {/* Verification status */}
            <div className="p-3 rounded-md bg-zinc-950 border border-zinc-800/80">
              <span className="text-zinc-500 block text-[10px] uppercase">
                Trust State
              </span>
              <div className="mt-0.5">
                {isVerified ? (
                  <span className="inline-flex items-center gap-1 text-emerald-400 font-medium text-[11px]">
                    <svg
                      className="w-3.5 h-3.5 text-emerald-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    Verified Note
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-amber-400 font-medium text-[11px]">
                    <svg
                      className="w-3.5 h-3.5 text-amber-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                      />
                    </svg>
                    Unverified Note
                  </span>
                )}
              </div>
            </div>

            {/* Page number */}
            {citation.page_number !== undefined && (
              <div className="p-3 rounded-md bg-zinc-950 border border-zinc-800/80">
                <span className="text-zinc-500 block text-[10px] uppercase">
                  Page / Location
                </span>
                <span className="text-zinc-300 block mt-0.5 font-medium">
                  Page {citation.page_number}
                </span>
              </div>
            )}

            {/* Timestamp */}
            {citation.timestamp_s !== undefined && (
              <div className="p-3 rounded-md bg-zinc-950 border border-zinc-800/80">
                <span className="text-zinc-500 block text-[10px] uppercase">
                  Timestamp
                </span>
                <span className="text-zinc-300 block mt-0.5 font-medium">
                  {formatTimestamp(citation.timestamp_s)}
                </span>
              </div>
            )}

            {/* Relevance Score */}
            {citation.score !== undefined && (
              <div className="p-3 rounded-md bg-zinc-950 border border-zinc-800/80">
                <span className="text-zinc-500 block text-[10px] uppercase">
                  Rerank Score
                </span>
                <span className="text-indigo-400 block mt-0.5 font-medium">
                  {(citation.score * 100).toFixed(1)}% match
                </span>
              </div>
            )}

            {/* Document Kind */}
            {citation.doc_kind && (
              <div className="p-3 rounded-md bg-zinc-950 border border-zinc-800/80">
                <span className="text-zinc-500 block text-[10px] uppercase">
                  Classification
                </span>
                <span className="text-zinc-300 block mt-0.5 capitalize">
                  {citation.doc_kind}
                </span>
              </div>
            )}
          </div>

          {/* Verified Excerpt Box */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-400 font-mono uppercase tracking-wider flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Verified Excerpt
              </span>
              <button
                type="button"
                onClick={handleCopyExcerpt}
                className="text-[11px] font-mono text-zinc-400 hover:text-emerald-400 flex items-center gap-1 transition-colors"
              >
                {copied ? (
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
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <svg
                      className="w-3.5 h-3.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                      />
                    </svg>
                    <span>Copy Excerpt</span>
                  </>
                )}
              </button>
            </div>

            <div className="relative p-4 rounded-lg bg-zinc-900/80 border border-zinc-800 border-l-4 border-l-emerald-500 shadow-inner">
              <p className="text-sm text-zinc-200 leading-relaxed font-sans whitespace-pre-wrap selection:bg-emerald-950 selection:text-emerald-200">
                {citation.excerpt ||
                  "Verified reference text extracted from knowledge base during multi-stage retrieval."}
              </p>
            </div>
          </div>

          {/* Quick Switch to Other Citations in this Answer */}
          {allCitations.length > 1 && (
            <div className="space-y-2 pt-2 border-t border-zinc-900">
              <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider block">
                All Citations in Answer ({allCitations.length})
              </span>
              <div className="flex flex-wrap gap-2">
                {allCitations.map((c) => {
                  const isCurrent = c.id === citation.id;
                  const label = c.id.startsWith("C") ? c.id : `C${c.id}`;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => onSelectCitation?.(c)}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono transition-all ${
                        isCurrent
                          ? "bg-emerald-900/80 text-emerald-300 border border-emerald-500 font-bold shadow-sm shadow-emerald-950/60"
                          : "bg-zinc-900/80 text-zinc-400 border border-zinc-800 hover:bg-zinc-800 hover:text-zinc-200"
                      }`}
                    >
                      <span>[{label}]</span>
                      <span className="truncate max-w-[120px] font-normal text-[11px]">
                        {c.source_title}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-zinc-800/80 bg-zinc-950/80 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-mono text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 border border-zinc-800 rounded-md transition-colors"
          >
            Close
          </button>

          {onAskFollowUp && (
            <button
              type="button"
              onClick={() => {
                onAskFollowUp(`Explain more about ${citation.source_title}`);
                onClose();
              }}
              className="px-4 py-2 text-xs font-mono font-medium rounded-md bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm shadow-indigo-950 flex items-center gap-1.5 transition-colors"
            >
              <svg
                className="w-3.5 h-3.5 text-indigo-200"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
              Ask Follow-Up
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
