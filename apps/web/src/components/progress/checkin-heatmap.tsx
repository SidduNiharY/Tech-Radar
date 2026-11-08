"use client";

import React from "react";
import { Flame } from "lucide-react";

export function CheckinHeatmap() {
  // 28 days of streak & energy data (4 weeks x 7 days)
  const days = Array.from({ length: 28 }, (_, i) => {
    // Generate simulated energy bands 1..5
    const levels = [4, 5, 3, 4, 5, 2, 4, 3, 5, 4, 5, 4, 3, 5, 4, 5, 3, 4, 5, 2, 4, 5, 4, 5, 3, 4, 5, 5];
    return {
      day: i + 1,
      level: levels[i % levels.length],
    };
  });

  const getCellColor = (level: number) => {
    switch (level) {
      case 5:
        return "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)]";
      case 4:
        return "bg-emerald-600/80";
      case 3:
        return "bg-emerald-700/60";
      case 2:
        return "bg-amber-600/60";
      default:
        return "bg-zinc-800";
    }
  };

  return (
    <div className="p-5 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-4">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
          <Flame className="w-4 h-4 text-emerald-400" />
          <span>28-Day Consistency & Energy Heatmap</span>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-emerald-400">
          <span>Active Streak: 28 Days 🔥</span>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-2 pt-2">
        {days.map((item) => (
          <div
            key={item.day}
            className={`aspect-square rounded-md ${getCellColor(
              item.level
            )} flex items-center justify-center text-[10px] font-mono text-black/70 font-semibold transition-transform hover:scale-110 cursor-default`}
            title={`Day ${item.day}: Energy Band ${item.level}`}
          >
            {item.day}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-end gap-2 text-[10px] text-zinc-400 font-mono pt-1">
        <span>Low Energy</span>
        <span className="w-2.5 h-2.5 rounded-sm bg-zinc-800" />
        <span className="w-2.5 h-2.5 rounded-sm bg-amber-600/60" />
        <span className="w-2.5 h-2.5 rounded-sm bg-emerald-700/60" />
        <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" />
        <span>Peak State</span>
      </div>
    </div>
  );
}
