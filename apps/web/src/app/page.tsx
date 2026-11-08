import React from "react";
import Link from "next/link";
import { NAV_ITEMS } from "../components/nav";
import { ShieldCheck, Cpu, Terminal, ArrowUpRight } from "lucide-react";

export default function HomePage(): React.JSX.Element {
  return (
    <div className="max-w-6xl mx-auto space-y-8 py-4">
      {/* Enclave Hero Panel */}
      <section className="obsidian-panel p-6 sm:p-8 relative overflow-hidden bg-gradient-to-br from-[#121215] via-[#121215] to-[#181820]">
        <div className="relative z-10 max-w-2xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Air-Gapped Sovereign Intelligence Enclave</span>
          </div>

          <h1 className="text-2xl sm:text-4xl font-bold tracking-tight text-zinc-100">
            TechRadar Cyber-Academic OS
          </h1>

          <p className="text-sm sm:text-base text-zinc-400 leading-relaxed">
            Local SLM-driven research, grounded exam preparation, and multi-agent
            knowledge synthesis protected by strict Tailscale owner boundaries and
            content security policies.
          </p>

          <div className="pt-2 flex flex-wrap gap-3 font-mono text-xs text-zinc-400">
            <span className="flex items-center gap-1.5 bg-black/40 border border-white/5 px-2.5 py-1 rounded">
              <Terminal className="w-3.5 h-3.5 text-indigo-400" />
              CSP: STRICT-DYNAMIC
            </span>
            <span className="flex items-center gap-1.5 bg-black/40 border border-white/5 px-2.5 py-1 rounded">
              <Cpu className="w-3.5 h-3.5 text-amber-400" />
              SLM: QWEN 2.5 CODER
            </span>
          </div>
        </div>

        {/* Ambient Glow Accent */}
        <div
          className="absolute right-0 top-0 w-96 h-96 rounded-full pointer-events-none opacity-20"
          style={{
            background:
              "radial-gradient(circle, rgba(99, 102, 241, 0.4) 0%, rgba(16, 185, 129, 0.1) 50%, transparent 70%)",
          }}
        />
      </section>

      {/* Navigation Quick Cards */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className="group obsidian-panel p-5 hover:border-white/20 transition-all duration-200 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center text-zinc-300 group-hover:text-emerald-400 group-hover:border-emerald-500/30 transition-colors">
                    <Icon className="w-5 h-5" />
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-zinc-500 group-hover:text-zinc-200 transition-colors" />
                </div>
                <h3 className="text-base font-semibold text-zinc-200 group-hover:text-white transition-colors">
                  {item.name}
                </h3>
                <p className="text-xs text-zinc-400 mt-1 leading-relaxed">
                  {item.description}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between text-[11px] font-mono text-zinc-500">
                <span>ROUTE</span>
                <span className="text-zinc-400">{item.href}</span>
              </div>
            </Link>
          );
        })}
      </section>
    </div>
  );
}
