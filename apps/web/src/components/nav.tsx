"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Calendar,
  MessageSquare,
  Dumbbell,
  BookOpen,
  ListTodo,
  ShieldCheck,
  Cpu,
  Radio,
  TrendingUp,
} from "lucide-react";
import { clsx } from "clsx";

export interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    name: "Today",
    href: "/today",
    icon: Calendar,
    description: "Daily curriculum and briefings",
  },
  {
    name: "Ask",
    href: "/ask",
    icon: MessageSquare,
    description: "Interactive grounded Q&A",
  },
  {
    name: "Practice",
    href: "/practice",
    icon: Dumbbell,
    description: "Adaptive testing & recall",
  },
  {
    name: "Library",
    href: "/library",
    icon: BookOpen,
    description: "Verified document vault",
  },
  {
    name: "Planner",
    href: "/planner",
    icon: ListTodo,
    description: "Study milestones & agenda",
  },
  {
    name: "Progress",
    href: "/progress",
    icon: TrendingUp,
    description: "Weekly review & skill map",
  },
  {
    name: "Jarvis",
    href: "/jarvis",
    icon: Radio,
    description: "Live voice assistant & orb",
  },
  {
    name: "Security",
    href: "/security",
    icon: ShieldCheck,
    description: "Enclave status & gates",
  },
];

export function Nav(): React.JSX.Element {
  const pathname = usePathname();

  const isCurrent = (href: string): boolean => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname?.startsWith(href) ?? false;
  };

  return (
    <>
      {/* Desktop Responsive Sidebar */}
      <aside className="hidden md:flex flex-col w-64 min-h-screen bg-[#09090b] border-r border-white/10 p-5 shrink-0 select-none">
        {/* Brand Header */}
        <div className="flex items-center gap-3 mb-8 px-2">
          <div className="w-9 h-9 rounded-lg bg-[#121215] border border-white/10 flex items-center justify-center text-emerald-400 shadow-sm">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-semibold tracking-wide text-zinc-100 uppercase">
              TechRadar
            </h1>
            <p className="text-[11px] font-mono text-zinc-400">Cyber-Academic OS</p>
          </div>
        </div>

        {/* Navigation Items */}
        <nav aria-label="Desktop Navigation" className="flex-1 space-y-1">
          {NAV_ITEMS.map((item) => {
            const active = isCurrent(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "group flex items-center gap-3.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                  active
                    ? "bg-[#121215] text-zinc-100 border border-emerald-500/40 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04]"
                )}
              >
                <Icon
                  className={clsx(
                    "w-4 h-4 transition-colors",
                    active
                      ? "text-emerald-400"
                      : "text-zinc-400 group-hover:text-zinc-200"
                  )}
                />
                <span className="flex-1">{item.name}</span>
                {active && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Security & Enclave Indicator Badge */}
        <div className="pt-4 border-t border-white/10 mt-auto">
          <div className="bg-[#121215] border border-white/10 rounded-lg p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] font-mono text-zinc-400 flex items-center gap-1.5">
                <Radio className="w-3 h-3 text-emerald-400 animate-pulse" />
                TAILSCALE ENCLAVE
              </span>
              <span className="text-[10px] font-mono text-emerald-400 px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                ACTIVE
              </span>
            </div>
            <p className="text-[11px] text-zinc-400 truncate">
              SEC-28 CSP • SEC-41 Verified
            </p>
          </div>
        </div>
      </aside>

      {/* Mobile Floating Glass Dock */}
      <nav
        aria-label="Mobile Navigation Dock"
        className="flex md:hidden fixed bottom-4 inset-x-4 z-50 glass-dock rounded-2xl px-3 py-2.5 items-center justify-around shadow-2xl shadow-black/80"
      >
        {NAV_ITEMS.map((item) => {
          const active = isCurrent(item.href);
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-label={item.name}
              className={clsx(
                "relative flex flex-col items-center justify-center p-2 rounded-xl transition-all duration-200",
                active
                  ? "text-emerald-400 bg-white/10"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
              )}
            >
              <Icon className="w-5 h-5" />
              <span className="text-[10px] mt-1 font-medium">{item.name}</span>
              {active && (
                <span className="absolute -top-1 w-1 h-1 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.9)]" />
              )}
            </Link>
          );
        })}
      </nav>
    </>
  );
}

export default Nav;
