"use client";

import React, { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

interface WakeToggleProps {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

const STORAGE_KEY = "tr_wakeword_enabled";

export function WakeToggle({ enabled, onToggle }: WakeToggleProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored !== null) {
        onToggle(stored === "true");
      }
    } catch {
      // localStorage may be disabled or sandboxed
    }
  }, [onToggle]);

  const handleToggle = (val: boolean) => {
    onToggle(val);
    try {
      localStorage.setItem(STORAGE_KEY, String(val));
    } catch {
      // Ignore sandboxed write failures
    }
  };

  if (!mounted) {
    return null;
  }

  return (
    <div className="flex items-center justify-between p-3.5 rounded-xl border border-zinc-800 bg-zinc-900/60 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
          <Sparkles className="w-4 h-4" />
        </div>
        <div>
          <div className="text-sm font-medium text-zinc-100 flex items-center gap-2">
            <span>Wake Word ("Hey Jarvis")</span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
              Local ONNX
            </span>
          </div>
          <p className="text-xs text-zinc-400">
            Continuously scan for activation phrase on-device without network streaming.
          </p>
        </div>
      </div>

      <label className="relative inline-flex items-center cursor-pointer">
        <input
          type="checkbox"
          role="switch"
          aria-label="Wake word"
          checked={enabled}
          onChange={(e) => handleToggle(e.target.checked)}
          className="sr-only peer"
        />
        <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-zinc-300 after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
      </label>
    </div>
  );
}
