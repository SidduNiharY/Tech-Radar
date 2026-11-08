"use client";

import React, { useState } from "react";
import { Orb, OrbState } from "../../components/orb";
import { ListeningLight, ListeningState } from "../../components/jarvis/listening-light";
import { WakeToggle } from "../../components/jarvis/wake-toggle";
import { MuteSwitch } from "../../components/jarvis/mute-switch";
import { ShieldCheck, Sparkles, Terminal, Volume2 } from "lucide-react";

interface VoiceTurn {
  id: string;
  role: "user" | "jarvis";
  text: string;
  timestamp: string;
  skillMatched?: string;
}

export default function JarvisVoicePage() {
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [listeningState, setListeningState] = useState<ListeningState>("off");
  const [wakeWordEnabled, setWakeWordEnabled] = useState(false);
  const [isMuted, setIsMuted] = useState(false);

  const [turns, setTurns] = useState<VoiceTurn[]>([
    {
      id: "1",
      role: "user",
      text: "Jarvis, how is my GATE DA syllabus pacing for linear algebra?",
      timestamp: "10:14 AM",
      skillMatched: "exams.syllabus_coverage",
    },
    {
      id: "2",
      role: "jarvis",
      text: "You have completed 4 of 6 topics in linear algebra. Eigenvalues and SVD are scheduled for revision tomorrow morning.",
      timestamp: "10:14 AM",
      skillMatched: "exams.syllabus_coverage",
    },
  ]);

  const [activeTicket, setActiveTicket] = useState<{
    id: string;
    action: string;
    secondsLeft: number;
  } | null>(null);

  const handleOrbClick = () => {
    if (isMuted) return;
    if (orbState === "idle") {
      setOrbState("listening");
      setListeningState("stream");
    } else if (orbState === "listening") {
      setOrbState("thinking");
      setTimeout(() => {
        setOrbState("speaking");
        setTimeout(() => {
          setOrbState("idle");
          setListeningState(wakeWordEnabled ? "wake" : "off");
        }, 3000);
      }, 1500);
    }
  };

  const handleWakeToggle = (enabled: boolean) => {
    setWakeWordEnabled(enabled);
    if (enabled && !isMuted) {
      setListeningState("wake");
    } else if (!enabled && orbState === "idle") {
      setListeningState("off");
    }
  };

  const handleMuteToggle = () => {
    const nextMuted = !isMuted;
    setIsMuted(nextMuted);
    if (nextMuted) {
      setListeningState("off");
      setOrbState("idle");
    } else {
      setListeningState(wakeWordEnabled ? "wake" : "off");
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-16">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white font-mono">
              Jarvis Live Voice
            </h1>
            <ListeningLight state={listeningState} />
          </div>
          <p className="text-sm text-zinc-400 mt-1">
            System-wide voice intelligence powered by Qwen3.5-4B and on-device wake detection.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <MuteSwitch isMuted={isMuted} onToggleMute={handleMuteToggle} />
        </div>
      </div>

      {/* Main Orb Centerpiece */}
      <div className="flex flex-col items-center justify-center p-12 rounded-2xl border border-zinc-800 bg-zinc-950/80 relative overflow-hidden backdrop-blur-xl">
        <div className="absolute inset-0 bg-radial-gradient pointer-events-none opacity-20" />
        
        <Orb state={orbState} onClick={handleOrbClick} />

        <div className="mt-8 text-center space-y-1">
          <span className="text-xs uppercase tracking-widest text-zinc-500 font-mono">
            Status: {orbState}
          </span>
          <p className="text-sm text-zinc-300">
            {orbState === "idle" && (wakeWordEnabled ? 'Say "Hey Jarvis" or tap the orb' : "Tap the orb to speak")}
            {orbState === "listening" && "Listening to your voice..."}
            {orbState === "thinking" && "Routing conversational intent..."}
            {orbState === "speaking" && "Synthesizing spoken response via Kokoro..."}
          </p>
        </div>
      </div>

      {/* Controls & Mode Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <WakeToggle enabled={wakeWordEnabled} onToggle={handleWakeToggle} />

        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/60 backdrop-blur-sm flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Volume2 className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-medium text-zinc-100">Audio Pipeline</div>
              <p className="text-xs text-zinc-400">SmallWebRTC + Kokoro TTS (80ms TTFT)</p>
            </div>
          </div>
          <span className="text-[10px] font-mono px-2 py-1 rounded bg-zinc-800 text-emerald-400 border border-zinc-700">
            Loopback 127.0.0.1
          </span>
        </div>
      </div>

      {/* 10s Confirmation Ticket Banner (SEC-56) */}
      {activeTicket && (
        <div className="p-4 rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-amber-400" />
            <div>
              <div className="font-semibold text-sm">Spoken Confirmation Ticket Pending</div>
              <p className="text-xs text-amber-300/80">
                Action: <span className="font-mono text-white">{activeTicket.action}</span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-lg font-bold text-amber-400">
              {activeTicket.secondsLeft}s
            </span>
            <button
              type="button"
              onClick={() => setActiveTicket(null)}
              className="px-3 py-1 bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded text-xs"
            >
              Confirm ("Yes")
            </button>
          </div>
        </div>
      )}

      {/* Recent Conversational Transcript */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
            <Terminal className="w-4 h-4 text-emerald-400" />
            <span>Voice Transcript & Intent Routing</span>
          </div>
          <span className="text-xs text-zinc-500 font-mono">Qwen3.5-4B</span>
        </div>

        <div className="space-y-3">
          {turns.map((turn) => (
            <div
              key={turn.id}
              className={`p-3.5 rounded-lg text-sm border ${
                turn.role === "user"
                  ? "bg-zinc-800/40 border-zinc-700/60 ml-8"
                  : "bg-emerald-950/20 border-emerald-500/20 mr-8"
              }`}
            >
              <div className="flex items-center justify-between text-[11px] text-zinc-400 mb-1">
                <span className="font-semibold text-zinc-300 capitalize">{turn.role}</span>
                <span className="font-mono">{turn.timestamp}</span>
              </div>
              <p className="text-zinc-200">{turn.text}</p>
              {turn.skillMatched && (
                <div className="mt-2 text-[10px] font-mono text-emerald-400/80 flex items-center gap-1">
                  <Sparkles className="w-3 h-3" />
                  <span>Routed Skill: {turn.skillMatched}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
