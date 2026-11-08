"use client";

import React from "react";
import { TrendingUp } from "lucide-react";

interface AccuracyPoint {
  day: string;
  accuracy: number; // 0 to 100
  sleepHours: number;
}

const DEFAULT_POINTS: AccuracyPoint[] = [
  { day: "Mon", accuracy: 75, sleepHours: 6.5 },
  { day: "Tue", accuracy: 80, sleepHours: 7.0 },
  { day: "Wed", accuracy: 65, sleepHours: 5.0 },
  { day: "Thu", accuracy: 70, sleepHours: 5.5 },
  { day: "Fri", accuracy: 85, sleepHours: 7.5 },
  { day: "Sat", accuracy: 90, sleepHours: 8.0 },
  { day: "Sun", accuracy: 88, sleepHours: 7.5 },
];

export function AccuracyLine() {
  return (
    <div className="p-5 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-4">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
          <TrendingUp className="w-4 h-4 text-indigo-400" />
          <span>Quiz Accuracy Trend & Sleep Correlation</span>
        </div>
        <span className="text-xs font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
          Avg: 79%
        </span>
      </div>

      <div className="h-40 flex items-end justify-between gap-2 pt-6 px-2">
        {DEFAULT_POINTS.map((pt) => {
          const heightPct = pt.accuracy;
          const isHighSleep = pt.sleepHours >= 6.5;

          return (
            <div key={pt.day} className="flex-1 flex flex-col items-center gap-2 group">
              <span className="text-[10px] font-mono text-zinc-400 opacity-0 group-hover:opacity-100 transition-opacity">
                {pt.accuracy}% ({pt.sleepHours}h)
              </span>
              <div className="w-full bg-zinc-800/80 rounded-t-md h-28 flex items-end justify-center p-1">
                <div
                  className={`w-full rounded-t transition-all duration-500 ${
                    isHighSleep ? "bg-indigo-500" : "bg-amber-500/80"
                  }`}
                  style={{ height: `${heightPct}%` }}
                />
              </div>
              <span className="text-[11px] font-mono text-zinc-400">{pt.day}</span>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-center gap-6 text-[11px] text-zinc-400 pt-2 border-t border-zinc-800/60">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm bg-indigo-500" />
          <span>Optimal Sleep (&gt;= 6.5h)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm bg-amber-500/80" />
          <span>Under-rested (&lt; 6.5h)</span>
        </div>
      </div>
    </div>
  );
}
