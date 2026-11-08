"use client";

/**
 * Library Screen: Document browser, upload zone, and "Ask this PDF" scoped query trigger.
 * Spec: 02 §5.14, 05 §3, Decision D48.
 */

import React, { useState, useMemo } from "react";
import { UploadZone, UploadItem } from "../../components/library/upload-zone";

export interface LibraryDoc {
  id: string;
  title: string;
  filename: string;
  filetype: "pdf" | "epub" | "docx" | "txt";
  size_bytes: number;
  pages?: number;
  chapters_count: number;
  chunks_count: number;
  sha256: string;
  mode: string; // "0o600"
  origin: "library" | "upload";
  ingested_at: string;
  sample_prompts: string[];
}

const INITIAL_LIBRARY_DOCS: LibraryDoc[] = [
  {
    id: "doc-101",
    title: "Indian Economy (15th Edition) — Ramesh Singh",
    filename: "Indian_Economy_15th_Ed.pdf",
    filetype: "pdf",
    size_bytes: 42_120_800,
    pages: 842,
    chapters_count: 22,
    chunks_count: 4_120,
    sha256: "b45a72df81c496c90184e1b827ac32ef8a7c290114092bba40192dfaa19ec23b",
    mode: "0o600",
    origin: "library",
    ingested_at: "2026-11-06",
    sample_prompts: [
      "Explain the Monetary Policy Committee (MPC) transmission mechanism in Chapter 7",
      "What are the major structural differences between FRBM 2003 and 2018 amendments?",
      "Generate 5 exam flashcards on GST Council voting weights",
    ],
  },
  {
    id: "doc-102",
    title: "Modern Operating Systems (4th Ed) — Andrew Tanenbaum",
    filename: "Modern_Operating_Systems_Tanenbaum.pdf",
    filetype: "pdf",
    size_bytes: 28_640_100,
    pages: 1_136,
    chapters_count: 14,
    chunks_count: 5_820,
    sha256: "17ac981fbb4e11fa0024bb67a44f8102d9c123bb091aeef18817bca82133d02a",
    mode: "0o600",
    origin: "library",
    ingested_at: "2026-11-05",
    sample_prompts: [
      "Compare Peterson's solution vs hardware atomic TSL instructions in mutual exclusion",
      "How does the Linux CFS (Completely Fair Scheduler) calculate vruntime?",
      "Explain the four conditions for Coffman deadlocks and prevention strategies",
    ],
  },
  {
    id: "doc-103",
    title: "Distributed Systems: Principles and Paradigms",
    filename: "Distributed_Systems_Paradigms.epub",
    filetype: "epub",
    size_bytes: 14_820_500,
    pages: 680,
    chapters_count: 11,
    chunks_count: 2_190,
    sha256: "5d04b87d21a9c1938b812efaa8123c71049bba1e9841bbce82937012afbb0124",
    mode: "0o600",
    origin: "upload",
    ingested_at: "2026-11-07",
    sample_prompts: [
      "Explain Vector Clocks and causal consistency ordering in distributed storage",
      "How does Raft handle split-vote leadership elections?",
      "What is the difference between 2-Phase Commit and 3-Phase Commit failure recovery?",
    ],
  },
  {
    id: "doc-104",
    title: "Indian Polity & Constitutional Governance — M. Laxmikanth",
    filename: "Indian_Polity_Governance.pdf",
    filetype: "pdf",
    size_bytes: 36_910_000,
    pages: 920,
    chapters_count: 35,
    chunks_count: 4_680,
    sha256: "8e9201fba419024b8102eac331904128fba10291ba440182914ba19ec02194bb",
    mode: "0o600",
    origin: "library",
    ingested_at: "2026-11-06",
    sample_prompts: [
      "Explain Article 32 vs Article 226 scope of writ jurisdiction",
      "What constitutes the Basic Structure doctrine under Kesavananda Bharati?",
      "Draft a 250-word synthesis of anti-defection provisions in the Tenth Schedule",
    ],
  },
  {
    id: "doc-105",
    title: "Cognitive Science & Memory Retention Notes",
    filename: "Cognitive_Science_Notes.docx",
    filetype: "docx",
    size_bytes: 2_450_000,
    pages: 180,
    chapters_count: 6,
    chunks_count: 680,
    sha256: "33190facb01928374bb012e84712039481903baec91024bb819203ca91048bce",
    mode: "0o600",
    origin: "upload",
    ingested_at: "2026-11-08",
    sample_prompts: [
      "Explain the FSRS spaced repetition stability and retrievability equations",
      "How does dual-coding theory facilitate long-term conceptual retention?",
      "Synthesize active recall strategies for technical curriculum",
    ],
  },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function truncateHash(hash: string): string {
  if (hash.length <= 16) return hash;
  return `${hash.slice(0, 8)}...${hash.slice(-8)}`;
}

export default function LibraryPage() {
  const [docs, setDocs] = useState<LibraryDoc[]>(INITIAL_LIBRARY_DOCS);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "pdf" | "epub" | "docx">("all");
  const [showUploadZone, setShowUploadZone] = useState<boolean>(true);

  // Scoped Query "Ask this PDF" Modal State
  const [scopedDoc, setScopedDoc] = useState<LibraryDoc | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(true);
  const [querySubmitted, setQuerySubmitted] = useState<string | null>(null);

  // Document browser filtering
  const filteredDocs = useMemo(() => {
    return docs.filter((doc) => {
      const matchesSearch =
        doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        doc.filename.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesTab = activeTab === "all" || doc.filetype === activeTab;
      return matchesSearch && matchesTab;
    });
  }, [docs, searchQuery, activeTab]);

  const handleUploadSuccess = (item: UploadItem) => {
    const ext = item.sanitized_name.split(".").pop()?.toLowerCase() || "pdf";
    const newDoc: LibraryDoc = {
      id: `doc-${Date.now()}`,
      title: item.sanitized_name.replace(/\.[^/.]+$/, "").replace(/_/g, " "),
      filename: item.sanitized_name,
      filetype: (ext === "epub" || ext === "docx" ? ext : "pdf") as LibraryDoc["filetype"],
      size_bytes: item.size_bytes,
      chapters_count: 1,
      chunks_count: Math.round(item.size_bytes / 8_000) || 120,
      sha256: item.sha256,
      mode: "0o600",
      origin: "upload",
      ingested_at: "Today",
      sample_prompts: [
        `Summarize key principles in ${item.sanitized_name}`,
        "Generate a structured conceptual outline of this document",
        "Extract definitions and key terms",
      ],
    };
    setDocs((prev) => [newDoc, ...prev]);
  };

  const handleOpenAskModal = (doc: LibraryDoc) => {
    setScopedDoc(doc);
    setQueryInput("");
    setQuerySubmitted(null);
  };

  const handleSubmitScopedQuery = (e: any) => {
    e.preventDefault();
    if (!scopedDoc || !queryInput.trim()) return;

    setQuerySubmitted(
      `Scoped query queued: "${queryInput}" targeting ${scopedDoc.filename}. Routed to worker role (qwen3.5:4b) with strict verified citations.`
    );
  };

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 p-4 sm:p-6 lg:p-8 space-y-8 font-sans selection:bg-emerald-500/30 selection:text-emerald-200">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-lg bg-zinc-900 border border-zinc-800 text-emerald-400">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
                />
              </svg>
            </span>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-100">
              Academic Library & Document Index
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-zinc-400">
            Curated textbooks, academic papers, and personal reference materials with verified local provenance.
          </p>
        </div>

        {/* Quick Stats Badges */}
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <span className="px-2.5 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-300">
            Total Docs: <span className="text-emerald-400 font-semibold">{docs.length}</span>
          </span>
          <span className="px-2.5 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-300">
            Indexed Chunks: <span className="text-sky-400 font-semibold">17,490</span>
          </span>
          <span className="px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
            mode 0o600: Protected
          </span>
        </div>
      </div>

      {/* Upload Zone Collapsible Section */}
      <section className="bg-zinc-950/60 border border-zinc-800 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="p-1 rounded bg-zinc-900 text-emerald-400 border border-zinc-800">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </span>
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider font-mono">
              Secure Document Ingestion (SEC-48 / Decision D48)
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setShowUploadZone((prev) => !prev)}
            className="text-xs font-mono text-zinc-400 hover:text-zinc-200 flex items-center gap-1"
          >
            <span>{showUploadZone ? "Hide Upload Zone" : "Show Upload Zone"}</span>
            <svg
              className={`w-3.5 h-3.5 transition-transform ${showUploadZone ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

        {showUploadZone && <UploadZone onUploadSuccess={handleUploadSuccess} />}
      </section>

      {/* Document Browser Section */}
      <section className="space-y-4">
        {/* Filter bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-zinc-900/60 border border-zinc-800/80 p-3 rounded-lg">
          {/* Format Tabs */}
          <div className="flex items-center gap-1.5 font-mono text-xs">
            <button
              onClick={() => setActiveTab("all")}
              className={`px-3 py-1 rounded transition ${
                activeTab === "all"
                  ? "bg-zinc-800 text-zinc-100 font-semibold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              All ({docs.length})
            </button>
            <button
              onClick={() => setActiveTab("pdf")}
              className={`px-3 py-1 rounded transition ${
                activeTab === "pdf"
                  ? "bg-zinc-800 text-zinc-100 font-semibold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              PDFs ({docs.filter((d) => d.filetype === "pdf").length})
            </button>
            <button
              onClick={() => setActiveTab("epub")}
              className={`px-3 py-1 rounded transition ${
                activeTab === "epub"
                  ? "bg-zinc-800 text-zinc-100 font-semibold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              EPUBs ({docs.filter((d) => d.filetype === "epub").length})
            </button>
            <button
              onClick={() => setActiveTab("docx")}
              className={`px-3 py-1 rounded transition ${
                activeTab === "docx"
                  ? "bg-zinc-800 text-zinc-100 font-semibold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Notes / DOCX ({docs.filter((d) => d.filetype === "docx").length})
            </button>
          </div>

          {/* Search box */}
          <div className="relative">
            <input
              type="text"
              placeholder="Search library documents..."
              value={searchQuery}
              onChange={(e: any) => setSearchQuery(e.target.value)}
              className="w-full sm:w-64 px-3 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-700"
            />
          </div>
        </div>

        {/* Document Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredDocs.length === 0 ? (
            <div className="col-span-full py-12 text-center text-zinc-500 font-mono text-xs border border-zinc-800 rounded-xl bg-zinc-950">
              No library documents found matching your filter.
            </div>
          ) : (
            filteredDocs.map((doc) => {
              return (
                <div
                  key={doc.id}
                  className="bg-zinc-950 border border-zinc-800/90 rounded-xl p-4 flex flex-col justify-between hover:border-zinc-700 transition group space-y-4"
                >
                  <div className="space-y-2.5">
                    {/* Header badges */}
                    <div className="flex items-center justify-between text-[11px] font-mono">
                      <span className="uppercase px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 font-semibold">
                        {doc.filetype}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {doc.mode} verified
                      </span>
                    </div>

                    {/* Document title */}
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-100 group-hover:text-emerald-300 transition line-clamp-2">
                        {doc.title}
                      </h3>
                      <p className="text-xs text-zinc-400 font-mono mt-0.5 truncate">
                        {doc.filename}
                      </p>
                    </div>

                    {/* Metadata details */}
                    <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-zinc-400 pt-1 border-t border-zinc-900">
                      <div>Size: <span className="text-zinc-200">{formatBytes(doc.size_bytes)}</span></div>
                      <div>Chunks: <span className="text-zinc-200">{doc.chunks_count.toLocaleString()}</span></div>
                      <div>Chapters: <span className="text-zinc-200">{doc.chapters_count}</span></div>
                      <div>Origin: <span className="text-zinc-200">{doc.origin}</span></div>
                    </div>

                    {/* SHA-256 preview */}
                    <div className="text-[10px] font-mono text-zinc-500 truncate bg-zinc-900/60 px-2 py-1 rounded border border-zinc-800">
                      SHA: <span className="text-zinc-400">{truncateHash(doc.sha256)}</span>
                    </div>
                  </div>

                  {/* "Ask this PDF" Action Trigger */}
                  <div className="pt-2 border-t border-zinc-900">
                    <button
                      type="button"
                      onClick={() => handleOpenAskModal(doc)}
                      className="w-full py-2 px-3 rounded-lg bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 border border-emerald-500/30 hover:border-emerald-500/60 font-medium text-xs transition flex items-center justify-center gap-2 group-hover:shadow-md group-hover:shadow-emerald-950/40"
                    >
                      <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                      <span>Ask this {doc.filetype.toUpperCase()}</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      {/* "Ask this PDF" Scoped Query Modal */}
      {scopedDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-zinc-950 border border-zinc-800 w-full max-w-2xl rounded-xl shadow-2xl p-5 space-y-4 font-sans animate-in zoom-in-95">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-zinc-800 pb-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="p-1 rounded bg-emerald-500/20 text-emerald-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </span>
                  <h3 className="text-sm font-semibold text-zinc-100">
                    Ask Scoped Question: {scopedDoc.title}
                  </h3>
                </div>
                <div className="text-xs text-zinc-400 font-mono">
                  Target Scope: <span className="text-emerald-400 font-medium">@doc:{scopedDoc.filename}</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setScopedDoc(null)}
                className="text-zinc-500 hover:text-zinc-300 p-1"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Scoped query suggestion chips */}
            <div className="space-y-1.5">
              <span className="text-xs text-zinc-400 font-mono">Suggested Questions:</span>
              <div className="flex flex-wrap gap-1.5">
                {scopedDoc.sample_prompts.map((prompt, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setQueryInput(prompt)}
                    className="text-left text-[11px] px-2.5 py-1 rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 text-zinc-300 transition"
                  >
                    "{prompt}"
                  </button>
                ))}
              </div>
            </div>

            {/* Query Form */}
            <form onSubmit={handleSubmitScopedQuery} className="space-y-3">
              <div>
                <textarea
                  rows={3}
                  value={queryInput}
                  onChange={(e: any) => setQueryInput(e.target.value)}
                  placeholder={`Ask anything specific to ${scopedDoc.filename}...`}
                  className="w-full p-3 text-xs bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              {/* Verified-only toggle */}
              <div className="flex items-center justify-between text-xs font-mono">
                <label className="flex items-center gap-2 cursor-pointer text-zinc-300">
                  <input
                    type="checkbox"
                    checked={verifiedOnly}
                    onChange={(e: any) => setVerifiedOnly(e.target.checked)}
                    className="rounded bg-zinc-900 border-zinc-700 text-emerald-500 focus:ring-emerald-500 focus:ring-offset-zinc-950"
                  />
                  <span>Enforce Strict Verified Citations (Dual-Checker Audit)</span>
                </label>
                <span className="text-zinc-500">Worker + Fact Checker pipeline</span>
              </div>

              {/* Feedback Alert if query submitted */}
              {querySubmitted && (
                <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 text-xs font-mono animate-fadeIn flex items-start gap-2">
                  <svg className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <div>{querySubmitted}</div>
                </div>
              )}

              {/* Modal Buttons */}
              <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setScopedDoc(null)}
                  className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-800 hover:bg-zinc-900 rounded transition"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={!queryInput.trim()}
                  className={`px-4 py-1.5 text-xs font-medium rounded transition flex items-center gap-1.5 ${
                    queryInput.trim()
                      ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-950"
                      : "bg-zinc-800 text-zinc-500 cursor-not-allowed border border-zinc-700"
                  }`}
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                  <span>Submit Scoped Query</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
