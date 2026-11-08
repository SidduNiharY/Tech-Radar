"use client";

import React, { useState, useMemo } from "react";
import { EconomyCardGrid } from "@/components/world/economy-card";
import { CausalityTree } from "@/components/world/causality-tree";

export interface GlossaryTermItem {
  term: string;
  category: "Economy" | "Technology" | "Geopolitics" | string;
  definition: string;
  synonyms: string[];
  related_terms: string[];
  importance: number;
}

export const BASELINE_GLOSSARY: GlossaryTermItem[] = [
  {
    term: "Repo Rate",
    category: "Economy",
    definition:
      "The interest rate at which the central bank lends money to commercial banks in the event of any shortfall of funds.",
    synonyms: ["repurchase rate", "repurchase agreement rate"],
    related_terms: ["Inflation", "GDP", "Fiscal Deficit"],
    importance: 1.0,
  },
  {
    term: "GDP",
    category: "Economy",
    definition:
      "Gross Domestic Product; the total monetary or market value of all finished goods and services produced within a country in a specific time period.",
    synonyms: ["Gross Domestic Product"],
    related_terms: ["Inflation", "Fiscal Deficit", "Repo Rate"],
    importance: 1.0,
  },
  {
    term: "Inflation",
    category: "Economy",
    definition:
      "The rate of increase in prices of goods and services over a given period of time, reducing currency purchasing power.",
    synonyms: ["price inflation"],
    related_terms: ["Repo Rate", "GDP", "Fiscal Deficit"],
    importance: 1.0,
  },
  {
    term: "Fiscal Deficit",
    category: "Economy",
    definition:
      "The gap between the government's total expenditure and its total receipts excluding borrowings.",
    synonyms: ["budget deficit"],
    related_terms: ["GDP", "Inflation"],
    importance: 1.0,
  },
  {
    term: "RAG",
    category: "Technology",
    definition:
      "Retrieval-Augmented Generation; a technique that enriches large language model prompts with relevant retrieved knowledge from external datasets.",
    synonyms: ["Retrieval-Augmented Generation"],
    related_terms: ["Transformer"],
    importance: 1.0,
  },
  {
    term: "Transformer",
    category: "Technology",
    definition:
      "A neural network architecture based on self-attention mechanisms, widely used in state-of-the-art natural language processing and multimodal AI.",
    synonyms: ["Transformer Architecture"],
    related_terms: ["RAG"],
    importance: 1.0,
  },
  {
    term: "eBPF",
    category: "Technology",
    definition:
      "Extended Berkeley Packet Filter; a kernel technology enabling sandboxed programs to execute safely within the Linux kernel without kernel modification.",
    synonyms: ["Extended Berkeley Packet Filter"],
    related_terms: [],
    importance: 1.0,
  },
];

const SAMPLE_ANALYSIS_MARKDOWN = `The latest macroeconomic policy consensus demonstrates that while the central bank maintains a steady [[Repo Rate]] of 6.50%, national [[GDP]] growth continues to expand at 7.2% annual velocity. Sustained food supply interventions have helped anchor [[Inflation]] near 5.1%, even as the target [[Fiscal Deficit]] trajectory remains tightly monitored. In parallel, local engineering pipelines are applying [[RAG]] on top of local [[Transformer]] architectures, with security containment hardened at the OS boundary using [[eBPF]] kernel sandboxing.`;

export default function WorldKnowledgeScreenPage() {
  const [activeTab, setActiveTab] = useState<"all" | "economy" | "causality" | "glossary">("all");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("All");
  const [selectedTerm, setSelectedTerm] = useState<GlossaryTermItem | null>(BASELINE_GLOSSARY[0]);
  const [interactiveText, setInteractiveText] = useState<string>(SAMPLE_ANALYSIS_MARKDOWN);

  const categories = ["All", "Economy", "Technology"];

  const filteredTerms = useMemo(() => {
    return BASELINE_GLOSSARY.filter((t) => {
      const matchesCategory =
        selectedCategory === "All" || t.category.toLowerCase() === selectedCategory.toLowerCase();
      const matchesQuery =
        searchTerm.trim() === "" ||
        t.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.definition.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.synonyms.some((s) => s.toLowerCase().includes(searchTerm.toLowerCase()));
      return matchesCategory && matchesQuery;
    });
  }, [searchTerm, selectedCategory]);

  const handleSelectTermByName = (termName: string) => {
    const found = BASELINE_GLOSSARY.find(
      (t) => t.term.toLowerCase() === termName.trim().toLowerCase()
    );
    if (found) {
      setSelectedTerm(found);
      // Scroll to glossary section if needed
      if (typeof document !== "undefined") {
        const el = document.getElementById("glossary-inspector-section");
        if (el) {
          el.scrollIntoView({ behavior: "smooth" });
        }
      }
    }
  };

  /**
   * Parse text containing [[term]] syntax and render interactive wiki-link pills
   */
  const renderWikiLinkedText = (text: string) => {
    const parts = text.split(/(\[\[[^\]]+\]\])/g);
    return parts.map((part, index) => {
      const match = part.match(/^\[\[([^\]]+)\]\]$/);
      if (match) {
        const termName = match[1];
        const isMatchedInGlossary = BASELINE_GLOSSARY.some(
          (t) => t.term.toLowerCase() === termName.toLowerCase()
        );
        return (
          <button
            key={index}
            type="button"
            data-testid={`wiki-link-${termName.toLowerCase().replace(/\s+/g, "-")}`}
            onClick={() => handleSelectTermByName(termName)}
            className={`inline-flex items-center gap-1 font-mono text-xs font-semibold px-2 py-0.5 mx-0.5 rounded transition-all cursor-pointer ${
              isMatchedInGlossary
                ? "bg-violet-950/70 text-violet-300 border border-violet-500/50 hover:bg-violet-900/90 hover:border-violet-400 shadow-[0_0_12px_rgba(139,92,246,0.2)]"
                : "bg-zinc-800 text-zinc-400 border border-zinc-700"
            }`}
            title={`Click to inspect glossary definition for [[${termName}]]`}
          >
            <span>[[{termName}]]</span>
          </button>
        );
      }
      return <span key={index}>{part}</span>;
    });
  };

  return (
    <div className="min-h-screen bg-[#07080c] text-zinc-100 font-sans antialiased pb-24 selection:bg-violet-600/30 selection:text-violet-200">
      {/* Background ambient lighting */}
      <div className="fixed inset-0 pointer-events-none bg-[radial-gradient(ellipse_80%_80%_at_50%_-20%,rgba(139,92,246,0.1),rgba(255,255,255,0))]" />

      <div className="relative mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 pt-8 md:pt-12 space-y-10">
        {/* Top Header */}
        <header className="border-b border-zinc-800/80 pb-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1.5 font-mono text-xs">
                <span className="flex h-2 w-2 rounded-full bg-violet-400 shadow-[0_0_8px_rgba(167,139,250,0.8)]" />
                <span className="text-zinc-400">TECHRADAR WORLD</span>
                <span className="text-zinc-600">//</span>
                <span className="text-emerald-400">GLOBAL KNOWLEDGE GRAPH</span>
              </div>
              <h1 className="text-2xl sm:text-3xl md:text-4xl font-extrabold tracking-tight text-white">
                World Knowledge & Macro Intelligence
              </h1>
              <p className="mt-1 font-mono text-xs sm:text-sm text-zinc-400">
                Macroeconomic Indicators · Causal Transmission Chains · Terminology Ontology
              </p>
            </div>

            {/* Quick Navigation Filter Pills */}
            <nav className="flex items-center gap-2 bg-zinc-950/80 p-1 rounded-lg border border-zinc-800/80 font-mono text-xs">
              {(
                [
                  { id: "all", label: "Unified View" },
                  { id: "economy", label: "Economy" },
                  { id: "causality", label: "Causality" },
                  { id: "glossary", label: "Glossary" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-3 py-1 rounded-md transition-all ${
                    activeTab === tab.id
                      ? "bg-violet-600 text-white font-medium shadow-md shadow-violet-950"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </header>

        {/* SECTION 1: Macroeconomic Indicators */}
        {(activeTab === "all" || activeTab === "economy") && (
          <div className="animate-in fade-in duration-300">
            <EconomyCardGrid
              lastUpdated="2026-11-08 12:00:00 UTC"
            />
          </div>
        )}

        {/* SECTION 2: Causality Chain Explorer */}
        {(activeTab === "all" || activeTab === "causality") && (
          <div className="animate-in fade-in duration-300">
            <CausalityTree />
          </div>
        )}

        {/* SECTION 3: Dynamic Terminology Glossary & Interactive Wiki-Links */}
        {(activeTab === "all" || activeTab === "glossary") && (
          <section
            id="glossary-inspector-section"
            data-testid="world-glossary-section"
            className="rounded-xl border border-zinc-800/80 bg-[#090a0f]/95 p-5 md:p-6 backdrop-blur-md shadow-2xl space-y-6"
          >
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-zinc-800/60">
              <div className="flex items-center gap-2">
                <span className="flex h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
                <h3 className="font-mono text-xs uppercase tracking-wider font-semibold text-zinc-300">
                  Dynamic Terminology Glossary &amp; Wiki-Link Ontology
                </h3>
              </div>
              <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
                [[term]] Bidirectional Resolving
              </span>
            </div>

            {/* Interactive Wiki-Link Text Reader / Sandbox */}
            <div className="rounded-xl border border-zinc-800/80 bg-zinc-950/80 p-4 md:p-5">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs text-zinc-400 uppercase tracking-wider font-semibold">
                  📖 Interactive Reader: Tap any [[wiki-link]] to inspect
                </span>
                <span className="font-mono text-[11px] text-violet-400">
                  Live Ontology Parser
                </span>
              </div>
              <div
                data-testid="wiki-reader-content"
                className="text-sm md:text-base text-zinc-300 leading-relaxed font-sans"
              >
                {renderWikiLinkedText(interactiveText)}
              </div>
            </div>

            {/* Glossary Index & Term Inspector Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left Column: Search & Term Pills List */}
              <div className="lg:col-span-5 space-y-4">
                {/* Search Bar & Category Filter */}
                <div className="space-y-2.5">
                  <input
                    type="text"
                    data-testid="glossary-search-input"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search terms, definitions, synonyms..."
                    className="w-full rounded-lg border border-zinc-800 bg-[#06070a] px-3.5 py-2 text-xs font-mono text-zinc-100 placeholder-zinc-600 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all"
                  />

                  <div className="flex items-center gap-1.5 font-mono text-xs">
                    {categories.map((cat) => (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => setSelectedCategory(cat)}
                        className={`px-2.5 py-1 rounded text-[11px] transition-all ${
                          selectedCategory === cat
                            ? "bg-violet-600/30 text-violet-300 border border-violet-500/50 font-semibold"
                            : "bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 border border-transparent"
                        }`}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Term List */}
                <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                  {filteredTerms.map((termItem) => {
                    const isSelected = selectedTerm?.term === termItem.term;
                    return (
                      <div
                        key={termItem.term}
                        data-testid={`term-item-${termItem.term}`}
                        onClick={() => setSelectedTerm(termItem)}
                        className={`p-3 rounded-lg border transition-all cursor-pointer ${
                          isSelected
                            ? "border-violet-500 bg-violet-950/30 shadow-[0_0_15px_rgba(139,92,246,0.15)]"
                            : "border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-mono text-xs font-semibold text-zinc-100">
                            {termItem.term}
                          </span>
                          <span
                            className={`font-mono text-[10px] px-2 py-0.5 rounded border ${
                              termItem.category === "Economy"
                                ? "bg-emerald-950/60 text-emerald-400 border-emerald-500/30"
                                : "bg-violet-950/60 text-violet-300 border-violet-500/30"
                            }`}
                          >
                            {termItem.category}
                          </span>
                        </div>
                        <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed">
                          {termItem.definition}
                        </p>
                      </div>
                    );
                  })}

                  {filteredTerms.length === 0 && (
                    <div className="p-4 rounded-lg border border-zinc-800 text-center font-mono text-xs text-zinc-500">
                      No glossary terms matching &ldquo;{searchTerm}&rdquo;.
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Term Definition Inspector */}
              <div className="lg:col-span-7">
                {selectedTerm ? (
                  <div
                    data-testid="term-inspector-card"
                    className="rounded-xl border border-zinc-800 bg-[#0c0d14] p-5 md:p-6 space-y-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-zinc-800">
                      <div className="flex items-center gap-2">
                        <h4 className="text-lg font-bold text-white tracking-tight">
                          {selectedTerm.term}
                        </h4>
                        <span
                          className={`font-mono text-xs px-2.5 py-0.5 rounded-full border ${
                            selectedTerm.category === "Economy"
                              ? "bg-emerald-950/70 text-emerald-300 border-emerald-500/40"
                              : "bg-violet-950/70 text-violet-300 border-violet-500/40"
                          }`}
                        >
                          {selectedTerm.category}
                        </span>
                      </div>
                      <span className="font-mono text-xs text-zinc-500">
                        Importance: {(selectedTerm.importance * 100).toFixed(0)}%
                      </span>
                    </div>

                    {/* Definition */}
                    <div>
                      <span className="font-mono text-[11px] uppercase tracking-wider text-zinc-500 block mb-1">
                        Authoritative Definition:
                      </span>
                      <p className="text-sm md:text-base text-zinc-200 leading-relaxed font-sans">
                        {selectedTerm.definition}
                      </p>
                    </div>

                    {/* Synonyms */}
                    {selectedTerm.synonyms.length > 0 && (
                      <div>
                        <span className="font-mono text-[11px] uppercase tracking-wider text-zinc-500 block mb-1.5">
                          Recognized Synonyms &amp; Aliases:
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {selectedTerm.synonyms.map((syn) => (
                            <span
                              key={syn}
                              className="font-mono text-xs px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300"
                            >
                              {syn}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Related Terms (Clickable wiki-links) */}
                    {selectedTerm.related_terms.length > 0 && (
                      <div className="pt-2 border-t border-zinc-800/80">
                        <span className="font-mono text-[11px] uppercase tracking-wider text-zinc-500 block mb-2">
                          Directly Related Concepts (Click to traverse):
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {selectedTerm.related_terms.map((rel) => (
                            <button
                              key={rel}
                              type="button"
                              onClick={() => handleSelectTermByName(rel)}
                              className="font-mono text-xs px-3 py-1 rounded bg-violet-950/50 text-violet-300 border border-violet-500/30 hover:bg-violet-900/60 hover:border-violet-400 transition-all cursor-pointer flex items-center gap-1"
                            >
                              <span>[[{rel}]]</span>
                              <span>➔</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-xl border border-zinc-800 bg-[#0c0d14] p-8 text-center text-zinc-500 font-mono text-xs">
                    Select a term from the index to view its full definition.
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
