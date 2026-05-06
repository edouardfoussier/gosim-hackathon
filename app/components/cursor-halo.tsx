"use client";

import { useEffect, useRef, useState } from "react";

/**
 * CursorHalo — cursor-following indicator for Xiexie's conversation
 * loop. Sized **2× larger than Clicky's** because Margaret (our senior
 * persona) needs to see at-a-glance status from across the room, not
 * lean in to find a 12-pixel dot.
 *
 * Four mutually-exclusive modes, ordered by precedence:
 *
 *   - **hidden**: continuous mode is off. The agent is asleep; we show
 *     nothing so the cursor stays clean. Triggered by the close-word
 *     ("thank you") or by the user clicking the mic to terminate.
 *
 *   - **idle** (continuousActive && !speaking && !working): a single
 *     pulsing ember dot ringed by a soft halo. Says "I'm listening,
 *     speak any time" without being noisy. This is the default state
 *     while the conversation loop is open.
 *
 *   - **working** (skill running silently): an 8-dot orbital loader
 *     spinning around an empty centre + a short label hint
 *     ("looking at your screen"). Same family as Clicky's spinner
 *     but with a wider gap so the rotation reads at distance.
 *
 *   - **speaking** (Marin is producing audio): five vertical bars
 *     driven by the live RMS level (procedural sine fallback when
 *     ``level`` is null). Takes precedence over ``working`` so that
 *     mid-sentence skill kicks don't downgrade the visual.
 *
 * The halo follows ``mousemove`` with a 24 px down-right offset so it
 * never sits on the click target. ``pointerEvents: none`` ensures it
 * never swallows a click. All visuals stay inside one rounded-pill
 * container so the surface itself is identifiable as a single agent
 * indicator (not three different things sliding around).
 */

export type CursorHaloMode = "hidden" | "idle" | "working" | "speaking";

export type CursorHaloProps = {
  /** Continuous mode = the conversation loop is open. Halo lives or
   * dies on this flag — it's the master gate so "thank you" can wipe
   * the indicator in one place. */
  continuousActive: boolean;
  /** Marin is producing audio right now (analyser RMS > silence). */
  speaking: boolean;
  /** Latest RMS level 0..1 for bar amplitude. Null = procedural sine. */
  level?: number | null;
  /** A skill is running in the background (read_screen, analyze_email, …). */
  working: boolean;
  /** Short status hint ("looking at your screen") rendered in working mode. */
  label?: string | null;
};

// ── 2× Clicky-equivalent sizes (Margaret-readable) ───────────────────
const HALO_OFFSET_X = 24;
const HALO_OFFSET_Y = 24;

const BAR_COUNT = 5;
const BAR_WIDTH = 6;          // was 3 in v1
const BAR_GAP = 4;            // was ~3
const BAR_MIN_H = 8;          // was 4
const BAR_MAX_H = 50;         // was 26

const IDLE_DOT = 22;          // was 10
const IDLE_HALO = 56;         // was 28

const SPINNER_SIZE = 56;      // was ~28
const SPINNER_DOT = 10;       // was 5
const SPINNER_DOT_COUNT = 8;

const LABEL_FONT = 16;        // was 12

const PILL_PAD_X = 18;        // was 12 (10/12px)
const PILL_PAD_Y = 14;        // was ~8

// ── palette ──────────────────────────────────────────────────────────
const EMBER_GRADIENT = "linear-gradient(180deg, #B05826, #D87A38)";
const EMBER_SOLID = "#B05826";
const INK = "#5C2E12";
const CREAM_BG = "rgba(245, 235, 215, 0.92)";
const EMBER_BORDER = "rgba(176, 88, 38, 0.28)";
const EMBER_SHADOW = "0 8px 22px rgba(176, 88, 38, 0.22)";

function pickMode(
  continuousActive: boolean,
  speaking: boolean,
  working: boolean,
): CursorHaloMode {
  if (!continuousActive) return "hidden";
  if (speaking) return "speaking";
  if (working) return "working";
  return "idle";
}

export function CursorHalo({
  continuousActive,
  speaking,
  level,
  working,
  label,
}: CursorHaloProps) {
  const [pos, setPos] = useState<{ x: number; y: number }>({
    x: -400,
    y: -400,
  });
  // Smoothed RMS so the bars don't jitter on every 100 ms tick.
  const smoothedRef = useRef(0);
  const [smoothed, setSmoothed] = useState(0);
  // Continuous tick counter so the spinner + procedural sine animate
  // even when the React tree isn't otherwise re-rendering.
  const [tickMs, setTickMs] = useState(0);

  // Track cursor.
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      setPos({ x: e.clientX, y: e.clientY });
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  // Single rAF loop drives bar smoothing + spinner phase + sine
  // fallback. Cheap (one update per frame, ~16 ms).
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const tick = () => {
      const now = performance.now();
      setTickMs(now - start);
      const target = speaking ? Math.max(0.15, level ?? 0.3) : 0;
      const next = smoothedRef.current + (target - smoothedRef.current) * 0.25;
      smoothedRef.current = next;
      setSmoothed(next);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking, level]);

  const mode = pickMode(continuousActive, speaking, working);

  if (mode === "hidden") return null;

  // Per-bar phase staggered so the heights look like a real waveform
  // and not a chorus line.
  const bars = Array.from({ length: BAR_COUNT }, (_, i) => {
    const phase = (i / BAR_COUNT + (tickMs / 220) % 1) % 1;
    const sine = (Math.sin(phase * Math.PI * 2) + 1) / 2; // 0..1
    const amp = smoothed * (0.45 + 0.55 * sine);
    return BAR_MIN_H + Math.max(0, Math.min(1, amp)) * (BAR_MAX_H - BAR_MIN_H);
  });

  // Spinner: SPINNER_DOT_COUNT dots evenly spaced on a circle, each one's
  // opacity shifted by its phase offset so the "lead" dot rotates.
  const spinnerCenter = SPINNER_SIZE / 2;
  const spinnerRadius = SPINNER_SIZE / 2 - SPINNER_DOT / 2 - 2;
  const spinnerLead = (tickMs / 90) % SPINNER_DOT_COUNT;
  const spinnerDots = Array.from({ length: SPINNER_DOT_COUNT }, (_, i) => {
    const angle = (i / SPINNER_DOT_COUNT) * Math.PI * 2 - Math.PI / 2;
    const dx = Math.cos(angle) * spinnerRadius;
    const dy = Math.sin(angle) * spinnerRadius;
    // Distance (in dot units) from the rotating lead, wrapped.
    const distFromLead = Math.min(
      Math.abs(i - spinnerLead),
      SPINNER_DOT_COUNT - Math.abs(i - spinnerLead),
    );
    // Lead dot is full opacity; opacity falls off with distance.
    const opacity = Math.max(0.18, 1 - distFromLead / (SPINNER_DOT_COUNT / 2));
    return { dx, dy, opacity };
  });

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed z-[60]"
      style={{
        left: pos.x + HALO_OFFSET_X,
        top: pos.y + HALO_OFFSET_Y,
        transition: "opacity 200ms ease",
      }}
    >
      <div
        className="flex items-center gap-3 rounded-full backdrop-blur-md"
        style={{
          background: CREAM_BG,
          border: `1.5px solid ${EMBER_BORDER}`,
          boxShadow: EMBER_SHADOW,
          padding: `${PILL_PAD_Y}px ${PILL_PAD_X}px`,
        }}
      >
        {/* ── IDLE: pulsing dot ─────────────────────────────────── */}
        {mode === "idle" ? (
          <div
            className="relative flex items-center justify-center"
            style={{ width: IDLE_HALO, height: IDLE_HALO }}
            aria-label="Xiexie listening"
          >
            <span
              className="absolute rounded-full"
              style={{
                width: IDLE_HALO,
                height: IDLE_HALO,
                border: `2px solid ${EMBER_SOLID}`,
                opacity: 0,
                animation: "xiexie-halo-pulse 1.8s ease-out infinite",
              }}
            />
            <span
              className="absolute rounded-full"
              style={{
                width: IDLE_HALO,
                height: IDLE_HALO,
                border: `2px solid ${EMBER_SOLID}`,
                opacity: 0,
                animation: "xiexie-halo-pulse 1.8s ease-out infinite",
                animationDelay: "0.6s",
              }}
            />
            <span
              className="absolute rounded-full"
              style={{
                width: IDLE_DOT,
                height: IDLE_DOT,
                background: EMBER_GRADIENT,
                boxShadow: `0 0 0 4px rgba(176, 88, 38, 0.18)`,
              }}
            />
          </div>
        ) : null}

        {/* ── WORKING: 8-dot orbital spinner + label ─────────────── */}
        {mode === "working" ? (
          <>
            <div
              className="relative"
              style={{ width: SPINNER_SIZE, height: SPINNER_SIZE }}
              aria-label="Xiexie working"
            >
              {spinnerDots.map((d, i) => (
                <span
                  key={i}
                  className="absolute rounded-full"
                  style={{
                    width: SPINNER_DOT,
                    height: SPINNER_DOT,
                    left: spinnerCenter + d.dx - SPINNER_DOT / 2,
                    top: spinnerCenter + d.dy - SPINNER_DOT / 2,
                    background: EMBER_SOLID,
                    opacity: d.opacity,
                  }}
                />
              ))}
            </div>
            <span
              style={{
                color: INK,
                fontFamily:
                  "var(--font-inter), Inter, ui-sans-serif, system-ui, sans-serif",
                fontSize: LABEL_FONT,
                fontWeight: 600,
                lineHeight: 1.15,
                whiteSpace: "nowrap",
              }}
            >
              {label ?? "thinking"}
            </span>
          </>
        ) : null}

        {/* ── SPEAKING: live-RMS bars ────────────────────────────── */}
        {mode === "speaking" ? (
          <div
            className="flex items-end"
            style={{ gap: BAR_GAP, height: BAR_MAX_H }}
            aria-label="Xiexie speaking"
          >
            {bars.map((h, i) => (
              <span
                key={i}
                style={{
                  width: BAR_WIDTH,
                  height: h,
                  borderRadius: BAR_WIDTH / 2,
                  background: EMBER_GRADIENT,
                  transition: "height 70ms linear",
                }}
              />
            ))}
          </div>
        ) : null}
      </div>

      {/* ``style jsx global`` so the keyframe name remains unscoped and
          the inline ``animation: xiexie-halo-pulse …`` references can
          actually find it (styled-jsx rewrites scoped names but inline
          styles aren't aware of the rewrite). */}
      <style jsx global>{`
        @keyframes xiexie-halo-pulse {
          0% {
            transform: scale(0.55);
            opacity: 0.85;
          }
          100% {
            transform: scale(1.35);
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
}
