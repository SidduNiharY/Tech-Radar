"use client";

/**
 * UploadZone component for secure library document intake.
 * Supports drag-and-drop (PDF, DOCX, EPUB up to 300MB), mode 0o600 badge,
 * and SEC-48 path traversal sanitization indicator.
 * Spec: 02 §5.14, 05 §3, SEC-48, SEC-57, Decision D48.
 */

import React, { useState, useRef, useCallback } from "react";

export const MAX_UPLOAD_BYTES = 300 * 1024 * 1024; // 300 MB limit
export const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".epub", ".mp4", ".mp3", ".txt"];

export interface UploadItem {
  id: string;
  original_name: string;
  sanitized_name: string;
  size_bytes: number;
  sha256: string;
  mode: string; // "0o600"
  status: "validating" | "uploading" | "scanned" | "quarantined" | "error";
  progress: number;
  stage_message: string;
  uploaded_at: string;
  error?: string;
}

interface UploadZoneProps {
  onUploadSuccess?: (item: UploadItem) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Client-side path traversal sanitizer matching SEC-48 and Decision D48.
 * Defangs `../../` sequences, null bytes, and converts path separators.
 */
function sanitizeFilenameClient(rawName: string): { sanitized: string; hadTraversal: boolean } {
  const hadTraversal = rawName.includes("..") || rawName.includes("/") || rawName.includes("\\") || rawName.includes("\x00");
  
  // Strip null bytes and non-printable characters
  let clean = rawName.replace(/[\x00-\x1f\x7f]/g, "");
  // Normalize slashes
  clean = clean.replace(/\\/g, "/");
  
  // Extract parts and filter dots
  const parts = clean.split("/").map(p => p.trim()).filter(p => p && !p.split("").every(c => c === "."));
  const basename = parts.length > 0 ? parts.join("_") : "upload.pdf";
  
  return {
    sanitized: basename.replace(/^\.+/, ""),
    hadTraversal,
  };
}

export function UploadZone({ onUploadSuccess }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [recentUploads, setRecentUploads] = useState<UploadItem[]>([
    {
      id: "upl-init-1",
      original_name: "Indian_Economy_15th_Ed.pdf",
      sanitized_name: "Indian_Economy_15th_Ed.pdf",
      size_bytes: 42_120_800,
      sha256: "b45a72df81c496c...91ec23",
      mode: "0o600",
      status: "scanned",
      progress: 100,
      stage_message: "Passed Intake Gateway (Mode 0o600)",
      uploaded_at: "Today, 18:20",
    },
    {
      id: "upl-init-2",
      original_name: "Modern_Operating_Systems_Ch4.epub",
      sanitized_name: "Modern_Operating_Systems_Ch4.epub",
      size_bytes: 18_450_200,
      sha256: "17ac981fbb4e11...33d02a",
      mode: "0o600",
      status: "scanned",
      progress: 100,
      stage_message: "Passed Intake Gateway (Mode 0o600)",
      uploaded_at: "Today, 17:45",
    },
  ]);

  const [activeUpload, setActiveUpload] = useState<UploadItem | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [traversalAlert, setTraversalAlert] = useState<string | null>(null);
  const fileInputRef = useRef<any>(null);

  const processFile = useCallback(
    (file: File) => {
      setErrorMessage(null);
      setTraversalAlert(null);

      // Check file size constraint (300 MB)
      if (file.size > MAX_UPLOAD_BYTES) {
        setErrorMessage(
          `Payload rejected: Size (${formatBytes(file.size)}) exceeds maximum limit of 300MB (Decision D37 / D48).`
        );
        return;
      }

      // Check allowed extensions
      const ext = "." + file.name.split(".").pop()?.toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        setErrorMessage(
          `Disallowed file type (${ext}). Only PDF, DOCX, EPUB, MP4, MP3, TXT are permitted.`
        );
        return;
      }

      // SEC-48 Path Traversal Sanitization
      const { sanitized, hadTraversal } = sanitizeFilenameClient(file.name);
      if (hadTraversal) {
        setTraversalAlert(
          `SEC-48: Path traversal detected in raw name "${file.name}". Sanitized to "${sanitized}".`
        );
      }

      const uploadId = `upl_${Date.now()}`;
      const randomSha = Array.from({ length: 64 }, () =>
        Math.floor(Math.random() * 16).toString(16)
      ).join("");

      const newUpload: UploadItem = {
        id: uploadId,
        original_name: file.name,
        sanitized_name: sanitized,
        size_bytes: file.size,
        sha256: randomSha,
        mode: "0o600",
        status: "validating",
        progress: 10,
        stage_message: "Sanitizing path and computing SHA-256...",
        uploaded_at: "Just now",
      };

      setActiveUpload(newUpload);

      // Simulate multi-stage secure pipeline upload
      setTimeout(() => {
        setActiveUpload((prev) =>
          prev ? { ...prev, status: "uploading", progress: 45, stage_message: "Streaming upload with mode 0o600..." } : null
        );
      }, 500);

      setTimeout(() => {
        setActiveUpload((prev) =>
          prev ? { ...prev, status: "uploading", progress: 80, stage_message: "Intake Gateway: Running Antivirus & Prompt-Injection Check..." } : null
        );
      }, 1200);

      setTimeout(() => {
        const completed: UploadItem = {
          ...newUpload,
          status: "scanned",
          progress: 100,
          stage_message: "Passed Intake Gateway (Mode 0o600 saved)",
        };
        setActiveUpload(null);
        setRecentUploads((prev) => [completed, ...prev]);
        if (onUploadSuccess) {
          onUploadSuccess(completed);
        }
      }, 2000);
    },
    [onUploadSuccess]
  );

  const handleDragOver = (e: any) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: any) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: any) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  return (
    <div className="w-full space-y-4">
      {/* Dropzone Container */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-xl p-6 sm:p-8 text-center cursor-pointer transition-all duration-200 ${
          isDragging
            ? "border-emerald-500 bg-emerald-950/20 shadow-lg shadow-emerald-950/40"
            : "border-zinc-800 hover:border-zinc-700 bg-zinc-950/80 hover:bg-zinc-900/40"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.epub,.mp4,.mp3,.txt"
          onChange={handleFileInputChange}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center space-y-3">
          <div className="p-3 rounded-full bg-zinc-900 border border-zinc-800 text-emerald-400">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-zinc-100">
              Drag and drop documents, or <span className="text-emerald-400 underline">browse files</span>
            </h4>
            <p className="text-xs text-zinc-400 mt-1">
              Supported formats: PDF, DOCX, EPUB, MP4, MP3, TXT (Maximum size: 300 MB)
            </p>
          </div>

          {/* Security Badges Row */}
          <div className="flex flex-wrap items-center justify-center gap-2 pt-1 font-mono text-[11px]">
            <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span>mode: 0o600 Owner-Only</span>
            </span>
            <span className="px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30">
              SEC-48: Path Traversal Defanged
            </span>
            <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
              SEC-57: Max 300MB
            </span>
          </div>
        </div>
      </div>

      {/* Path Traversal Defanging Alert */}
      {traversalAlert && (
        <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-start gap-2 animate-fadeIn">
          <svg className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <span className="font-semibold">Path Traversal Neutralized:</span> {traversalAlert}
          </div>
        </div>
      )}

      {/* Error Message */}
      {errorMessage && (
        <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-start gap-2 animate-fadeIn">
          <svg className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <span className="font-semibold">Upload Rejected:</span> {errorMessage}
          </div>
        </div>
      )}

      {/* Active Upload Progress Card */}
      {activeUpload && (
        <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-3 font-mono animate-fadeIn">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-emerald-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              <span className="font-semibold text-zinc-100">{activeUpload.sanitized_name}</span>
              <span className="text-zinc-500">({formatBytes(activeUpload.size_bytes)})</span>
            </div>
            <span className="text-emerald-400 font-semibold">{activeUpload.progress}%</span>
          </div>

          {/* Progress bar */}
          <div className="h-2 w-full bg-zinc-900 rounded-full overflow-hidden border border-zinc-800">
            <div
              style={{ width: `${activeUpload.progress}%` }}
              className="h-full bg-emerald-500 transition-all duration-300"
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-zinc-400">
            <span>{activeUpload.stage_message}</span>
            <span className="text-zinc-500">mode 0o600</span>
          </div>
        </div>
      )}

      {/* Recent Uploads Feed */}
      <div className="space-y-2">
        <div className="text-xs font-mono uppercase tracking-wider text-zinc-400">
          Recent Intake Uploads
        </div>

        <div className="border border-zinc-800/80 rounded-lg overflow-hidden bg-zinc-950">
          <div className="divide-y divide-zinc-800/60 font-sans text-xs">
            {recentUploads.map((item) => (
              <div key={item.id} className="p-3 flex items-center justify-between gap-3 hover:bg-zinc-900/30 transition">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded bg-zinc-900 text-zinc-400 border border-zinc-800">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div>
                    <div className="font-mono text-zinc-200 font-medium">{item.sanitized_name}</div>
                    <div className="text-[11px] text-zinc-500 font-mono mt-0.5 flex items-center gap-2">
                      <span>{formatBytes(item.size_bytes)}</span>
                      <span>•</span>
                      <span>mode: <span className="text-emerald-400">{item.mode}</span></span>
                      <span>•</span>
                      <span>{item.uploaded_at}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 font-mono text-[11px]">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span>Intake Passed</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default UploadZone;
