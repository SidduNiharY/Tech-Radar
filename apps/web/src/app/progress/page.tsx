"use client";

import React from "react";
import { GoalBars } from "../../components/progress/goal-bars";
import { AccuracyLine } from "../../components/progress/accuracy-line";
import { CheckinHeatmap } from "../../components/progress/checkin-heatmap";
import { SkillMapTable } from "../../components/progress/skill-map-table";
import { Calendar, CheckCircle, Flame, Lightbulb, Sparkles, TrendingUp } from "lucide-react";

export default function ProgressPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-8 pb-16">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white font-mono">
              Progress & Mastery
            </h1>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Week 45 (Nov 02 - Nov 08)
            </span>
          </div>
          <p className="text-sm text-zinc-400 mt-1">
            Weekly analytics, goal pacing, sleep-performance patterns, and vault skill map.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-400 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/60">
            <Calendar className="w-3.5 h-3.5 text-zinc-400" />
            <span>2026-W45</span>
          </span>
        </div>
      </div>

      {/* KPI Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-zinc-400">
            <Flame className="w-3.5 h-3.5 text-amber-500" />
            <span>Study Streak</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white">28 Days</div>
          <div className="text-[11px] text-emerald-400">🔥 Unbroken daily streak</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-zinc-400">
            <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
            <span>Total Time</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white">450 min</div>
          <div className="text-[11px] text-zinc-400">Target: 525 min (86%)</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-zinc-400">
            <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
            <span>Quiz Accuracy</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white">79.2%</div>
          <div className="text-[11px] text-emerald-400">+4.5% vs last week</div>
        </div>

        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900/40 space-y-1">
          <div className="flex items-center gap-2 text-xs font-mono text-zinc-400">
            <Sparkles className="w-3.5 h-3.5 text-rose-400" />
            <span>Cards Reviewed</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white">184</div>
          <div className="text-[11px] text-zinc-400">FSRS Spaced Repetition</div>
        </div>
      </div>

      {/* Behavioral Correlation Pattern Banner */}
      <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10 text-indigo-200 flex items-start gap-3">
        <Lightbulb className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
        <div>
          <div className="font-semibold text-sm text-indigo-100 flex items-center gap-2">
            <span>Correlation Insight (Plain Code Calculation)</span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/40">
              Confidence: High
            </span>
          </div>
          <p className="text-xs text-indigo-300/90 mt-0.5">
            Your quiz accuracy is 12 points lower after nights under 6 hours (14 days of data). Consider moving challenging revision blocks after full rest nights.
          </p>
        </div>
      </div>

      {/* Visual Charts Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <GoalBars />
        <AccuracyLine />
      </div>

      {/* 28-Day Consistency Heatmap */}
      <CheckinHeatmap />

      {/* Skill Map Table */}
      <SkillMapTable />
    </div>
  );
}
