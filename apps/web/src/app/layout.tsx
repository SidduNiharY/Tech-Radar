import type { Metadata } from "next";
import React from "react";
import "./globals.css";
import { Nav } from "../components/nav";
import { Orb } from "../components/orb";
import { Shield, Sparkles } from "lucide-react";

export const metadata: Metadata = {
  title: "TechRadar Brain",
  description: "Cyber-Academic OS & Local Grounded Intelligence Enclave",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#09090b] text-[#f4f4f5] min-h-screen antialiased flex flex-col md:flex-row selection:bg-emerald-500/30 selection:text-emerald-200">
        {/* Navigation (Desktop Sidebar & Mobile Glass Dock) */}
        <Nav />

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 min-h-screen">
          {/* Top Header */}
          <header className="sticky top-0 z-40 h-16 border-b border-white/10 bg-[#09090b]/80 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between">
            {/* Left Title / Breadcrumbs */}
            <div className="flex items-center gap-2 sm:gap-3">
              <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                SEC-28
              </span>
              <span className="text-zinc-600">/</span>
              <h2 className="text-sm font-semibold text-zinc-200 tracking-wide">
                TechRadar Brain
              </h2>
            </div>

            {/* Right Controls: System Status Badge + Jarvis Orb */}
            <div className="flex items-center gap-3 sm:gap-4">
              {/* System Status Badge */}
              <div className="hidden sm:flex items-center gap-2 bg-[#121215] border border-white/10 px-3 py-1.5 rounded-full text-xs font-mono text-zinc-300">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
                <span className="text-zinc-300">ENCLAVE SECURE</span>
                <Shield className="w-3.5 h-3.5 text-emerald-400" />
              </div>

              {/* Jarvis Voice Assistant Orb */}
              <div className="flex items-center gap-2 pl-2 border-l border-white/10">
                <Orb
                  state="idle"
                  size={38}
                  label="Talk to Jarvis"
                />
              </div>
            </div>
          </header>

          {/* Dynamic Page Viewport */}
          <main className="flex-1 p-4 sm:p-6 pb-24 md:pb-6 overflow-y-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
