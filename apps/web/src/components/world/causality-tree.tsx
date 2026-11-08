"use client";

import React, { useState, useMemo } from "react";

export interface CauseNode {
  id: string;
  event: string;
  domain: "Economy" | "Technology" | "Geopolitics" | "Energy" | string;
  confidence: number;
  stage: "root" | "intermediate" | "downstream";
}

export interface CausalLink {
  source_id: string;
  target_id: string;
  relationship: string;
  evidence_quote: string;
}

export interface CausalityTreeProps {
  initialNodes?: CauseNode[];
  initialLinks?: CausalLink[];
  onNodeClick?: (node: CauseNode) => void;
  className?: string;
}

export const DEFAULT_CAUSAL_NODES: CauseNode[] = [
  // Root Causes (in-degree 0)
  {
    id: "root-1",
    event: "RBI Repo Rate Kept at 6.50% Plateau",
    domain: "Economy",
    confidence: 0.98,
    stage: "root",
  },
  {
    id: "root-2",
    event: "Global Crude Oil Benchmark Stabilization ($74/bbl)",
    domain: "Energy",
    confidence: 0.92,
    stage: "root",
  },
  {
    id: "root-3",
    event: "Open-Weights Speculative Decoding Inference Breakthroughs",
    domain: "Technology",
    confidence: 0.95,
    stage: "root",
  },

  // Intermediate Links / Channels
  {
    id: "mid-1",
    event: "Commercial Bank Lending Spreads & Fixed Deposit Yields Steady",
    domain: "Economy",
    confidence: 0.91,
    stage: "intermediate",
  },
  {
    id: "mid-2",
    event: "Domestic Logistics & Food Transport Input Costs Containment",
    domain: "Economy",
    confidence: 0.89,
    stage: "intermediate",
  },
  {
    id: "mid-3",
    event: "Commodity Hardware Edge AI Serving Latency Drops by 68%",
    domain: "Technology",
    confidence: 0.94,
    stage: "intermediate",
  },

  // Downstream Effects
  {
    id: "leaf-1",
    event: "Retail CPI Headline Inflation Re-Anchoring to 4.5% FY27 Target",
    domain: "Economy",
    confidence: 0.96,
    stage: "downstream",
  },
  {
    id: "leaf-2",
    event: "Gross Fixed Capital Formation Expansion to 7.2% GDP Growth",
    domain: "Economy",
    confidence: 0.9,
    stage: "downstream",
  },
  {
    id: "leaf-3",
    event: "Decentralized Second-Brain Deployments Displace Cloud SaaS RAG",
    domain: "Technology",
    confidence: 0.87,
    stage: "downstream",
  },
];

export const DEFAULT_CAUSAL_LINKS: CausalLink[] = [
  {
    source_id: "root-1",
    target_id: "mid-1",
    relationship: "anchors liquidity cost",
    evidence_quote: "MPC statement confirms credit growth moderating toward sustainable deposit pace under steady 6.5% policy repo corridor.",
  },
  {
    source_id: "root-2",
    target_id: "mid-2",
    relationship: "depressurizes fuel surcharge",
    evidence_quote: "WPI transport fuel index dropped 1.8%, neutralizing secondary food distribution pricing pass-through.",
  },
  {
    source_id: "mid-1",
    target_id: "leaf-2",
    relationship: "sustains long-term corporate capex",
    evidence_quote: "Predictable borrowing environment supported private investment projects commissioning in heavy engineering.",
  },
  {
    source_id: "mid-2",
    target_id: "leaf-1",
    relationship: "restrains retail perishable margins",
    evidence_quote: "Urban vegetables and pulses consumer price index decelerated 240 bps in latest MoSPI release.",
  },
  {
    source_id: "root-3",
    target_id: "mid-3",
    relationship: "eliminates memory bandwidth bottleneck",
    evidence_quote: "Multi-token draft heads combined with dual-pipe KV cache allow 70B models to achieve 42 tok/s on single Mac workstations.",
  },
  {
    source_id: "mid-3",
    target_id: "leaf-3",
    relationship: "shifts workload from hyperscaler to private edge",
    evidence_quote: "Zero API token costs and air-gapped data confidentiality make on-device inference the default enterprise architecture.",
  },
];

export function CausalityTree({
  initialNodes = DEFAULT_CAUSAL_NODES,
  initialLinks = DEFAULT_CAUSAL_LINKS,
  onNodeClick,
  className = "",
}: CausalityTreeProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string>("root-1");
  const [selectedDomain, setSelectedDomain] = useState<string>("All");

  const domains = ["All", "Economy", "Technology", "Energy", "Geopolitics"];

  const nodeMap = useMemo(() => {
    const map = new Map<string, CauseNode>();
    initialNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [initialNodes]);

  // Compute upstream root causes and downstream reachable effects for selected node
  const activeChain = useMemo(() => {
    if (!selectedNodeId || !nodeMap.has(selectedNodeId)) {
      return { rootCauses: [], effects: [], directLinks: [] };
    }

    // Direct links involving selected node
    const directLinks = initialLinks.filter(
      (l) => l.source_id === selectedNodeId || l.target_id === selectedNodeId
    );

    // Upstream ancestors
    const visitedAncestors = new Set<string>();
    const ancestorQueue = [selectedNodeId];
    while (ancestorQueue.length > 0) {
      const current = ancestorQueue.shift()!;
      for (const link of initialLinks) {
        if (link.target_id === current && !visitedAncestors.has(link.source_id)) {
          visitedAncestors.add(link.source_id);
          ancestorQueue.push(link.source_id);
        }
      }
    }

    // Downstream successors
    const visitedSuccessors = new Set<string>();
    const successorQueue = [selectedNodeId];
    while (successorQueue.length > 0) {
      const current = successorQueue.shift()!;
      for (const link of initialLinks) {
        if (link.source_id === current && !visitedSuccessors.has(link.target_id)) {
          visitedSuccessors.add(link.target_id);
          successorQueue.push(link.target_id);
        }
      }
    }

    const rootCauses = Array.from(visitedAncestors)
      .map((id) => nodeMap.get(id)!)
      .filter((n) => n && n.stage === "root");

    const effects = Array.from(visitedSuccessors)
      .map((id) => nodeMap.get(id)!)
      .filter(Boolean);

    return { rootCauses, effects, directLinks };
  }, [selectedNodeId, initialLinks, nodeMap]);

  const selectedNode = nodeMap.get(selectedNodeId);

  // Group nodes by stage and domain filter
  const rootNodes = initialNodes.filter(
    (n) => n.stage === "root" && (selectedDomain === "All" || n.domain === selectedDomain)
  );
  const intermediateNodes = initialNodes.filter(
    (n) => n.stage === "intermediate" && (selectedDomain === "All" || n.domain === selectedDomain)
  );
  const downstreamNodes = initialNodes.filter(
    (n) => n.stage === "downstream" && (selectedDomain === "All" || n.domain === selectedDomain)
  );

  const handleSelectNode = (node: CauseNode) => {
    setSelectedNodeId(node.id);
    onNodeClick?.(node);
  };

  const getDomainBadge = (domain: string) => {
    switch (domain) {
      case "Economy":
        return "bg-emerald-950/70 text-emerald-300 border-emerald-500/40";
      case "Technology":
        return "bg-violet-950/70 text-violet-300 border-violet-500/40";
      case "Energy":
        return "bg-amber-950/70 text-amber-300 border-amber-500/40";
      default:
        return "bg-sky-950/70 text-sky-300 border-sky-500/40";
    }
  };

  return (
    <section
      data-testid="causality-tree"
      className={`relative rounded-xl border border-zinc-800/80 bg-[#090a0f]/95 p-5 md:p-6 backdrop-blur-md shadow-2xl transition-all duration-300 ${className}`}
    >
      {/* Top Hairline Violet Accent */}
      <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-violet-500/40 to-transparent" />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-violet-400 shadow-[0_0_8px_rgba(167,139,250,0.8)]" />
          <h3 className="font-mono text-xs uppercase tracking-wider font-semibold text-zinc-300">
            Causal Inference & Event Chain Graph
          </h3>
          <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-zinc-900 text-zinc-400 border border-zinc-800">
            Directed Acyclic Graph
          </span>
        </div>

        {/* Domain Filter Pills */}
        <div className="flex items-center gap-1.5 font-mono text-xs">
          {domains.map((dom) => (
            <button
              key={dom}
              type="button"
              onClick={() => setSelectedDomain(dom)}
              className={`px-2.5 py-0.5 rounded text-[11px] transition-all ${
                selectedDomain === dom
                  ? "bg-violet-600/30 text-violet-300 border border-violet-500/50 font-semibold"
                  : "bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 border border-transparent"
              }`}
            >
              {dom}
            </button>
          ))}
        </div>
      </div>

      {/* Three-Tier Visual Causal Pipeline */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-6 relative">
        {/* Column 1: Root Causes */}
        <div className="space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
            <span className="font-mono text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
              <span>●</span> Root Causes (In-degree: 0)
            </span>
            <span className="text-[10px] font-mono text-zinc-500">
              {rootNodes.length} nodes
            </span>
          </div>

          <div className="space-y-2.5">
            {rootNodes.map((node) => {
              const isSelected = selectedNodeId === node.id;
              return (
                <div
                  key={node.id}
                  data-testid={`cause-node-${node.id}`}
                  onClick={() => handleSelectNode(node)}
                  className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                    isSelected
                      ? "border-emerald-500 bg-emerald-950/30 shadow-[0_0_20px_rgba(16,185,129,0.2)]"
                      : "border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5 font-mono text-[10px]">
                    <span className={`px-2 py-0.5 rounded border ${getDomainBadge(node.domain)}`}>
                      {node.domain}
                    </span>
                    <span className="text-zinc-500">conf: {(node.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p className="text-xs font-medium text-zinc-200 leading-snug">
                    {node.event}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Column 2: Intermediate Links */}
        <div className="space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
            <span className="font-mono text-xs font-semibold text-violet-400 flex items-center gap-1.5">
              <span>➔</span> Transmission Channels
            </span>
            <span className="text-[10px] font-mono text-zinc-500">
              {intermediateNodes.length} nodes
            </span>
          </div>

          <div className="space-y-2.5">
            {intermediateNodes.map((node) => {
              const isSelected = selectedNodeId === node.id;
              return (
                <div
                  key={node.id}
                  data-testid={`cause-node-${node.id}`}
                  onClick={() => handleSelectNode(node)}
                  className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                    isSelected
                      ? "border-violet-500 bg-violet-950/30 shadow-[0_0_20px_rgba(139,92,246,0.2)]"
                      : "border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5 font-mono text-[10px]">
                    <span className={`px-2 py-0.5 rounded border ${getDomainBadge(node.domain)}`}>
                      {node.domain}
                    </span>
                    <span className="text-zinc-500">conf: {(node.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p className="text-xs font-medium text-zinc-200 leading-snug">
                    {node.event}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Column 3: Downstream Effects */}
        <div className="space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
            <span className="font-mono text-xs font-semibold text-amber-400 flex items-center gap-1.5">
              <span>◆</span> Downstream Impacts
            </span>
            <span className="text-[10px] font-mono text-zinc-500">
              {downstreamNodes.length} nodes
            </span>
          </div>

          <div className="space-y-2.5">
            {downstreamNodes.map((node) => {
              const isSelected = selectedNodeId === node.id;
              return (
                <div
                  key={node.id}
                  data-testid={`cause-node-${node.id}`}
                  onClick={() => handleSelectNode(node)}
                  className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                    isSelected
                      ? "border-amber-500 bg-amber-950/30 shadow-[0_0_20px_rgba(245,158,11,0.2)]"
                      : "border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5 font-mono text-[10px]">
                    <span className={`px-2 py-0.5 rounded border ${getDomainBadge(node.domain)}`}>
                      {node.domain}
                    </span>
                    <span className="text-zinc-500">conf: {(node.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p className="text-xs font-medium text-zinc-200 leading-snug">
                    {node.event}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Selected Node Deep-Dive Drawer */}
      {selectedNode && (
        <div
          data-testid="node-inspector"
          className="mt-6 rounded-xl border border-zinc-800 bg-[#0c0d14] p-4 md:p-5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-zinc-800">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-semibold text-violet-300">
                Event Inspector // Node ID: [{selectedNode.id}]
              </span>
              <span className={`font-mono text-[10px] px-2 py-0.5 rounded border ${getDomainBadge(selectedNode.domain)}`}>
                {selectedNode.domain}
              </span>
            </div>
            <span className="font-mono text-xs text-emerald-400">
              Inference Confidence: {(selectedNode.confidence * 100).toFixed(0)}%
            </span>
          </div>

          <h4 className="mt-2 text-sm font-semibold text-zinc-100">
            {selectedNode.event}
          </h4>

          {/* Active Chain Upstream & Downstream traversal summary */}
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
            {/* Upstream Root Causes */}
            <div className="rounded-lg bg-zinc-950/80 p-3 border border-zinc-800/60">
              <span className="text-zinc-500 block mb-1">
                Upstream Root Causes ({activeChain.rootCauses.length}):
              </span>
              {activeChain.rootCauses.length > 0 ? (
                <ul className="space-y-1">
                  {activeChain.rootCauses.map((rc) => (
                    <li key={rc.id} className="text-emerald-400 flex items-center gap-1.5">
                      <span>✓</span> {rc.event}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-zinc-600">This node is an originating root cause.</span>
              )}
            </div>

            {/* Downstream Effects */}
            <div className="rounded-lg bg-zinc-950/80 p-3 border border-zinc-800/60">
              <span className="text-zinc-500 block mb-1">
                Reachable Effects ({activeChain.effects.length}):
              </span>
              {activeChain.effects.length > 0 ? (
                <ul className="space-y-1">
                  {activeChain.effects.map((ef) => (
                    <li key={ef.id} className="text-amber-400 flex items-center gap-1.5">
                      <span>➔</span> {ef.event}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-zinc-600">Terminal effect node with no further descendants.</span>
              )}
            </div>
          </div>

          {/* Evidence Quotes from active links */}
          {activeChain.directLinks.length > 0 && (
            <div className="mt-3 pt-3 border-t border-zinc-800/60 space-y-2">
              <span className="font-mono text-[11px] text-zinc-500 block">
                Corroborating Evidence Quotes from Causal Links:
              </span>
              {activeChain.directLinks.map((link, idx) => (
                <div key={idx} className="rounded bg-zinc-950 p-2.5 border border-zinc-800/60 text-xs">
                  <div className="flex items-center gap-2 font-mono text-[10px] text-violet-400 mb-1">
                    <span>{link.source_id}</span>
                    <span>―({link.relationship})→</span>
                    <span>{link.target_id}</span>
                  </div>
                  <blockquote className="text-zinc-300 italic">
                    &ldquo;{link.evidence_quote}&rdquo;
                  </blockquote>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
