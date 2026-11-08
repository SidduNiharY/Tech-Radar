"use client";

import React from "react";
import { Mic, Radio, ShieldAlert } from "lucide-react";

export type ListeningState = "wake" | "stream" | "off";

interface ListeningLightProps {
  state: ListeningState;
}

export function ListeningLight({ state }: ListeningLightProps) {
  const configs = {
    wake: {
      label: "Device Listening (Offline)",
      color: "text-amber-400 border-amber-500/40 bg-amber-500/10",
      dot: "bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(251,191,36,0.6)]",
      icon: Mic,
      description: "Audio evaluated locally in WebAssembly. No network data transmitted.",
    },
    stream: {
      label: "Live Streaming (Server)",
      color: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
      dot: "bg-emerald-400 animate-ping shadow-[0_0_12px_rgba(16,185,129,0.8)]",
      icon: Radio,
      description: "Authenticated WebRTC voice pipeline active over local loopback.",
    },
    off: {
      label: "Microphone Inactive",
      color: "text-zinc-500 border-zinc-800 bg-zinc-900/40",
      dot: "bg-zinc-600",
      icon: ShieldAlert,
      description: "Microphone tracks destroyed. Listening halted.",
    },
  };

  const current = configs[state];
  const Icon = current.icon;

  return (
    <div
      data-listening={state}
      className={`inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full border text-xs font-mono transition-all ${current.color}`}
    >
      <span className={`w-2 h-2 rounded-full ${current.dot}`} />
      <Icon className="w-3.5 h-3.5" />
      <span className="font-medium">{current.label}</span>
    </div>
  );
}
