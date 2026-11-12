"use client";

import React, { useEffect, useMemo, useState } from "react";
import { isSafeLink } from "../../lib/security";

export interface StreamdownProps {
  content: string;
  onCitationClick?: (citationId: string) => void;
  allowedLinkPrefixes?: string[];
  allowedImagePrefixes?: string[];
  isStreaming?: boolean;
  className?: string;
}

/**
 * Format LaTeX math expression when KaTeX is not loaded or as safe fallback.
 */
function formatMathNotation(tex: string): string {
  let s = tex.trim();

  // Greek letters
  const greek: Record<string, string> = {
    "\\alpha": "α",
    "\\beta": "β",
    "\\gamma": "γ",
    "\\delta": "δ",
    "\\epsilon": "ε",
    "\\zeta": "ζ",
    "\\eta": "η",
    "\\theta": "θ",
    "\\iota": "ι",
    "\\kappa": "κ",
    "\\lambda": "λ",
    "\\mu": "μ",
    "\\nu": "ν",
    "\\xi": "ξ",
    "\\pi": "π",
    "\\rho": "ρ",
    "\\sigma": "σ",
    "\\tau": "τ",
    "\\upsilon": "υ",
    "\\phi": "φ",
    "\\chi": "χ",
    "\\psi": "ψ",
    "\\omega": "ω",
    "\\Gamma": "Γ",
    "\\Delta": "Δ",
    "\\Theta": "Θ",
    "\\Lambda": "Λ",
    "\\Xi": "Ξ",
    "\\Pi": "Π",
    "\\Sigma": "Σ",
    "\\Upsilon": "Υ",
    "\\Phi": "Φ",
    "\\Psi": "Ψ",
    "\\Omega": "Ω",
  };

  for (const [k, v] of Object.entries(greek)) {
    s = s.replaceAll(k, v);
  }

  // Common math symbols
  s = s.replaceAll("\\times", "×");
  s = s.replaceAll("\\cdot", "·");
  s = s.replaceAll("\\leq", "≤");
  s = s.replaceAll("\\le", "≤");
  s = s.replaceAll("\\geq", "≥");
  s = s.replaceAll("\\ge", "≥");
  s = s.replaceAll("\\neq", "≠");
  s = s.replaceAll("\\ne", "≠");
  s = s.replaceAll("\\approx", "≈");
  s = s.replaceAll("\\infty", "∞");
  s = s.replaceAll("\\in", "∈");
  s = s.replaceAll("\\notin", "∉");
  s = s.replaceAll("\\subset", "⊂");
  s = s.replaceAll("\\subseteq", "⊆");
  s = s.replaceAll("\\forall", "∀");
  s = s.replaceAll("\\exists", "∃");
  s = s.replaceAll("\\nabla", "∇");
  s = s.replaceAll("\\partial", "∂");
  s = s.replaceAll("\\pm", "±");
  s = s.replaceAll("\\mp", "∓");
  s = s.replaceAll("\\sum", "∑");
  s = s.replaceAll("\\prod", "∏");
  s = s.replaceAll("\\int", "∫");
  s = s.replaceAll("\\to", "→");
  s = s.replaceAll("\\rightarrow", "→");
  s = s.replaceAll("\\leftarrow", "←");
  s = s.replaceAll("\\leftrightarrow", "↔");
  s = s.replaceAll("\\Rightarrow", "⇒");
  s = s.replaceAll("\\Leftarrow", "⇐");
  s = s.replaceAll("\\Leftrightarrow", "⇔");

  // \frac{a}{b} -> (a / b)
  s = s.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1 / $2)");

  // \sqrt{x} -> √(x)
  s = s.replace(/\\sqrt\{([^{}]+)\}/g, "√($1)");

  // \text{abc} -> abc
  s = s.replace(/\\text\{([^{}]+)\}/g, "$1");
  s = s.replace(/\\mathrm\{([^{}]+)\}/g, "$1");
  s = s.replace(/\\mathbf\{([^{}]+)\}/g, "$1");

  // Superscripts and subscripts
  const supers: Record<string, string> = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "+": "⁺",
    "-": "⁻",
    "=": "⁼",
    "(": "⁽",
    ")": "⁾",
    n: "ⁿ",
    i: "ⁱ",
  };
  const subs: Record<string, string> = {
    "0": "₀",
    "1": "₁",
    "2": "₂",
    "3": "₃",
    "4": "₄",
    "5": "₅",
    "6": "₆",
    "7": "₇",
    "8": "₈",
    "9": "₉",
    "+": "₊",
    "-": "₋",
    "=": "₌",
    "(": "₍",
    ")": "₎",
    a: "ₐ",
    e: "ₑ",
    o: "ₒ",
    x: "ₓ",
    i: "ᵢ",
    j: "ⱼ",
    k: "ₖ",
    t: "ₜ",
  };

  s = s.replace(/\^([0-9\+\-\(\)ni])/g, (_, ch) => supers[ch] || `^${ch}`);
  s = s.replace(/\_([0-9\+\-\(\)aeoxijkt])/g, (_, ch) => subs[ch] || `_${ch}`);
  s = s.replace(/\^\{([^{}]+)\}/g, "^($1)");
  s = s.replace(/\_\{([^{}]+)\}/g, "_($1)");

  return s;
}

/**
 * LaTeX Equation Component with KaTeX rendering and safe fallback.
 */
function LatexMath({
  tex,
  displayMode = false,
}: {
  tex: string;
  displayMode?: boolean;
}) {
  const [katexHtml, setKatexHtml] = useState<string | null>(null);

  useEffect(() => {
    // Check if katex is available on window or global
    if (typeof window !== "undefined") {
      const globalKatex = (window as unknown as { katex?: { renderToString: (tex: string, opts: unknown) => string } }).katex;
      if (globalKatex && typeof globalKatex.renderToString === "function") {
        try {
          const rendered = globalKatex.renderToString(tex, {
            displayMode,
            throwOnError: false,
          });
          setKatexHtml(rendered);
          return;
        } catch {
          // fallback
        }
      }
    }
  }, [tex, displayMode]);

  if (katexHtml) {
    return (
      <span
        className={displayMode ? "block my-3 text-center overflow-x-auto py-2" : "inline-block px-1"}
        dangerouslySetInnerHTML={{ __html: katexHtml }}
      />
    );
  }

  // Safe styled mathematical notation fallback
  const formatted = formatMathNotation(tex);
  if (displayMode) {
    return (
      <div className="my-3 p-3 rounded-md bg-zinc-900/90 border border-zinc-800 text-center overflow-x-auto">
        <span className="font-serif italic text-indigo-300 text-base tracking-wide select-all">
          {formatted}
        </span>
      </div>
    );
  }

  return (
    <span className="inline-block px-1.5 py-0.5 mx-0.5 rounded bg-zinc-900/70 border border-zinc-800/80 font-serif italic text-indigo-300 text-sm select-all">
      {formatted}
    </span>
  );
}

interface MermaidNode {
  id: string;
  label: string;
  shape: "rect" | "round" | "decision" | "stadium";
}

interface MermaidEdge {
  from: string;
  to: string;
  label?: string;
  style?: "arrow" | "line";
}

/**
 * Safe Mermaid Structured Diagram Renderer adhering strictly to SEC-28.
 * Parses flowcharts / graphs and renders a clean Cyber-Academic SVG diagram without external script execution.
 */
function MermaidDiagram({ code }: { code: string }) {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);

  const parsed = useMemo(() => {
    const lines = code.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("%%"));
    const nodes = new Map<string, MermaidNode>();
    const edges: MermaidEdge[] = [];
    let direction: "TD" | "LR" = "TD";

    for (const line of lines) {
      if (line.startsWith("graph") || line.startsWith("flowchart")) {
        if (line.includes("LR")) direction = "LR";
        continue;
      }

      // Match connections: A --> B, A[Label] -->|Text| B(Label)
      const edgeRegex = /([A-Za-z0-9_-]+)(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\}|\(\[(.*?)\]\))?\s*(-->|---|-.->|==>)(?:\|(.*?)\|)?\s*([A-Za-z0-9_-]+)(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\}|\(\[(.*?)\]\))?/;
      const match = line.match(edgeRegex);

      if (match) {
        const fromId = match[1];
        const fromRect = match[2];
        const fromRound = match[3];
        const fromDecision = match[4];
        const fromStadium = match[5];
        const edgeType = match[6];
        const edgeLabel = match[7];
        const toId = match[8];
        const toRect = match[9];
        const toRound = match[10];
        const toDecision = match[11];
        const toStadium = match[12];

        // Register from node
        if (!nodes.has(fromId)) {
          const label = fromRect || fromRound || fromDecision || fromStadium || fromId;
          const shape = fromDecision ? "decision" : fromStadium ? "stadium" : fromRound ? "round" : "rect";
          nodes.set(fromId, { id: fromId, label, shape });
        }

        // Register to node
        if (!nodes.has(toId)) {
          const label = toRect || toRound || toDecision || toStadium || toId;
          const shape = toDecision ? "decision" : toStadium ? "stadium" : toRound ? "round" : "rect";
          nodes.set(toId, { id: toId, label, shape });
        }

        edges.push({
          from: fromId,
          to: toId,
          label: edgeLabel?.trim(),
          style: edgeType.includes(">") ? "arrow" : "line",
        });
      } else {
        // Standalone node definition: Node1[Text]
        const singleNodeMatch = line.match(/([A-Za-z0-9_-]+)(?:\[(.*?)\]|\((.*?)\)|\{(.*?)\}|\(\[(.*?)\]\))/);
        if (singleNodeMatch) {
          const id = singleNodeMatch[1];
          const label = singleNodeMatch[2] || singleNodeMatch[3] || singleNodeMatch[4] || singleNodeMatch[5] || id;
          const shape = singleNodeMatch[4] ? "decision" : singleNodeMatch[5] ? "stadium" : singleNodeMatch[3] ? "round" : "rect";
          if (!nodes.has(id)) {
            nodes.set(id, { id, label, shape });
          }
        }
      }
    }

    return {
      direction,
      nodes: Array.from(nodes.values()),
      edges,
    };
  }, [code]);

  const handleCopy = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(code);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (showRaw || parsed.nodes.length === 0) {
    return (
      <div className="my-4 rounded-lg bg-zinc-950 border border-zinc-800 overflow-hidden font-mono text-xs">
        <div className="px-3 py-2 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between">
          <span className="text-zinc-400">Mermaid Diagram Source</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              className="text-zinc-400 hover:text-zinc-200"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            {parsed.nodes.length > 0 && (
              <button
                type="button"
                onClick={() => setShowRaw(false)}
                className="text-indigo-400 hover:text-indigo-300"
              >
                View Diagram
              </button>
            )}
          </div>
        </div>
        <pre className="p-4 overflow-x-auto text-zinc-300">{code}</pre>
      </div>
    );
  }

  // Layout calculations for Cyber-Academic SVG rendering
  const isTD = parsed.direction === "TD";
  const nodeWidth = 160;
  const nodeHeight = 44;
  const gapX = isTD ? 40 : 80;
  const gapY = isTD ? 64 : 40;

  // Simple layered layout
  const nodePositions = new Map<string, { x: number; y: number }>();
  parsed.nodes.forEach((node, index) => {
    if (isTD) {
      const col = index % 2;
      const row = Math.floor(index / 2);
      nodePositions.set(node.id, {
        x: 40 + col * (nodeWidth + gapX),
        y: 30 + row * (nodeHeight + gapY),
      });
    } else {
      const row = index % 2;
      const col = Math.floor(index / 2);
      nodePositions.set(node.id, {
        x: 40 + col * (nodeWidth + gapX),
        y: 30 + row * (nodeHeight + gapY),
      });
    }
  });

  const maxCols = isTD ? Math.min(2, parsed.nodes.length) : Math.ceil(parsed.nodes.length / 2);
  const maxRows = isTD ? Math.ceil(parsed.nodes.length / 2) : Math.min(2, parsed.nodes.length);
  const svgWidth = Math.max(380, 80 + maxCols * (nodeWidth + gapX));
  const svgHeight = Math.max(160, 60 + maxRows * (nodeHeight + gapY));

  return (
    <div className="my-4 rounded-lg bg-zinc-950 border border-zinc-800 overflow-hidden shadow-lg shadow-black/40">
      {/* Header bar */}
      <div className="px-3 py-2 bg-zinc-900/80 border-b border-zinc-800 flex items-center justify-between text-xs font-mono">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
          <span className="text-zinc-300 font-semibold tracking-wider">
            DIAGRAM // {parsed.direction}
          </span>
          <span className="text-zinc-500">({parsed.nodes.length} nodes)</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleCopy}
            className="text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            {copied ? "Copied" : "Copy Source"}
          </button>
          <button
            type="button"
            onClick={() => setShowRaw(true)}
            className="text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            Raw Code
          </button>
        </div>
      </div>

      {/* SVG Container */}
      <div className="p-4 overflow-x-auto flex justify-center bg-[#09090b]">
        <svg
          width={svgWidth}
          height={svgHeight}
          className="select-none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <marker
              id="mermaid-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#818cf8" />
            </marker>
          </defs>

          {/* Edges */}
          {parsed.edges.map((edge, idx) => {
            const fromPos = nodePositions.get(edge.from);
            const toPos = nodePositions.get(edge.to);
            if (!fromPos || !toPos) return null;

            const startX = fromPos.x + nodeWidth / 2;
            const startY = fromPos.y + nodeHeight;
            const endX = toPos.x + nodeWidth / 2;
            const endY = toPos.y;

            // Direct line or curve
            const midY = (startY + endY) / 2;
            const pathData = `M ${startX} ${startY} C ${startX} ${midY}, ${endX} ${midY}, ${endX} ${endY}`;

            return (
              <g key={`edge-${idx}`}>
                <path
                  d={pathData}
                  fill="none"
                  stroke="#6366f1"
                  strokeWidth="1.75"
                  strokeDasharray={edge.style === "line" ? "4,4" : undefined}
                  markerEnd={edge.style === "arrow" ? "url(#mermaid-arrow)" : undefined}
                />
                {edge.label && (
                  <g transform={`translate(${(startX + endX) / 2}, ${midY})`}>
                    <rect
                      x="-30"
                      y="-10"
                      width="60"
                      height="20"
                      rx="4"
                      fill="#18181b"
                      stroke="#3f3f46"
                      strokeWidth="1"
                    />
                    <text
                      x="0"
                      y="3"
                      textAnchor="middle"
                      fill="#c4b5fd"
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      {edge.label}
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          {/* Nodes */}
          {parsed.nodes.map((node) => {
            const pos = nodePositions.get(node.id);
            if (!pos) return null;

            const isDecision = node.shape === "decision";
            const rx = node.shape === "stadium" ? 22 : node.shape === "round" ? 10 : 4;

            return (
              <g key={`node-${node.id}`} transform={`translate(${pos.x}, ${pos.y})`}>
                <rect
                  width={nodeWidth}
                  height={nodeHeight}
                  rx={rx}
                  fill="#18181b"
                  stroke={isDecision ? "#10b981" : "#6366f1"}
                  strokeWidth="1.5"
                  className="transition-all hover:stroke-indigo-400"
                />
                <text
                  x={nodeWidth / 2}
                  y={nodeHeight / 2 + 4}
                  textAnchor="middle"
                  fill="#f4f4f5"
                  fontSize="12"
                  fontFamily="sans-serif"
                  fontWeight="500"
                >
                  {node.label.length > 20 ? node.label.slice(0, 18) + "..." : node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

/**
 * Safe inline parser that strictly enforces SEC-28:
 * 1. Disallows raw HTML (escaped as text).
 * 2. Disallows external image tags (blocked in answer body).
 * 3. Renders inline LaTeX equations ($...$ or \(...\)).
 * 4. Converts citation markers ([C1], [C2], [C#]) into clickable emerald badges.
 */
function parseInline(
  text: string,
  onCitationClick?: (id: string) => void,
  allowedLinkPrefixes: string[] = []
): React.ReactNode[] {
  // Regex pattern matching:
  // 1. Citation badges: [C#] or [C1], [C2], etc.
  // 2. Inline math: $...$ or \(...\)
  // 3. Blocked images: ![alt](url)
  // 4. Inline code: `code`
  // 5. Bold/Italic: **bold** or *italic*
  // 6. Links: [text](url)
  // Note: HTML tags like <script> are NOT parsed as elements; they fall through to text nodes and are escaped by React.
  const tokenRegex =
    /(\[(?:C[0-9]+|C#)\])|(\$(?:\\\$|[^\$])+\$|\\\((?:[\s\S]*?)\\\))|(!\[(.*?)\]\((.*?)\))|(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[(.*?)\]\((.*?)\))/g;

  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(text)) !== null) {
    // Plain text before match
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const [fullMatch, citationMatch, mathMatch, imageMatch, imgAlt, , codeMatch, boldMatch, italicMatch, linkMatch, linkText, linkUrl] = match;

    if (citationMatch) {
      // 1. Citation badge tag [C1], [C2], [C#]
      const cleanId = citationMatch.slice(1, -1);
      nodes.push(
        <button
          key={`cite-${match.index}`}
          type="button"
          onClick={() => onCitationClick?.(cleanId)}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 mx-0.5 text-xs font-mono font-semibold rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/80 hover:bg-emerald-900 hover:border-emerald-500 hover:text-emerald-300 transition-all cursor-pointer shadow-sm shadow-emerald-950/50 align-baseline"
          title={`View grounding source [${cleanId}]`}
        >
          <span>[{cleanId}]</span>
        </button>
      );
    } else if (mathMatch) {
      // 2. Inline LaTeX Math
      let tex = mathMatch;
      if (tex.startsWith("$") && tex.endsWith("$")) {
        tex = tex.slice(1, -1);
      } else if (tex.startsWith("\\(") && tex.endsWith("\\)")) {
        tex = tex.slice(2, -2);
      }
      nodes.push(<LatexMath key={`math-${match.index}`} tex={tex} displayMode={false} />);
    } else if (imageMatch) {
      // 3. SEC-28 Enforcement: Block external image tags in answer body
      nodes.push(
        <span
          key={`img-blocked-${match.index}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 mx-1 rounded text-xs bg-zinc-900 border border-zinc-700/80 text-zinc-400 font-mono"
          title="External images are blocked for data exfiltration protection (SEC-28)"
        >
          <svg className="w-3 h-3 text-amber-500 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          [Blocked Image: {imgAlt || "external"}]
        </span>
      );
    } else if (codeMatch) {
      // 4. Inline code
      const code = codeMatch.slice(1, -1);
      nodes.push(
        <code
          key={`code-${match.index}`}
          className="font-mono text-xs bg-zinc-900 text-indigo-300 px-1.5 py-0.5 rounded border border-zinc-800"
        >
          {code}
        </code>
      );
    } else if (boldMatch) {
      // 5. Bold
      nodes.push(
        <strong key={`bold-${match.index}`} className="font-semibold text-zinc-100">
          {boldMatch.slice(2, -2)}
        </strong>
      );
    } else if (italicMatch) {
      // 6. Italic
      nodes.push(
        <em key={`italic-${match.index}`} className="italic text-zinc-200">
          {italicMatch.slice(1, -1)}
        </em>
      );
    } else if (linkMatch) {
      // 7. SEC-28 safe links
      // isSafeLink refuses "//host" and "/\host", which startsWith("/") let through.
      if (isSafeLink(linkUrl, allowedLinkPrefixes)) {
        nodes.push(
          <a
            key={`link-${match.index}`}
            href={linkUrl}
            className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 transition-colors"
          >
            {linkText}
          </a>
        );
      } else {
        // External link blocked per SEC-28 link ban
        nodes.push(
          <span
            key={`link-blocked-${match.index}`}
            className="text-zinc-300 underline decoration-zinc-600 decoration-dotted cursor-help"
            title={`Outbound link disabled (SEC-28): ${linkUrl}`}
          >
            {linkText}
          </span>
        );
      }
    } else {
      nodes.push(fullMatch);
    }

    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

/**
 * Streamdown: Safe, hardened Markdown renderer adhering strictly to SEC-28.
 */
export function Streamdown({
  content,
  onCitationClick,
  allowedLinkPrefixes = [],
  isStreaming = false,
  className = "",
}: StreamdownProps) {
  // Parse blocks: code blocks, block math, headings, lists, tables, blockquotes, paragraphs
  const blocks = useMemo(() => {
    const raw = content || "";
    const lines = raw.split("\n");
    const result: React.ReactNode[] = [];

    let i = 0;
    while (i < lines.length) {
      const line = lines[i];

      // 1. Code blocks: ```lang ... ```
      if (line.trim().startsWith("```")) {
        const lang = line.trim().slice(3).trim().toLowerCase();
        const codeLines: string[] = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith("```")) {
          codeLines.push(lines[i]);
          i++;
        }
        i++; // skip closing ```
        const fullCode = codeLines.join("\n");

        if (lang === "mermaid") {
          result.push(<MermaidDiagram key={`mermaid-${i}`} code={fullCode} />);
        } else if (lang === "math" || lang === "latex") {
          result.push(<LatexMath key={`math-${i}`} tex={fullCode} displayMode={true} />);
        } else {
          result.push(
            <div
              key={`code-${i}`}
              className="my-3 rounded-lg bg-zinc-950 border border-zinc-800 overflow-hidden font-mono text-xs"
            >
              {lang && (
                <div className="px-3 py-1.5 bg-zinc-900 border-b border-zinc-800 text-zinc-500 text-[11px] uppercase tracking-wider">
                  {lang}
                </div>
              )}
              <pre className="p-3.5 overflow-x-auto text-zinc-200 selection:bg-indigo-950">
                {fullCode}
              </pre>
            </div>
          );
        }
        continue;
      }

      // 2. Block-level Math: $$ ... $$ or \[ ... \]
      if (line.trim().startsWith("$$") || line.trim().startsWith("\\[")) {
        const isBracket = line.trim().startsWith("\\[");
        const closer = isBracket ? "\\]" : "$$";

        // Check if single line
        const trimmed = line.trim();
        const opener = isBracket ? "\\[" : "$$";
        if (trimmed.length > 2 && trimmed.endsWith(closer) && trimmed.lastIndexOf(closer) > 1) {
          const tex = trimmed.slice(opener.length, -closer.length);
          result.push(<LatexMath key={`math-block-${i}`} tex={tex} displayMode={true} />);
          i++;
          continue;
        }

        const mathLines: string[] = [];
        if (trimmed.length > opener.length) {
          mathLines.push(trimmed.slice(opener.length));
        }
        i++;
        while (i < lines.length && !lines[i].trim().endsWith(closer)) {
          mathLines.push(lines[i]);
          i++;
        }
        if (i < lines.length) {
          const endLine = lines[i].trim();
          if (endLine.length > closer.length) {
            mathLines.push(endLine.slice(0, -closer.length));
          }
          i++;
        }
        result.push(
          <LatexMath key={`math-block-${i}`} tex={mathLines.join("\n")} displayMode={true} />
        );
        continue;
      }

      // 3. Headings: #, ##, ###, ####, #####, ######
      const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        const text = headingMatch[2];
        const inline = parseInline(text, onCitationClick, allowedLinkPrefixes);

        if (level === 1) {
          result.push(
            <h1 key={`h1-${i}`} className="text-xl font-bold text-zinc-100 mt-6 mb-3 border-b border-zinc-800 pb-2">
              {inline}
            </h1>
          );
        } else if (level === 2) {
          result.push(
            <h2 key={`h2-${i}`} className="text-lg font-semibold text-zinc-100 mt-5 mb-2.5">
              {inline}
            </h2>
          );
        } else if (level === 3) {
          result.push(
            <h3 key={`h3-${i}`} className="text-base font-semibold text-zinc-200 mt-4 mb-2">
              {inline}
            </h3>
          );
        } else {
          result.push(
            <h4 key={`h4-${i}`} className="text-sm font-semibold text-zinc-300 mt-3 mb-1.5">
              {inline}
            </h4>
          );
        }
        i++;
        continue;
      }

      // 4. Horizontal Rule
      if (/^(\*\*\*|---|___)$/.test(line.trim())) {
        result.push(<hr key={`hr-${i}`} className="border-zinc-800 my-4" />);
        i++;
        continue;
      }

      // 5. Blockquotes / Alerts: > [!NOTE] or > quote
      if (line.trim().startsWith(">")) {
        const quoteLines: string[] = [];
        while (i < lines.length && lines[i].trim().startsWith(">")) {
          quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
          i++;
        }
        const fullQuote = quoteLines.join("\n");
        const inline = parseInline(fullQuote, onCitationClick, allowedLinkPrefixes);
        result.push(
          <blockquote
            key={`quote-${i}`}
            className="my-3 pl-4 border-l-2 border-indigo-500/80 bg-zinc-900/40 py-2 pr-3 rounded-r text-zinc-300 italic text-sm"
          >
            {inline}
          </blockquote>
        );
        continue;
      }

      // 6. Lists (ordered and unordered)
      if (/^(\s*[-*+]|\s*\d+\.)\s+/.test(line)) {
        const listItems: { ordered: boolean; text: string }[] = [];
        while (i < lines.length && /^(\s*[-*+]|\s*\d+\.)\s+/.test(lines[i])) {
          const itemLine = lines[i];
          const isOrdered = /^\s*\d+\./.test(itemLine);
          const itemText = itemLine.replace(/^(\s*[-*+]|\s*\d+\.)\s+/, "");
          listItems.push({ ordered: isOrdered, text: itemText });
          i++;
        }

        const isOrderedList = listItems[0].ordered;
        if (isOrderedList) {
          result.push(
            <ol key={`ol-${i}`} className="my-2.5 pl-6 list-decimal space-y-1 text-sm text-zinc-200">
              {listItems.map((item, idx) => (
                <li key={idx} className="leading-relaxed">
                  {parseInline(item.text, onCitationClick, allowedLinkPrefixes)}
                </li>
              ))}
            </ol>
          );
        } else {
          result.push(
            <ul key={`ul-${i}`} className="my-2.5 pl-5 list-disc space-y-1 text-sm text-zinc-200">
              {listItems.map((item, idx) => (
                <li key={idx} className="leading-relaxed">
                  {parseInline(item.text, onCitationClick, allowedLinkPrefixes)}
                </li>
              ))}
            </ul>
          );
        }
        continue;
      }

      // 7. Markdown Tables
      if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
        const tableLines: string[] = [];
        while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
          tableLines.push(lines[i].trim());
          i++;
        }

        if (tableLines.length >= 2) {
          const headerCells = tableLines[0]
            .slice(1, -1)
            .split("|")
            .map((c) => c.trim());
          // Check for separator row (e.g. |---|---|)
          const dataRows = tableLines.slice(1).filter((row) => !/^[|\s:-]+$/.test(row));

          result.push(
            <div key={`table-${i}`} className="my-4 overflow-x-auto rounded-lg border border-zinc-800">
              <table className="w-full text-left text-sm font-sans border-collapse">
                <thead className="bg-zinc-900 border-b border-zinc-800 text-xs font-mono uppercase text-zinc-400">
                  <tr>
                    {headerCells.map((h, hIdx) => (
                      <th key={hIdx} className="px-4 py-2.5 font-medium">
                        {parseInline(h, onCitationClick, allowedLinkPrefixes)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/80 bg-zinc-950/60">
                  {dataRows.map((row, rIdx) => {
                    const cells = row.slice(1, -1).split("|").map((c) => c.trim());
                    return (
                      <tr key={rIdx} className="hover:bg-zinc-900/40 transition-colors">
                        {cells.map((cell, cIdx) => (
                          <td key={cIdx} className="px-4 py-2 text-zinc-300">
                            {parseInline(cell, onCitationClick, allowedLinkPrefixes)}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
          continue;
        }
      }

      // 8. Paragraphs / Empty lines
      if (!line.trim()) {
        i++;
        continue;
      }

      // Gather consecutive paragraph lines
      const pLines: string[] = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !lines[i].trim().startsWith("```") &&
        !lines[i].trim().startsWith("$$") &&
        !lines[i].trim().startsWith("\\[") &&
        !lines[i].match(/^#{1,6}\s+/) &&
        !lines[i].trim().startsWith(">") &&
        !/^(\s*[-*+]|\s*\d+\.)\s+/.test(lines[i]) &&
        !(lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|"))
      ) {
        pLines.push(lines[i]);
        i++;
      }

      const pText = pLines.join(" ");
      result.push(
        <p key={`p-${i}`} className="my-2.5 text-sm leading-relaxed text-zinc-200">
          {parseInline(pText, onCitationClick, allowedLinkPrefixes)}
        </p>
      );
    }

    return result;
  }, [content, onCitationClick, allowedLinkPrefixes]);

  return (
    <div className={`space-y-1 font-sans text-zinc-200 ${className}`}>
      {blocks}
      {isStreaming && (
        <span
          className="inline-block w-1.5 h-4 ml-1 bg-indigo-500 animate-pulse align-middle"
          title="Streaming response..."
        />
      )}
    </div>
  );
}
