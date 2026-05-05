"use client";

import { useEffect, useRef, useState } from "react";

/**
 * CursorHalo — an in-browser, cursor-following indicator showing two
 * states of Xiexie agent activity (Clicky-parity in browser; the native
 * PyQt6 SoundwaveOverlay shows the same thing in the .app build):
 *
 *   - **speaking**: Marin is producing audio (driven by Realtime RMS).
 *     We render five animated vertical bars whose amplitude follows
 *     ``level`` (0..1). Warm ember accent.
 *
 *   - **working**: a silent skill is running (read_screen / analyze_email
 *     / open_app / …). We render a soft pulsing dot + a short text hint
 *     (``label``) so Margaret sees Xiexie *thinking*, not frozen.
 *
 * Both states can co-exist (the agent narrates a result while another
 * skill kicks off in parallel); the bars take precedence visually but
 * the working hint stays readable underneath.
 *
 * Positioning: fixed-overlay div tracking ``mousemove``. We offset the
 * halo ~22 px down/right of the cursor so it never sits *exactly* on
 * the click target — same offset Clicky uses. ``pointerEvents: none``
 * so it never swallows clicks.
 */

export type CursorHaloProps = {
  speaking: boolean;
  /** Marin RMS level 0..1; null when no live audio analyser. */
  level?: number | null;
  working: boolean;
  /** Short status hint, e.g. "looking at your screen". */
  label?: string | null;
};

const BAR_COUNT = 5;
const HALO_OFFSET_X = 18;
const HALO_OFFSET_Y = 18;

export function CursorHalo({
  speaking,
  level,
  working,
  label,
}: CursorHaloProps) {
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: -200, y: -200 });
  // Smooth the level so bars don't jitter on every 100 ms tick from the
  // analyser. We lerp toward the target at ~70% per frame (~16 ms).
  const smoothedRef = useRef(0);
  const [smoothed, setSmoothed] = useState(0);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      setPos({ x: e.clientX, y: e.clientY });
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const target = speaking ? Math.max(0.15, level ?? 0.3) : 0;
      const next = smoothedRef.current + (target - smoothedRef.current) * 0.25;
      smoothedRef.current = next;
      setSmoothed(next);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking, level]);

  const visible = speaking || working;
  if (!visible) return null;

  // Per-bar phase so heights stagger like a real soundwave.
  const bars = Array.from({ length: BAR_COUNT }, (_, i) => {
    // Procedural sine fallback when level is missing or near zero —
    // gives the indicator life even before Marin speaks the first word.
    const phase = i / BAR_COUNT + (Date.now() / 220) % 1;
    const sine = (Math.sin(phase * Math.PI * 2) + 1) / 2; // 0..1
    const amp = speaking ? smoothed * (0.5 + 0.5 * sine) : 0;
    const min = 4;
    const max = 26;
    const h = min + Math.max(0, Math.min(1, amp)) * (max - min);
    return h;
  });

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed z-[60]"
      style={{
        left: pos.x + HALO_OFFSET_X,
        top: pos.y + HALO_OFFSET_Y,
        transition: "opacity 180ms ease",
        opacity: visible ? 1 : 0,
      }}
    >
      <div
        className="flex items-center gap-2 rounded-full px-3 py-2 backdrop-blur-sm"
        style={{
          background: "rgba(245, 235, 215, 0.85)",
          border: "1px solid rgba(176, 88, 38, 0.25)",
          boxShadow: "0 6px 18px rgba(176, 88, 38, 0.18)",
        }}
      >
        {speaking ? (
          <div className="flex items-end gap-[3px]" aria-label="Xiexie speaking">
            {bars.map((h, i) => (
              <span
                key={i}
                style={{
                  width: 3,
                  height: h,
                  borderRadius: 2,
                  background: "linear-gradient(180deg, #B05826, #D87A38)",
                  transition: "height 70ms linear",
                }}
              />
            ))}
          </div>
        ) : null}

        {working && !speaking ? (
          <div className="flex items-center gap-2" aria-label="Xiexie working">
            <span
              className="block h-2.5 w-2.5 rounded-full"
              style={{
                background: "#B05826",
                animation: "xiexie-pulse 1.1s ease-in-out infinite",
              }}
            />
            <span
              className="text-[12px] font-medium leading-none"
              style={{
                color: "#5C2E12",
                fontFamily:
                  "var(--font-inter), Inter, ui-sans-serif, system-ui, sans-serif",
              }}
            >
              {label ?? "thinking"}
            </span>
          </div>
        ) : null}

        {working && speaking && label ? (
          <span
            className="text-[11px] leading-none opacity-70"
            style={{
              color: "#5C2E12",
              fontFamily:
                "var(--font-inter), Inter, ui-sans-serif, system-ui, sans-serif",
            }}
          >
            {label}
          </span>
        ) : null}
      </div>
      <style jsx>{`
        @keyframes xiexie-pulse {
          0%,
          100% {
            transform: scale(1);
            opacity: 0.55;
          }
          50% {
            transform: scale(1.35);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}
