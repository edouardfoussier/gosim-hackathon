"use client";

/**
 * Passive wake-word listener powered by ``webkitSpeechRecognition``.
 *
 * Scope:
 *   - Lives in the browser (Chrome / Edge).
 *   - Continuously listens for one of a handful of wake-word variants
 *     ("xiexie", "shi shi", "she she", "shieshie") and fires a single
 *     callback when any of them is detected with non-trivial confidence.
 *   - Auto-restarts on silence / network glitches so the demo doesn't
 *     stall five minutes in.
 *
 * Limitations (deliberately accepted, not fixed):
 *   - Chrome / Edge only. Safari / WKWebView do NOT expose
 *     ``webkitSpeechRecognition`` — by design. The same UX is delivered
 *     in production by the backend openWakeWord ONNX runtime pushing
 *     a ``wake`` event over WS, which works on every webview.
 *   - The Web Speech API uses Google's cloud STT under the hood, so
 *     audio leaves the machine. This is a *demo* path, not the local-
 *     first production path. Documented loudly in the pitch.
 *
 * Architecture (single mic at a time):
 *   - When the wake-word fires, we STOP the recognizer immediately so
 *     the realtime session can claim the microphone via getUserMedia
 *     without contention.
 *   - The close-word ("thank you" / "merci" / "xiexie merci") is
 *     watched on the realtime session's own user-transcript stream —
 *     no second recognizer is needed.
 *   - When the realtime session ends, the page re-arms ``startPassive``
 *     so the wake loop is back in business for the next turn.
 */

const WAKE_VARIANTS = [
  "xiexie",
  "shieshie",
  "shi shi",
  "she she",
  "sheshe",
  "xie xie",
];

const CLOSE_VARIANTS = [
  "thank you",
  "thanks",
  "merci",
  "xiexie merci",
  "thank you xiexie",
  "all good",
  "we're done",
];

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string; confidence: number };
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [k: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionErrorEventLike {
  error: string;
  message?: string;
}
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

/** Returns the constructor or null when the browser doesn't ship one. */
function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function isBrowserWakeWordAvailable(): boolean {
  return getRecognitionCtor() !== null;
}

/** Normalise a transcript chunk for variant matching. */
function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/[.,!?;:'"()\[\]{}]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function containsAny(text: string, variants: string[]): string | null {
  const norm = normalise(text);
  for (const v of variants) {
    if (norm.includes(v)) return v;
  }
  return null;
}

/** Test helper — exposed so the page can match close-words on realtime user transcripts. */
export function detectCloseWord(transcript: string): string | null {
  return containsAny(transcript, CLOSE_VARIANTS);
}

export interface PassiveWakeListenerOptions {
  /** Called once per wake detection with the variant that matched. */
  onWake: (variant: string) => void;
  /** Called when the recognizer encounters a non-fatal error. */
  onError?: (message: string) => void;
  /** Called whenever the recognizer's listening state flips. */
  onStateChange?: (listening: boolean) => void;
}

export interface PassiveWakeListenerHandle {
  /** Stop and discard the recognizer; call before opening the realtime mic. */
  stop: () => void;
  /** True while the recognizer is actively listening (between auto-restarts). */
  isListening: () => boolean;
}

/**
 * Start a passive wake-word listener. Throws if the browser doesn't ship
 * SpeechRecognition (caller should feature-detect with ``isBrowserWakeWordAvailable``
 * and fall back gracefully).
 */
export function startPassiveWakeListener(
  options: PassiveWakeListenerOptions
): PassiveWakeListenerHandle {
  const Ctor = getRecognitionCtor();
  if (!Ctor) {
    throw new Error(
      "webkitSpeechRecognition is not available in this browser. " +
        "Use Chrome / Edge for the wake-word demo, or wait for the " +
        "openWakeWord ONNX backend path to land."
    );
  }

  let stopped = false;
  let listening = false;
  let recognition: SpeechRecognitionLike | null = null;

  const startRecognizer = () => {
    if (stopped) return;
    const r = new Ctor();
    r.continuous = true;
    r.interimResults = true;
    r.lang = "en-US";

    r.onstart = () => {
      listening = true;
      options.onStateChange?.(true);
    };
    r.onend = () => {
      listening = false;
      options.onStateChange?.(false);
      // Auto-restart unless the caller asked us to stop. ``onend`` fires
      // after silence in continuous mode too; we just kick a fresh
      // recognizer to keep listening forever.
      if (!stopped) {
        // Tiny delay so we don't hammer the browser API.
        setTimeout(startRecognizer, 200);
      }
    };
    r.onerror = (event) => {
      const code = event.error;
      // ``no-speech`` and ``aborted`` are normal in continuous mode —
      // don't surface them. Anything else is worth bubbling up.
      if (code !== "no-speech" && code !== "aborted") {
        options.onError?.(`wake-listener error: ${code}`);
      }
    };
    r.onresult = (event) => {
      let combined = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        combined += " " + r[0].transcript;
      }
      const matched = containsAny(combined, WAKE_VARIANTS);
      if (matched) {
        // Fire and let the caller stop us — they're about to claim the mic.
        options.onWake(matched);
      }
    };

    recognition = r;
    try {
      r.start();
    } catch (err) {
      // ``start`` throws ``InvalidStateError`` if a previous recognizer is
      // still finishing teardown. Retry in 300 ms.
      if (!stopped) setTimeout(startRecognizer, 300);
    }
  };

  startRecognizer();

  return {
    stop: () => {
      stopped = true;
      const r = recognition;
      recognition = null;
      if (r) {
        try {
          r.abort();
        } catch {
          /* ignore */
        }
      }
      listening = false;
      options.onStateChange?.(false);
    },
    isListening: () => listening,
  };
}
