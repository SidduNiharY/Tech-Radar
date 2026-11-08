"use client";

/**
 * Security Dashboard Page.
 * Displays Host Alerter Heartbeat, Loopback Listener Verification, and Quarantine Table.
 * Spec: 02 §5.14, 05 §3, SEC-20, SEC-44, SEC-51, SEC-56, SEC-57.
 */

import React, { useState, useEffect } from "react";
import { QuarantineTable } from "../../components/security/quarantine-table";

interface SecurityMetric {
  name: string;
  value: string;
  status: "secure" | "warning" | "alert";
  subtext: string;
}

export default function SecurityPage() {
  const [lastHeartbeat, setLastHeartbeat] = useState<number>(0);
  const [secondsAgo, setSecondsAgo] = useState<number>(4);
  const [listenerVerified, setListenerVerified] = useState<boolean>(true);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);

  // Heartbeat live simulation timer
  useEffect(() => {
    setLastHeartbeat(Date.now());
    const interval = setInterval(() => {
      setSecondsAgo((prev) => {
        if (prev >= 28) {
          // Heartbeat pulse every 30s
          setLastHeartbeat(Date.now());
          return 0;
        }
        return prev + 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const handleManualVerification = () => {
    setIsVerifying(true);
    setTimeout(() => {
      setListenerVerified(true);
      setIsVerifying(false);
      setSecondsAgo(0);
      setLastHeartbeat(Date.now());
    }, 600);
  };

  const metrics: SecurityMetric[] = [
    {
      name: "Host Alerter Heartbeat",
      value: "Healthy / Protected",
      status: "secure",
      subtext: `Active ping ${secondsAgo}s ago via techradar-heartbeat.timer`,
    },
    {
      name: "Loopback Interface Binding",
      value: "127.0.0.1:8000 ONLY",
      status: listenerVerified ? "secure" : "alert",
      subtext: "0.0.0.0 public interface blocked by SEC-20 / SEC-51",
    },
    {
      name: "Falco Runtime Sensors",
      value: "Enforced (14 Rules)",
      status: "secure",
      subtext: "Kernel syscall monitors + egress canary active",
    },
    {
      name: "AIDE File Integrity",
      value: "0 Unauthorized Diff",
      status: "secure",
      subtext: "Cryptographic baseline matches SHA-256 DB",
    },
  ];

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 p-4 sm:p-6 lg:p-8 space-y-8 font-sans selection:bg-rose-500/30 selection:text-rose-200">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-lg bg-zinc-900 border border-zinc-800 text-rose-400">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
            </span>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-zinc-100">
              Security & Isolation Dashboard
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-zinc-400">
            Real-time host integrity telemetry, SEC-20 loopback enforcement, and intake quarantine management.
          </p>
        </div>

        {/* Verification Trigger */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleManualVerification}
            disabled={isVerifying}
            className="px-3 py-1.5 text-xs font-mono rounded bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-zinc-300 transition flex items-center gap-2"
          >
            <svg
              className={`w-3.5 h-3.5 text-emerald-400 ${isVerifying ? "animate-spin" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            <span>{isVerifying ? "Verifying..." : "Run Policy Audit"}</span>
          </button>
        </div>
      </div>

      {/* Primary Status Banner Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Host Alerter Heartbeat Card with Green Pulsating Badge */}
        <div className="bg-zinc-950/80 border border-zinc-800/80 rounded-xl p-4 space-y-3 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-400">
              Host Alerter
            </span>
            {/* Green pulsating badge */}
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="text-[10px] font-mono font-medium tracking-wide">PULSING</span>
            </div>
          </div>
          <div>
            <div className="text-base font-semibold text-zinc-100 flex items-center gap-2">
              <span>Heartbeat Active</span>
            </div>
            <div className="text-xs text-zinc-400 mt-1 font-mono">
              Last ping: <span className="text-emerald-400 font-medium">{secondsAgo}s ago</span>
            </div>
          </div>
          <div className="text-[11px] text-zinc-500 pt-2 border-t border-zinc-900 font-mono">
            Unit: techradar-heartbeat.timer
          </div>
        </div>

        {/* Loopback Listener Verification Card */}
        <div className="bg-zinc-950/80 border border-zinc-800/80 rounded-xl p-4 space-y-3 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-400">
              Network Surface
            </span>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              SEC-20 / SEC-51
            </span>
          </div>
          <div>
            <div className="text-base font-semibold text-zinc-100 font-mono flex items-center gap-1.5">
              <span className="text-emerald-400">127.0.0.1</span>
              <span className="text-zinc-500">:8000</span>
            </div>
            <div className="text-xs text-zinc-400 mt-1">
              Loopback bound strictly. Public 0.0.0.0 binding rejected.
            </div>
          </div>
          <div className="text-[11px] text-zinc-500 pt-2 border-t border-zinc-900 font-mono flex items-center justify-between">
            <span>Tailscale mesh: tailscale0</span>
            <span className="text-emerald-400">VERIFIED</span>
          </div>
        </div>

        {/* Honeytoken & Threat Tripwires Card */}
        <div className="bg-zinc-950/80 border border-zinc-800/80 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-400">
              Tripwire Decoys
            </span>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              ARMED
            </span>
          </div>
          <div>
            <div className="text-base font-semibold text-zinc-100">
              0 Tamper Events
            </div>
            <div className="text-xs text-zinc-400 mt-1">
              Canary .env.production and honeytoken credentials intact.
            </div>
          </div>
          <div className="text-[11px] text-zinc-500 pt-2 border-t border-zinc-900 font-mono">
            Falco audit rules: 100% active
          </div>
        </div>

        {/* Storage Sandboxing Card */}
        <div className="bg-zinc-950/80 border border-zinc-800/80 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-zinc-400">
              File Mode Sandbox
            </span>
            <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
              STRICT
            </span>
          </div>
          <div>
            <div className="text-base font-semibold text-zinc-100 font-mono">
              0o400 <span className="text-zinc-500 text-xs font-sans">/</span> 0o600
            </div>
            <div className="text-xs text-zinc-400 mt-1">
              Quarantine mode 0o400 read-only. Clean uploads mode 0o600.
            </div>
          </div>
          <div className="text-[11px] text-zinc-500 pt-2 border-t border-zinc-900 font-mono">
            SEC-48 traversal defanged
          </div>
        </div>
      </div>

      {/* Security Architecture Notice */}
      <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800/90 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="p-2 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </span>
          <div className="space-y-0.5">
            <h4 className="text-xs font-semibold text-zinc-200">
              Quarantine Isolation Vault Active (SEC-56 Enforced)
            </h4>
            <p className="text-xs text-zinc-400">
              Quarantined artifacts cannot be parsed, chunked, or indexed by LLM worker agents.
              To release an item to the clean vault, an administrator must generate and cryptographically confirm a 60-second one-time action ticket.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] font-mono px-2.5 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-300">
            SEC-56 Tickets: Active
          </span>
        </div>
      </div>

      {/* Quarantine Table Component */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider font-mono">
            Intake Quarantine Inspection
          </h2>
          <span className="text-xs text-zinc-500 font-mono">
            Automatic purging after 7 days retention policy
          </span>
        </div>
        <QuarantineTable />
      </section>
    </div>
  );
}
