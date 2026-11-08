"use client";

import React from "react";
import { clsx } from "clsx";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

export interface OrbProps {
  /**
   * Current operating state of Jarvis voice pipeline.
   * - 'idle': Calm breathing violet-indigo glow.
   * - 'listening': Alert emerald glow reactive to ambient mic input.
   * - 'thinking': Amber-indigo oscillating aurora gradient.
   * - 'speaking': Electric indigo-cyan frequency ripples.
   */
  state?: OrbState;

  /**
   * Sound reactivity level between 0.0 (silent) and 1.0 (loudest).
   */
  audioLevel?: number;

  /**
   * Pixel dimension (width and height) of the orb container (default: 48).
   */
  size?: number;

  /**
   * Optional click handler (e.g. to initiate voice conversation).
   */
  onClick?: () => void;

  /**
   * Optional additional CSS classes.
   */
  className?: string;

  /**
   * Accessible button label. Defaults to "Talk to Jarvis".
   */
  label?: string;
}

export function Orb({
  state = "idle",
  audioLevel = 0,
  size = 48,
  onClick,
  className,
  label = "Talk to Jarvis",
}: OrbProps): React.JSX.Element {
  // Clamp audioLevel to [0, 1]
  const clampedAudio = Math.max(0, Math.min(1, audioLevel));

  // Determine radial gradient styling based on state
  const getGradient = (currentState: OrbState): string => {
    switch (currentState) {
      case "listening":
        return "radial-gradient(circle at 35% 35%, #34d399 0%, #10b981 45%, #059669 80%, #064e3b 100%)";
      case "thinking":
        return "radial-gradient(circle at 35% 35%, #fbbf24 0%, #f59e0b 45%, #6366f1 80%, #312e81 100%)";
      case "speaking":
        return "radial-gradient(circle at 35% 35%, #38bdf8 0%, #6366f1 45%, #4338ca 80%, #1e1b4b 100%)";
      case "idle":
      default:
        return "radial-gradient(circle at 35% 35%, #818cf8 0%, #4f46e5 45%, #312e81 80%, #1e1b4b 100%)";
    }
  };

  // Determine glow shadow box-shadow
  const getGlow = (currentState: OrbState): string => {
    const audioGlowBoost = clampedAudio * 15;
    switch (currentState) {
      case "listening":
        return `0 0 ${24 + audioGlowBoost}px rgba(16, 185, 129, ${0.5 + clampedAudio * 0.4})`;
      case "thinking":
        return "0 0 28px rgba(245, 158, 11, 0.55), 0 0 45px rgba(99, 102, 241, 0.4)";
      case "speaking":
        return `0 0 ${28 + audioGlowBoost}px rgba(99, 102, 241, ${0.6 + clampedAudio * 0.35})`;
      case "idle":
      default:
        return "0 0 20px rgba(99, 102, 241, 0.35)";
    }
  };

  // Determine ring stroke color
  const getRingColor = (currentState: OrbState): string => {
    switch (currentState) {
      case "listening":
        return "rgba(16, 185, 129, 0.7)";
      case "thinking":
        return "rgba(245, 158, 11, 0.65)";
      case "speaking":
        return "rgba(56, 189, 248, 0.75)";
      case "idle":
      default:
        return "rgba(99, 102, 241, 0.35)";
    }
  };

  const ringRadius = 42;
  const reactiveScale = 1 + clampedAudio * 0.35;

  return (
    <button
      type="button"
      role="button"
      aria-label={label}
      onClick={onClick}
      style={{
        width: `${size}px`,
        height: `${size}px`,
      }}
      className={clsx(
        "relative flex items-center justify-center rounded-full p-0 transition-transform duration-300 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-zinc-950 cursor-pointer select-none",
        className
      )}
    >
      {/* Outer Audio Frequency Rings */}
      <svg
        className={clsx(
          "absolute inset-0 w-full h-full pointer-events-none overflow-visible",
          state === "thinking" && "animate-spin"
        )}
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          transform: `scale(${reactiveScale})`,
          transition: "transform 150ms ease-out",
        }}
      >
        {/* Ambient Ring */}
        <circle
          cx="50"
          cy="50"
          r={ringRadius}
          stroke={getRingColor(state)}
          strokeWidth="1.5"
          strokeDasharray={state === "thinking" ? "8 6" : "none"}
          className={clsx(
            state === "idle" && "opacity-40",
            state === "listening" && "opacity-80",
            state === "speaking" && "opacity-90"
          )}
        />

        {/* Audio Frequency Reactive Ring */}
        {(state === "listening" || state === "speaking") && (
          <circle
            cx="50"
            cy="50"
            r={ringRadius + 4 + clampedAudio * 6}
            stroke={getRingColor(state)}
            strokeWidth="1"
            strokeDasharray="4 4"
            className="animate-ping opacity-60 origin-center"
          />
        )}
      </svg>

      {/* Pulsing Core Sphere */}
      <div
        className={clsx(
          "w-3/4 h-3/4 rounded-full relative transition-all duration-300 flex items-center justify-center",
          state === "idle" && "animate-orb-idle",
          state === "listening" && "animate-orb-listening",
          state === "thinking" && "animate-orb-thinking"
        )}
        style={{
          background: getGradient(state),
          boxShadow: getGlow(state),
        }}
      >
        {/* Specular 3D Highlight */}
        <div
          className="absolute inset-x-2 top-1 h-1/3 rounded-full opacity-60 pointer-events-none"
          style={{
            background:
              "linear-gradient(to bottom, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0) 100%)",
          }}
        />

        {/* Inner Core Spark */}
        <div
          className={clsx(
            "w-2 h-2 rounded-full transition-opacity duration-200",
            state === "listening" ? "bg-emerald-200 opacity-90 shadow-sm" : "bg-white opacity-40"
          )}
        />
      </div>

      {/* Screen Reader Announcement */}
      <span className="sr-only">Jarvis Voice Assistant ({state})</span>
    </button>
  );
}

export default Orb;
