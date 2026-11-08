"use client";

import React, { useState } from "react";
import { CheckCircle2, Clock, MapPin, Sparkles } from "lucide-react";

export type SkillStatus = "not_started" | "learning" | "built";

interface SkillItem {
  id: string;
  name: string;
  category: "dev" | "gate" | "bank" | "english" | "world";
  status: SkillStatus;
  updated: string;
}

const INITIAL_SKILLS: SkillItem[] = [
  { id: "1", name: "FastAPI Async Services", category: "dev", status: "built", updated: "2026-11-08" },
  { id: "2", name: "Linear Algebra & SVD", category: "gate", status: "learning", updated: "2026-11-08" },
  { id: "3", name: "Docker Security & CapDrop", category: "dev", status: "built", updated: "2026-11-08" },
  { id: "4", name: "Monetary Policy & Repo Rates", category: "world", status: "built", updated: "2026-11-08" },
  { id: "5", name: "Syllabus Tree Parser", category: "gate", status: "built", updated: "2026-11-08" },
  { id: "6", name: "Data Structures & Graphs", category: "gate", status: "learning", updated: "2026-11-07" },
  { id: "7", name: "Bank Aptitude Coding Formulas", category: "bank", status: "built", updated: "2026-11-07" },
  { id: "8", name: "Pronunciation IPA & Fluency", category: "english", status: "learning", updated: "2026-11-08" },
];

export function SkillMapTable() {
  const [skills, setSkills] = useState<SkillItem[]>(INITIAL_SKILLS);

  const handleStatusChange = (id: string, nextStatus: SkillStatus) => {
    setSkills((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: nextStatus, updated: "2026-11-08" } : s))
    );
  };

  const getStatusBadge = (status: SkillStatus) => {
    switch (status) {
      case "built":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" /> Built
          </span>
        );
      case "learning":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Clock className="w-3 h-3" /> Learning
          </span>
        );
      case "not_started":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
            Not Started
          </span>
        );
    }
  };

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 space-y-4">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
          <MapPin className="w-4 h-4 text-emerald-400" />
          <span>Interactive Skill Map (Vault Markdown Synced)</span>
        </div>
        <span className="text-xs font-mono text-zinc-400">
          Built: {skills.filter((s) => s.status === "built").length} / {skills.length}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-400 font-mono">
              <th className="pb-2.5 font-medium">Skill / Competency</th>
              <th className="pb-2.5 font-medium">Domain</th>
              <th className="pb-2.5 font-medium">Status</th>
              <th className="pb-2.5 font-medium">Last Synced</th>
              <th className="pb-2.5 font-medium text-right">Update Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {skills.map((skill) => (
              <tr key={skill.id} className="hover:bg-zinc-800/20 transition-colors">
                <td className="py-2.5 font-medium text-zinc-200">{skill.name}</td>
                <td className="py-2.5 uppercase text-[10px] font-mono text-zinc-400">
                  {skill.category}
                </td>
                <td className="py-2.5">{getStatusBadge(skill.status)}</td>
                <td className="py-2.5 font-mono text-zinc-500">{skill.updated}</td>
                <td className="py-2.5 text-right space-x-1">
                  {(["not_started", "learning", "built"] as SkillStatus[]).map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => handleStatusChange(skill.id, st)}
                      className={`px-2 py-0.5 rounded text-[10px] font-mono border transition-all ${
                        skill.status === st
                          ? "bg-zinc-700 text-white border-zinc-500 font-semibold"
                          : "bg-zinc-900 text-zinc-400 border-zinc-800 hover:border-zinc-700 hover:text-zinc-200"
                      }`}
                    >
                      {st === "not_started" ? "Reset" : st}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
