"use client";

import React, { useState } from "react";

export type BriefingSection = "Tech" | "India" | "World" | "Economy" | "Science" | string;

export interface BriefingStory {
  id?: string | number;
  cluster_id?: string;
  title: string;
  section: BriefingSection;
  domains?: string[];
  domain_count?: number;
  verified_headline?: boolean;
  why?: string;
  how_it_affects_me?: string;
  exam_tags?: string[];
  relevance?: number;
  published_at?: string;
  summary?: string;
}

export interface BriefingCardProps {
  item: BriefingStory;
  defaultExpanded?: boolean;
  onSelectTake?: (item: BriefingStory) => void;
  onAskDeepDive?: (item: BriefingStory) => void;
}

const SECTION_STYLES: Record<string, { badge: string; borderGlow: string }> = {
  Tech: {
    badge: "bg-violet-950/70 text-violet-300 border-violet-500/40",
    borderGlow: "hover:border-violet-500/50 hover:shadow-[0_0_25px_rgba(139,92,246,0.15)]",
  },
  India: {
    badge: "bg-amber-950/70 text-amber-300 border-amber-500/40",
    borderGlow: "hover:border-amber-500/50 hover:shadow-[0_0_25px_rgba(245,158,11,0.12)]",
  },
  World: {
    badge: "bg-sky-950/70 text-sky-300 border-sky-500/40",
    borderGlow: "hover:border-sky-500/50 hover:shadow-[0_0_25px_rgba(14,165,233,0.12)]",
  },
  Economy: {
    badge: "bg-emerald-950/70 text-emerald-300 border-emerald-500/40",
    borderGlow: "hover:border-emerald-500/50 hover:shadow-[0_0_25px_rgba(16,185,129,0.15)]",
  },
  Science: {
    badge: "bg-fuchsia-950/70 text-fuchsia-300 border-fuchsia-500/40",
    borderGlow: "hover:border-fuchsia-500/50 hover:shadow-[0_0_25px_rgba(217,70,239,0.15)]",
  },
};

export function BriefingCard({
  item,
  defaultExpanded = true,
  onSelectTake,
  onAskDeepDive,
}: BriefingCardProps) {
  const [isExpanded, setIsExpanded] = useState<boolean>(defaultExpanded);
  const [copied, setCopied] = useState<boolean>(false);

  const sectionStyle = SECTION_STYLES[item.section] || {
    badge: "bg-zinc-900/80 text-zinc-300 border-zinc-700/60",
    borderGlow: "hover:border-zinc-600/50 hover:shadow-[0_0_20px_rgba(255,255,255,0.05)]",
  };

  const domainCount =
    typeof item.domain_count === "number"
      ? item.domain_count
      : Array.isArray(item.domains)
        ? item.domains.length
        : 1;

  const isVerified = item.verified_headline ?? domainCount >= 3;

  const handleCopy = async () => {
    try {
      const summaryText = `${item.title}\n\nWhy it matters: ${item.why || "N/A"}\nHow it affects me: ${item.how_it_affects_me || "N/A"}`;
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(summaryText);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // clipboard access fallback
    }
  };

  return (
    <article
      data-testid="briefing-card"
      className={`group relative rounded-xl border border-zinc-800/80 bg-[#090a0f]/90 p-5 md:p-6 backdrop-blur-md transition-all duration-300 ${sectionStyle.borderGlow}`}
    >
      {/* Hairline subtle top light accent */}
      <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-violet-500/30 to-transparent" />

      {/* Header bar: Section Badge + Verified Domains Tag + Relevance */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 pb-3 border-b border-zinc-800/60 text-xs font-mono">
        <div className="flex items-center gap-2">
          {/* Section Badge */}
          <span
            data-testid="section-badge"
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full font-semibold border tracking-wider uppercase text-[11px] ${sectionStyle.badge}`}
          >
            {item.section}
          </span>

          {/* Verified Domain Count Tag */}
          <span
            data-testid="verified-domains-tag"
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded font-medium border text-[11px] ${
              isVerified
                ? "bg-emerald-950/70 text-emerald-400 border-emerald-500/40 shadow-[0_0_12px_rgba(16,185,129,0.15)]"
                : "bg-zinc-900/70 text-zinc-400 border-zinc-700/50"
            }`}
          >
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full ${
                isVerified ? "bg-emerald-400 animate-pulse" : "bg-zinc-500"
              }`}
            />
            [{domainCount} domain{domainCount !== 1 ? "s" : ""} verified]
          </span>
        </div>

        {/* Exam Tags / Relevance */}
        <div className="flex items-center gap-1.5">
          {item.exam_tags?.map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 rounded bg-zinc-900/90 text-zinc-400 border border-zinc-800 text-[10px]"
            >
              {tag}
            </span>
          ))}
          {typeof item.relevance === "number" && (
            <span className="text-zinc-500 text-[10px]">
              rel: {(item.relevance * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      {/* Main Headline */}
      <div className="mt-3.5 mb-3">
        <h3
          data-testid="briefing-headline"
          className="text-base md:text-lg font-semibold tracking-tight text-zinc-100 group-hover:text-violet-200 transition-colors leading-snug"
        >
          {item.title}
        </h3>
        {item.summary && (
          <p className="mt-1.5 text-sm text-zinc-400 line-clamp-2 leading-relaxed">
            {item.summary}
          </p>
        )}
      </div>

      {/* Domains cited pill list */}
      {item.domains && item.domains.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3.5">
          <span className="text-[11px] font-mono text-zinc-500">Sources:</span>
          {item.domains.map((dom) => (
            <span
              key={dom}
              className="text-[11px] font-mono px-2 py-0.5 rounded bg-zinc-900/80 text-zinc-400 border border-zinc-800/80 hover:border-zinc-700"
            >
              {dom}
            </span>
          ))}
        </div>
      )}

      {/* Collapsible toggle button */}
      <div className="pt-2 border-t border-zinc-900">
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          aria-expanded={isExpanded}
          className="w-full flex items-center justify-between py-1 text-xs font-mono text-violet-400 hover:text-violet-300 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <span className="text-xs">{isExpanded ? "▾" : "▸"}</span>
            {isExpanded ? "Collapse Intel Insights" : "Expand Intel Insights (\"Why\" & \"For me\")"}
          </span>
          <span className="text-zinc-500 text-[11px]">
            {isExpanded ? "Hide" : "Show"}
          </span>
        </button>

        {/* Collapsible Insights Panel */}
        {isExpanded && (
          <div
            data-testid="collapsible-insights"
            className="mt-3 space-y-2.5 pt-1 animate-in fade-in duration-200"
          >
            {/* Why it matters block */}
            <div
              data-testid="insight-why"
              className="relative rounded-lg border-l-2 border-violet-500 bg-violet-950/20 p-3 pl-3.5 text-xs md:text-sm text-zinc-200 shadow-sm"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-violet-400">
                  ⚡ Why it matters
                </span>
              </div>
              <p className="leading-relaxed text-zinc-300">
                {item.why || "Key development in this domain impacting systemic risk and policy velocity."}
              </p>
            </div>

            {/* How it affects me block */}
            <div
              data-testid="insight-affects"
              className="relative rounded-lg border-l-2 border-emerald-500 bg-emerald-950/20 p-3 pl-3.5 text-xs md:text-sm text-zinc-200 shadow-sm"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-emerald-400">
                  🎯 How it affects me
                </span>
              </div>
              <p className="leading-relaxed text-zinc-300">
                {item.how_it_affects_me || "Direct implications for personal capital allocation, system architecture, and daily study."}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Card Footer Actions */}
      <div className="mt-4 pt-3 flex flex-wrap items-center justify-between gap-2 border-t border-zinc-800/60">
        <div className="flex items-center gap-2">
          {onSelectTake && (
            <button
              type="button"
              onClick={() => onSelectTake(item)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/20 text-violet-300 border border-violet-500/40 hover:bg-violet-600/30 hover:border-violet-400 text-xs font-mono font-medium transition-all shadow-[0_0_15px_rgba(139,92,246,0.15)]"
            >
              <span>✎</span>
              My take
            </button>
          )}

          {onAskDeepDive && (
            <button
              type="button"
              onClick={() => onAskDeepDive(item)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 text-zinc-300 border border-zinc-700/60 hover:border-zinc-500 hover:text-white text-xs font-mono transition-all"
            >
              <span>🔍</span>
              Go deeper
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-500 hover:text-zinc-300 transition-colors"
          title="Copy headline and insights"
        >
          <span>{copied ? "✓ Copied" : "⧉ Copy Intel"}</span>
        </button>
      </div>
    </article>
  );
}
