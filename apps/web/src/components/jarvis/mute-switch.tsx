"use client";

import React from "react";
import { Mic, MicOff } from "lucide-react";

interface MuteSwitchProps {
  isMuted: boolean;
  onToggleMute: () => void;
}

export function MuteSwitch({ isMuted, onToggleMute }: MuteSwitchProps) {
  return (
    <button
      type="button"
      onClick={onToggleMute}
      aria-label={isMuted ? "Unmute" : "Mute"}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-mono font-medium border transition-all ${
        isMuted
          ? "border-rose-500/40 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20"
          : "border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:border-zinc-700 hover:text-white"
      }`}
    >
      {isMuted ? <MicOff className="w-4 h-4 text-rose-400" /> : <Mic className="w-4 h-4 text-zinc-400" />}
      <span>{isMuted ? "Muted (Tracks Stopped)" : "Hardware Mic Active"}</span>
    </button>
  );
}
