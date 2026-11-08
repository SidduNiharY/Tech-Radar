"use client";

import React from "react";
import { Target } from "lucide-react";

interface GoalProgress {
  goal: string;
  label: string;
  actualMinutes: number;
  targetMinutes: number;
  color: string;
}

interface GoalBarsProps {
  goals?: GoalProgress[];
}

const DEFAULT_GOALS: GoalProgress[] = [
  { goal: "gate", label: "GATE DA / CS", actualMinutes: 180, targetMinutes: 240, color: "bg-indigo-500" },
  { goal: "dev", label: "Full-Stack AI Dev", actualMinutes: 135, targetMinutes: 120, color: "bg-emerald-500" },
  { goal: "bank", label: "Bank & Govt Exams", actualMinutes: 60, targetMinutes: 90, color: "bg-amber-500" },
  { goal: "english", label: "English & Soft Skills", actualMinutes: 45, targetMinutes: 45, color: "bg-rose-500" },
  { goal: "world", label: "World Understanding", actualMinutes: 30, targetMinutes: 30, color: "bg-cyan-500" },
];

export function GoalBars({ goals = DEFAULT_GOALS }: GoalBarsProps) {
  return (
    <div
      role="region"
      aria-label="Study minutes per goal"
      className="p-5 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-4"
    >
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
          <Target className="w-4 h-4 text-emerald-400" />
          <span>Study Targets vs Actuals (Weekly)</span>
        </div>
        <span className="text-xs font-mono text-zinc-400">Total: 450 / 525 mins</span>
      </div>

      <div className="space-y-4" role="img" aria-label="minutes per goal chart">
        {goals.map((item) => {
          const pct = Math.min(100, Math.round((item.actualMinutes / item.targetMinutes) * 100));
          const isOver = item.actualMinutes >= item.targetMinutes;

          return (
            <div key={item.goal} className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="font-medium text-zinc-200">{item.label}</span>
                <span className="font-mono text-zinc-400">
                  {item.actualMinutes}m / {item.targetMinutes}m{" "}
                  <span className={isOver ? "text-emerald-400 font-semibold" : "text-zinc-500"}>
                    ({pct}%)
                  </span>
                </span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-2.5 overflow-hidden">
                <div
                  className={`h-2.5 rounded-full transition-all duration-500 ${item.color}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
