"use client";

/**
 * QuarantineTable component for isolated document inspection and SEC-56 release.
 * Spec: 02 §5.14, 05 §3, SEC-56, Decision D43.
 */

import React, { useState, useEffect, useCallback } from "react";

export interface QuarantinedDoc {
  id: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  reason: string;
  threat_level: "critical" | "high" | "medium";
  quarantined_at: string;
  mode: string; // "0o400"
  status: "quarantined" | "releasing" | "released" | "deleted";
}

export interface ActionTicketState {
  ticket_id: string;
  action: string;
  doc_id: string;
  filename: string;
  payload_hash: string;
  signature: string;
  created_at: number;
  expires_at: number;
  seconds_left: number;
}

const INITIAL_QUARANTINE_DOCS: QuarantinedDoc[] = [
  {
    id: "q-1082",
    filename: "macroeconomics_leak_2026.pdf",
    sha256: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    size_bytes: 3_452_180,
    reason: "PDF JavaScript execution detected (/JS, /Launch, /OpenAction)",
    threat_level: "critical",
    quarantined_at: "2026-11-08 17:15:22 UTC",
    mode: "0o400",
    status: "quarantined",
  },
  {
    id: "q-1083",
    filename: "prelims_cheatsheet_v2.docx",
    sha256: "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
    size_bytes: 841_200,
    reason: "Prompt injection attempt: role-play jailbreak detected (injection score: 0.99)",
    threat_level: "high",
    quarantined_at: "2026-11-08 18:02:40 UTC",
    mode: "0o400",
    status: "quarantined",
  },
  {
    id: "q-1084",
    filename: "advanced_system_notes.epub",
    sha256: "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    size_bytes: 14_892_100,
    reason: "Disallowed executable polyglot header (MZ / ELF magic bytes detected)",
    threat_level: "critical",
    quarantined_at: "2026-11-08 18:31:05 UTC",
    mode: "0o400",
    status: "quarantined",
  },
  {
    id: "q-1085",
    filename: "syllabus_annexure_b.pdf",
    sha256: "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    size_bytes: 1_210_540,
    reason: "ClamAV heuristic match: Heuristics.Structured.PDF.EmbeddedBinary",
    threat_level: "medium",
    quarantined_at: "2026-11-08 19:10:14 UTC",
    mode: "0o400",
    status: "quarantined",
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

export function QuarantineTable() {
  const [docs, setDocs] = useState<QuarantinedDoc[]>(INITIAL_QUARANTINE_DOCS);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeTicket, setActiveTicket] = useState<ActionTicketState | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [releaseFeedback, setReleaseFeedback] = useState<string | null>(null);

  // 60-second countdown timer for active SEC-56 ticket
  useEffect(() => {
    if (!activeTicket) return;

    const timer = setInterval(() => {
      const now = Math.floor(Date.now() / 1000);
      const remaining = activeTicket.expires_at - now;

      if (remaining <= 0) {
        setActiveTicket((prev) => (prev ? { ...prev, seconds_left: 0 } : null));
      } else {
        setActiveTicket((prev) => (prev ? { ...prev, seconds_left: remaining } : null));
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [activeTicket]);

  const handleCopyHash = useCallback((fullHash: string) => {
    navigator.clipboard?.writeText(fullHash);
    setCopiedHash(fullHash);
    setTimeout(() => setCopiedHash(null), 2000);
  }, []);

  // SEC-56 Ticket Creation: Generates 60s one-time cryptographic action ticket
  const handleRequestTicket = useCallback((doc: QuarantinedDoc) => {
    const now = Math.floor(Date.now() / 1000);
    const ttl = 60; // strictly 60 seconds per SEC-56
    const randomHex = Array.from({ length: 8 }, () =>
      Math.floor(Math.random() * 16).toString(16)
    ).join("");
    const randomSig = Array.from({ length: 16 }, () =>
      Math.floor(Math.random() * 16).toString(16)
    ).join("");

    const ticket: ActionTicketState = {
      ticket_id: `tk_${randomHex}`,
      action: "quarantine.release",
      doc_id: doc.id,
      filename: doc.filename,
      payload_hash: doc.sha256.slice(0, 32),
      signature: `hmac_sha256_${randomSig}`,
      created_at: now,
      expires_at: now + ttl,
      seconds_left: ttl,
    };

    setActiveTicket(ticket);
    setReleaseFeedback(null);
  }, []);

  // SEC-56 Ticket Confirmation: Consumes single-use ticket and releases document
  const handleConfirmRelease = useCallback(() => {
    if (!activeTicket || activeTicket.seconds_left <= 0) return;

    const confirmedDocId = activeTicket.doc_id;
    const ticketId = activeTicket.ticket_id;

    setDocs((prev) =>
      prev.map((d) =>
        d.id === confirmedDocId ? { ...d, status: "released" } : d
      )
    );

    setReleaseFeedback(
      `SEC-56 Ticket ${ticketId} verified & consumed. Document released to Clean Vault (mode 0o600).`
    );
    setActiveTicket(null);

    setTimeout(() => {
      setReleaseFeedback(null);
    }, 8000);
  }, [activeTicket]);

  const handleDelete = useCallback((docId: string) => {
    setDocs((prev) => prev.filter((d) => d.id !== docId));
  }, []);

  const filteredDocs = docs.filter(
    (d) =>
      d.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.reason.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.sha256.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="w-full space-y-4">
      {/* Search and summary header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-zinc-900/60 border border-zinc-800/80 p-3.5 rounded-lg">
        <div className="flex items-center gap-2">
          <svg
            className="w-4 h-4 text-rose-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <span className="text-sm font-medium text-zinc-200">
            Isolated Quarantine Repository ({filteredDocs.length} items)
          </span>
          <span className="px-2 py-0.5 text-xs font-mono rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">
            0o400 Read-Only
          </span>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search by file, reason, or hash..."
            value={searchTerm}
            onChange={(e: any) => setSearchTerm(e.target.value)}
            className="px-3 py-1.5 text-xs bg-zinc-950 border border-zinc-800 rounded text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-700 w-64"
          />
        </div>
      </div>

      {/* Release feedback banner */}
      {releaseFeedback && (
        <div className="flex items-center gap-2 px-3 py-2 bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 rounded text-xs font-mono animate-fadeIn">
          <svg className="w-4 h-4 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span>{releaseFeedback}</span>
        </div>
      )}

      {/* Quarantine Table */}
      <div className="overflow-x-auto border border-zinc-800 rounded-lg bg-zinc-950">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/50 text-zinc-400 font-mono text-[11px] uppercase tracking-wider">
              <th className="py-2.5 px-3">File Name</th>
              <th className="py-2.5 px-3">SHA-256 Digest</th>
              <th className="py-2.5 px-3">Quarantine Reason</th>
              <th className="py-2.5 px-3">Threat</th>
              <th className="py-2.5 px-3">Isolated At</th>
              <th className="py-2.5 px-3 text-right">SEC-56 Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 font-sans">
            {filteredDocs.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-zinc-500 font-mono text-xs">
                  No quarantined documents matching filter.
                </td>
              </tr>
            ) : (
              filteredDocs.map((doc) => {
                const isReleased = doc.status === "released";
                return (
                  <tr
                    key={doc.id}
                    className={`hover:bg-zinc-900/30 transition-colors ${
                      isReleased ? "opacity-40 bg-zinc-900/20" : ""
                    }`}
                  >
                    {/* Filename & size */}
                    <td className="py-2.5 px-3 font-mono">
                      <div className="flex items-center gap-2">
                        <span className="text-zinc-200 font-medium">{doc.filename}</span>
                        <span className="text-[10px] text-zinc-500 font-mono">
                          ({formatBytes(doc.size_bytes)})
                        </span>
                      </div>
                      <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                        mode: <span className="text-amber-400/80">{doc.mode}</span> | ID: {doc.id}
                      </div>
                    </td>

                    {/* SHA-256 preview with copy */}
                    <td className="py-2.5 px-3 font-mono">
                      <div className="flex items-center gap-1.5">
                        <span className="text-zinc-400 bg-zinc-900 px-1.5 py-0.5 rounded border border-zinc-800 text-[11px]">
                          {truncateHash(doc.sha256)}
                        </span>
                        <button
                          onClick={() => handleCopyHash(doc.sha256)}
                          title="Copy full SHA-256 hash"
                          className="text-zinc-500 hover:text-zinc-300 p-1 rounded hover:bg-zinc-800 transition"
                        >
                          {copiedHash === doc.sha256 ? (
                            <span className="text-[10px] text-emerald-400">Copied!</span>
                          ) : (
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"
                              />
                            </svg>
                          )}
                        </button>
                      </div>
                    </td>

                    {/* Quarantine reason */}
                    <td className="py-2.5 px-3 max-w-xs">
                      <p className="text-zinc-300 text-xs line-clamp-2 leading-relaxed">
                        {doc.reason}
                      </p>
                    </td>

                    {/* Threat level badge */}
                    <td className="py-2.5 px-3">
                      {doc.threat_level === "critical" && (
                        <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-rose-500/10 text-rose-400 border border-rose-500/30">
                          CRITICAL
                        </span>
                      )}
                      {doc.threat_level === "high" && (
                        <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                          HIGH
                        </span>
                      )}
                      {doc.threat_level === "medium" && (
                        <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                          MEDIUM
                        </span>
                      )}
                    </td>

                    {/* Quarantined at */}
                    <td className="py-2.5 px-3 font-mono text-[11px] text-zinc-400 whitespace-nowrap">
                      {doc.quarantined_at}
                    </td>

                    {/* Actions */}
                    <td className="py-2.5 px-3 text-right">
                      {isReleased ? (
                        <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/30 px-2 py-1 rounded border border-emerald-500/20">
                          Released (Clean)
                        </span>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleRequestTicket(doc)}
                            className="px-2.5 py-1 text-xs font-medium rounded bg-rose-950/40 hover:bg-rose-900/50 text-rose-300 border border-rose-800/60 hover:border-rose-600 transition flex items-center gap-1.5"
                          >
                            <svg className="w-3.5 h-3.5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                            </svg>
                            <span>Release (Requires 60s Ticket)</span>
                          </button>
                          <button
                            onClick={() => handleDelete(doc.id)}
                            title="Delete file permanently"
                            className="p-1 text-zinc-500 hover:text-zinc-300 rounded hover:bg-zinc-900"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* SEC-56 One-Time Action Ticket Confirmation Modal */}
      {activeTicket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-zinc-950 border border-zinc-800 w-full max-w-lg rounded-xl shadow-2xl p-5 space-y-4 font-sans animate-in zoom-in-95">
            {/* Modal header */}
            <div className="flex items-start justify-between border-b border-zinc-800 pb-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="p-1 rounded bg-rose-500/20 text-rose-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                  </span>
                  <h3 className="text-sm font-semibold text-zinc-100">
                    SEC-56 One-Time Action Ticket Confirmation
                  </h3>
                </div>
                <p className="text-xs text-zinc-400">
                  Release Quarantine Document: <span className="text-zinc-200 font-mono">{activeTicket.filename}</span>
                </p>
              </div>
              <button
                onClick={() => setActiveTicket(null)}
                className="text-zinc-500 hover:text-zinc-300 p-1"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Countdown timer badge */}
            <div
              className={`p-3 rounded-lg border flex items-center justify-between transition-colors ${
                activeTicket.seconds_left > 20
                  ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                  : activeTicket.seconds_left > 0
                  ? "bg-amber-950/20 border-amber-500/30 text-amber-300"
                  : "bg-rose-950/30 border-rose-500/40 text-rose-300"
              }`}
            >
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 animate-spin text-current" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                <span className="text-xs font-mono font-medium">
                  {activeTicket.seconds_left > 0
                    ? `Ticket Valid for: ${activeTicket.seconds_left}s (Expires at T+60s)`
                    : "Ticket Expired (> 60s window elapsed)"}
                </span>
              </div>
              <span className="font-mono text-sm font-bold">
                00:{String(activeTicket.seconds_left).padStart(2, "0")}
              </span>
            </div>

            {/* Cryptographic ticket details */}
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 space-y-2 text-xs font-mono">
              <div className="flex justify-between items-center text-zinc-400">
                <span>Action:</span>
                <span className="text-rose-400 font-semibold">{activeTicket.action}</span>
              </div>
              <div className="flex justify-between items-center text-zinc-400">
                <span>Ticket ID:</span>
                <span className="text-zinc-200">{activeTicket.ticket_id}</span>
              </div>
              <div className="flex justify-between items-center text-zinc-400">
                <span>Payload SHA-256:</span>
                <span className="text-zinc-300">{activeTicket.payload_hash}...</span>
              </div>
              <div className="flex justify-between items-center text-zinc-400">
                <span>HMAC Signature:</span>
                <span className="text-emerald-400">{activeTicket.signature}</span>
              </div>
              <div className="pt-2 border-t border-zinc-800/80 text-[11px] text-zinc-500 font-sans">
                Notice: SEC-56 enforces single-use replay protection and 60-second automatic revocation.
                Consuming this ticket transitions the file to Clean Vault storage with mode 0o600.
              </div>
            </div>

            {/* Modal actions */}
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setActiveTicket(null)}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-800 hover:bg-zinc-900 rounded transition"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={activeTicket.seconds_left <= 0}
                onClick={handleConfirmRelease}
                className={`px-4 py-1.5 text-xs font-medium rounded transition flex items-center gap-1.5 ${
                  activeTicket.seconds_left > 0
                    ? "bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-950"
                    : "bg-zinc-800 text-zinc-500 cursor-not-allowed border border-zinc-700"
                }`}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span>
                  {activeTicket.seconds_left > 0
                    ? "Confirm Release (Execute Ticket)"
                    : "Ticket Expired — Regenerate"}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default QuarantineTable;
