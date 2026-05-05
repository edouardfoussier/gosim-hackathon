"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, Radio, Sparkles, Volume2 } from "lucide-react";
import { connect, send, type ServerEvent } from "@/lib/ws";
import { MicRecorder, TtsPlayer } from "@/lib/audio";
import {
  RealtimeClient,
  fetchVoiceCapabilities,
  type RealtimeCapabilities,
  type RealtimeEvent,
} from "@/lib/realtime";
import {
  detectCloseWord,
  isBrowserWakeWordAvailable,
  startPassiveWakeListener,
  type PassiveWakeListenerHandle,
} from "@/lib/wake-listener";
import { VerdictCard } from "@/components/verdict-card";
import { CursorHalo } from "@/components/cursor-halo";

type Variant = "phishing" | "suspicious" | "clear";
type Confidence = "high" | "medium" | "low";

type LogEntry =
  | { kind: "user"; text: string }
  | { kind: "xiexie"; text: string }
  | { kind: "skill"; name: string; result?: string; error?: string }
  | {
      kind: "alert";
      variant: Variant;
      confidence?: Confidence;
      text: string;
    };

function normalizeVariant(level: string | undefined): Variant {
  if (level === "phishing" || level === "danger") return "phishing";
  if (level === "clear") return "clear";
  return "suspicious";
}

function deriveConfidence(
  variant: Variant,
  message: string
): Confidence | undefined {
  const m = message.toLowerCase();
  if (m.includes("high confidence")) return "high";
  if (m.includes("medium confidence")) return "medium";
  if (m.includes("low confidence")) return "low";
  if (variant === "phishing") return "high";
  if (variant === "suspicious") return "low";
  return undefined;
}

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8787/ws";
const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8787";
const TTS_VOICE = process.env.NEXT_PUBLIC_TTS_VOICE;

const LEVEL_BAR_COUNT = 5;

export default function Home() {
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [audioLevel, setAudioLevel] = useState(0);
  const [micError, setMicError] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<RealtimeCapabilities | null>(
    null
  );
  const [continuousActive, setContinuousActive] = useState(false);
  const [continuousStarting, setContinuousStarting] = useState(false);
  const [wakeArmed, setWakeArmed] = useState(false);
  const [wakeSupported, setWakeSupported] = useState(false);
  // Cursor-halo signals fanned out from the backend WS:
  //   speakingFromWs.level — Marin's RMS (also fed straight from the
  //     local realtime client; we listen to the WS too so any future
  //     surface that doesn't own the analyser can still react).
  //   workingActive — silent agent activity (read_screen, analyze_email,
  //     planner think). Drives the pulsing dot + label hint.
  const [haloLevel, setHaloLevel] = useState<number | null>(null);
  const [workingActive, setWorkingActive] = useState(false);
  const [workingLabel, setWorkingLabel] = useState<string | null>(null);
  const workingResetTimerRef = useRef<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);
  const ttsRef = useRef<TtsPlayer | null>(null);
  const levelRafRef = useRef<number | null>(null);
  const realtimeRef = useRef<RealtimeClient | null>(null);
  const wakeRef = useRef<PassiveWakeListenerHandle | null>(null);

  const onEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
      case "transcript":
        setLog((l) => [...l, { kind: "user", text: e.text }]);
        break;
      case "speak":
        setLog((l) => [...l, { kind: "xiexie", text: e.text }]);
        ttsRef.current?.speak(e.text);
        break;
      case "confirm":
        setLog((l) => [...l, { kind: "xiexie", text: e.text }]);
        ttsRef.current?.speak(e.text);
        break;
      case "skill_start":
        setLog((l) => [...l, { kind: "skill", name: e.name }]);
        break;
      case "skill_result":
        setLog((l) => [
          ...l,
          { kind: "skill", name: e.name, result: e.result },
        ]);
        break;
      case "skill_error":
        setLog((l) => [
          ...l,
          { kind: "skill", name: e.name, error: e.error },
        ]);
        break;
      case "alert": {
        const variant = normalizeVariant(e.level);
        setLog((l) => [
          ...l,
          {
            kind: "alert",
            variant,
            confidence: deriveConfidence(variant, e.message),
            text: e.message,
          },
        ]);
        break;
      }
      case "speaking":
        if (e.state === "start") {
          if (typeof e.level === "number") setHaloLevel(e.level);
        } else {
          setHaloLevel(null);
        }
        break;
      case "working":
        if (e.state === "start") {
          if (workingResetTimerRef.current !== null) {
            window.clearTimeout(workingResetTimerRef.current);
            workingResetTimerRef.current = null;
          }
          setWorkingActive(true);
          setWorkingLabel(e.label ?? null);
        } else {
          // Tiny linger so a fast skill (e.g. open_app) still flashes the
          // halo for ~300 ms — otherwise the dot pops in and out and
          // looks like a glitch.
          if (workingResetTimerRef.current !== null) {
            window.clearTimeout(workingResetTimerRef.current);
          }
          workingResetTimerRef.current = window.setTimeout(() => {
            setWorkingActive(false);
            setWorkingLabel(null);
            workingResetTimerRef.current = null;
          }, 280);
        }
        break;
      case "done":
        setThinking(false);
        break;
    }
  }, []);

  useEffect(() => {
    const ws = connect(
      WS_URL,
      onEvent,
      () => setConnected(true),
      () => setConnected(false)
    );
    wsRef.current = ws;
    ttsRef.current = new TtsPlayer(TTS_VOICE);

    void fetchVoiceCapabilities(BACKEND_URL).then(setCapabilities);

    const pollSpeaking = window.setInterval(() => {
      const isSpeaking = ttsRef.current?.isSpeaking() ?? false;
      setSpeaking((prev) => (prev !== isSpeaking ? isSpeaking : prev));
    }, 150);

    return () => {
      window.clearInterval(pollSpeaking);
      ttsRef.current?.cancel();
      recorderRef.current?.cleanup();
      realtimeRef.current?.stop();
      realtimeRef.current = null;
      wakeRef.current?.stop();
      wakeRef.current = null;
      if (levelRafRef.current !== null) {
        cancelAnimationFrame(levelRafRef.current);
      }
      if (workingResetTimerRef.current !== null) {
        window.clearTimeout(workingResetTimerRef.current);
        workingResetTimerRef.current = null;
      }
      ws.close();
    };
  }, [onEvent]);

  // Arm the passive wake listener as soon as we know the backend has a
  // continuous voice path (no key → no point arming). Keeps Marin's
  // mic-claim path snappy: by the time the user says "Xiexie" the
  // recognizer is already up.
  useEffect(() => {
    if (!capabilities?.continuous) return;
    if (continuousActive || continuousStarting) return;
    armWakeListener();
    return () => {
      // Only tear down on unmount: re-arming is handled by stopContinuous.
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capabilities?.continuous]);

  const submitText = useCallback((text: string) => {
    if (!wsRef.current || !text.trim()) return;
    setThinking(true);
    send(wsRef.current, { type: "user_text", text: text.trim() });
    setDraft("");
  }, []);

  const handleRealtimeEvent = useCallback((event: RealtimeEvent) => {
    switch (event.type) {
      case "user_transcript":
        setLog((l) => [...l, { kind: "user", text: event.text }]);
        // Close-word detection runs on the same transcript stream the
        // model already sees — no second recognizer required. When the
        // user politely says "thank you" / "merci" / "xiexie" we close
        // the realtime channel and re-arm the passive wake listener.
        if (detectCloseWord(event.text)) {
          stopContinuousRef.current();
        }
        return;
      case "assistant_transcript":
        // Realtime streams partial deltas first then a final ``done`` event.
        // We only commit the final transcript so we don't double-render
        // (audio playback already gives Margaret the spoken reply).
        if (event.partial) return;
        setLog((l) => [...l, { kind: "xiexie", text: event.text }]);
        return;
      case "tool_start":
        setLog((l) => [...l, { kind: "skill", name: event.name }]);
        return;
      case "tool_result":
        setLog((l) => [
          ...l,
          {
            kind: "skill",
            name: event.name,
            ...(event.ok ? { result: event.result } : { error: event.result }),
          },
        ]);
        return;
      case "model_audio_started":
        setSpeaking(true);
        return;
      case "model_audio_stopped":
        setSpeaking(false);
        return;
      case "error":
        setMicError(event.message);
        return;
    }
  }, []);

  // Forward declarations so the wake-listener can call ``startContinuous``
  // before it's defined below. We assign through these refs once the real
  // closures exist — keeps the dependency graph readable.
  const startContinuousRef = useRef<() => Promise<void>>(async () => {});
  const stopContinuousRef = useRef<() => void>(() => {});

  const armWakeListener = useCallback(() => {
    if (wakeRef.current) return; // already armed
    if (!isBrowserWakeWordAvailable()) {
      setWakeSupported(false);
      return;
    }
    setWakeSupported(true);
    try {
      const handle = startPassiveWakeListener({
        onWake: (variant) => {
          // Wake fired — stop the recognizer immediately so the realtime
          // session can claim the mic via getUserMedia without contention.
          handle.stop();
          wakeRef.current = null;
          setWakeArmed(false);
          // Surface the wake in the chat so Margaret sees the trigger.
          setLog((l) => [
            ...l,
            { kind: "skill", name: "wake-word", result: `heard "${variant}"` },
          ]);
          void startContinuousRef.current();
        },
        onError: (msg) => setMicError(msg),
        onStateChange: (listening) => setWakeArmed(listening),
      });
      wakeRef.current = handle;
    } catch (err) {
      // Browser doesn't actually expose the API — flip the flag and move on.
      setWakeSupported(false);
    }
  }, []);

  const stopContinuous = useCallback(() => {
    realtimeRef.current?.stop();
    realtimeRef.current = null;
    setContinuousActive(false);
    setSpeaking(false);
    // Re-arm the wake listener so the next "Xiexie" reopens the channel.
    armWakeListener();
  }, [armWakeListener]);

  const startContinuous = useCallback(async () => {
    if (continuousStarting || continuousActive) return;
    setMicError(null);
    setContinuousStarting(true);
    // Cancel any local TTS so the browser SpeechSynthesis voice doesn't
    // overlap with Marin's voice coming back over WebRTC.
    ttsRef.current?.cancel();
    // Make sure the passive listener has released the mic (wake-fire stops
    // it automatically; this is the manual-click path).
    wakeRef.current?.stop();
    wakeRef.current = null;
    setWakeArmed(false);
    const client = new RealtimeClient();
    try {
      await client.start({ backendUrl: BACKEND_URL, onEvent: handleRealtimeEvent });
      realtimeRef.current = client;
      setContinuousActive(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "could not open voice channel";
      setMicError(message);
      client.stop();
      // Re-arm the listener since we never opened the realtime mic.
      armWakeListener();
    } finally {
      setContinuousStarting(false);
    }
  }, [continuousStarting, continuousActive, handleRealtimeEvent, armWakeListener]);

  // Wire the ref-based forward declarations so the wake-listener closure
  // (defined first) can call into the latest ``startContinuous`` /
  // ``stopContinuous`` without re-arming the listener every render.
  useEffect(() => {
    startContinuousRef.current = startContinuous;
    stopContinuousRef.current = stopContinuous;
  }, [startContinuous, stopContinuous]);

  const tickLevel = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || !recorder.isRecording()) {
      setAudioLevel(0);
      levelRafRef.current = null;
      return;
    }
    setAudioLevel(recorder.audioLevel());
    levelRafRef.current = requestAnimationFrame(tickLevel);
  }, []);

  const startRecording = useCallback(async () => {
    setMicError(null);
    // Cancel any in-flight TTS so Margaret isn't talked over by Xiexie.
    ttsRef.current?.cancel();
    const recorder = new MicRecorder();
    try {
      await recorder.start();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "could not access microphone";
      setMicError(message);
      recorder.cleanup();
      return;
    }
    recorderRef.current = recorder;
    setRecording(true);
    levelRafRef.current = requestAnimationFrame(tickLevel);
  }, [tickLevel]);

  const stopRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    setRecording(false);
    if (levelRafRef.current !== null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    setAudioLevel(0);

    let blob: Blob;
    try {
      blob = await recorder.stop();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "could not stop recording";
      setMicError(message);
      recorder.cleanup();
      recorderRef.current = null;
      return;
    }
    recorder.cleanup();
    recorderRef.current = null;

    if (blob.size === 0) {
      setMicError("no audio captured — try again a bit louder");
      return;
    }

    setTranscribing(true);
    try {
      const form = new FormData();
      const filename = blob.type.includes("ogg") ? "audio.ogg" : "audio.webm";
      form.append("audio", blob, filename);
      const res = await fetch(`${BACKEND_URL}/transcribe`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(`transcribe failed (${res.status})`);
      const data = (await res.json()) as { text?: string };
      const text = (data.text ?? "").trim();
      if (text) {
        submitText(text);
      } else {
        setMicError("didn't catch that — try again?");
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "transcription failed";
      setMicError(message);
    } finally {
      setTranscribing(false);
    }
  }, [submitText]);

  const continuousMode = capabilities?.continuous ?? false;

  const onMicClick = useCallback(() => {
    if (continuousMode) {
      if (continuousActive) {
        stopContinuous();
      } else {
        void startContinuous();
      }
      return;
    }
    if (recording) {
      void stopRecording();
    } else {
      void startRecording();
    }
  }, [
    continuousMode,
    continuousActive,
    recording,
    startContinuous,
    stopContinuous,
    startRecording,
    stopRecording,
  ]);

  const micBusy = continuousStarting || transcribing || thinking;
  const micActive = continuousMode ? continuousActive : recording;

  return (
    <main className="min-h-screen flex flex-col items-center px-6 py-10">
      {/* Cursor-following halo: speaks when Marin produces audio, pulses
          when the agent is silently working (vision call, scam analysis,
          etc.). Mirrors the native PyQt6 SoundwaveOverlay in the .app
          build. */}
      <CursorHalo
        speaking={speaking}
        level={haloLevel}
        working={workingActive}
        label={workingLabel}
      />

      {/* Header */}
      <header className="w-full max-w-3xl flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-ember-500 flex items-center justify-center text-white font-semibold">
            谢
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Xiexie</h1>
            <p className="text-sm text-ember-700/70">
              your computer companion
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {speaking && (
            <span className="flex items-center gap-1 text-ember-700">
              <Volume2 size={14} />
              <span>speaking…</span>
            </span>
          )}
          {!continuousActive && wakeArmed && (
            <span
              className="flex items-center gap-1 text-ember-700/80"
              title="Say 'Xiexie' to start a conversation. Say 'thank you' to end it."
            >
              <span className="relative inline-flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ember-400 opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-ember-500" />
              </span>
              <span className="text-xs">listening for &ldquo;Xiexie&rdquo; or &ldquo;computer&rdquo;…</span>
            </span>
          )}
          <div className="flex items-center gap-2">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                connected ? "bg-emerald-500" : "bg-zinc-300"
              }`}
            />
            <span className="text-zinc-600">
              {connected ? "connected" : "offline"}
            </span>
          </div>
        </div>
      </header>

      {/* Conversation */}
      <section className="w-full max-w-3xl flex-1 flex flex-col gap-3 mb-8 min-h-[40vh]">
        {log.length === 0 && <EmptyState />}
        {log.map((e, i) => (
          <Bubble key={i} entry={e} submitText={submitText} />
        ))}
      </section>

      {/* Input */}
      <section className="w-full max-w-3xl">
        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            submitText(draft);
          }}
          className="flex items-center gap-3 bg-white rounded-2xl shadow-sm border border-ember-100 p-2"
        >
          <button
            type="button"
            onClick={onMicClick}
            disabled={micBusy}
            className={`relative w-12 h-12 rounded-full flex items-center justify-center text-white transition disabled:opacity-50 ${
              micActive
                ? "bg-ember-500 pulse-ring"
                : "bg-ember-300 hover:bg-ember-400"
            }`}
            aria-label={
              continuousMode
                ? continuousActive
                  ? "end continuous conversation"
                  : "start continuous conversation"
                : recording
                ? "stop listening"
                : "start listening"
            }
            title={
              continuousMode
                ? continuousActive
                  ? "End continuous conversation"
                  : "Start continuous conversation"
                : recording
                ? "Stop recording"
                : "Click to record"
            }
          >
            {continuousMode ? (
              micActive ? (
                <MicOff size={22} />
              ) : (
                <Radio size={22} />
              )
            ) : micActive ? (
              <MicOff size={22} />
            ) : (
              <Mic size={22} />
            )}
          </button>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder='Try: "open Mail" or "find my last EDF bill"'
            className="flex-1 bg-transparent outline-none text-lg px-2"
          />
          <button
            type="submit"
            className="px-4 py-2 rounded-xl bg-zinc-900 text-white text-base hover:bg-zinc-800 disabled:opacity-40"
            disabled={!connected || !draft.trim()}
          >
            Send
          </button>
        </form>
        <LevelMeter level={audioLevel} active={recording} />
        <p className="mt-2 text-xs text-zinc-500 text-center min-h-[1rem]">
          {micError ? (
            <span className="text-rose-600">⚠ {micError}</span>
          ) : continuousStarting ? (
            "opening voice channel…"
          ) : continuousMode && continuousActive ? (
            <>
              continuous conversation — speak any time, click the mic to end
            </>
          ) : continuousMode ? (
            <>
              Continuous voice via <code>gpt-realtime</code>{capabilities?.voice
                ? ` (${capabilities.voice})`
                : ""}
              {" "}— click the mic to start.
            </>
          ) : transcribing ? (
            "transcribing…"
          ) : recording ? (
            "listening — click again to send"
          ) : thinking ? (
            "thinking…"
          ) : (
            <>
              Click-to-record STT through <code>/transcribe</code>. Set{" "}
              <code>OPENAI_API_KEY</code> for continuous voice.
            </>
          )}
        </p>
      </section>
    </main>
  );
}

function LevelMeter({ level, active }: { level: number; active: boolean }) {
  const visible = active || level > 0.01;
  return (
    <div
      className="mt-3 flex items-end justify-center gap-1 h-6"
      aria-hidden="true"
    >
      {Array.from({ length: LEVEL_BAR_COUNT }).map((_, i) => {
        // Each bar reaches its full height at a different level threshold so
        // the meter "fills" left-to-right rather than pulsing in unison.
        const threshold = (i + 1) / (LEVEL_BAR_COUNT + 1);
        const reach = Math.max(0, level - threshold * 0.4);
        const scale = visible ? Math.min(1, reach * 3 + 0.05) : 0;
        return (
          <span
            key={i}
            className="w-1.5 h-6 rounded-full bg-ember-500 origin-bottom transition-transform duration-75"
            style={{
              transform: `scaleY(${scale.toFixed(3)})`,
              opacity: visible ? 0.85 : 0.15,
            }}
          />
        );
      })}
    </div>
  );
}

function EmptyState() {
  const samples = [
    "What's on my plate today?",
    "Find my last EDF bill",
    "Read me the email from Aetna",
    "Set a reminder for 3:30pm to leave for the airport",
  ];
  return (
    <div className="rounded-2xl border border-ember-100 bg-white p-6">
      <div className="flex items-center gap-2 text-ember-700 mb-3">
        <Sparkles size={18} />
        <span className="text-base font-medium">Try saying…</span>
      </div>
      <ul className="space-y-2 text-zinc-700">
        {samples.map((s) => (
          <li key={s} className="text-base">
            “{s}”
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm text-zinc-500">
        Xiexie reads your wiki ( <code>data/wiki/</code> ), picks a skill, asks
        before doing anything big, and learns a little after every conversation.
      </p>
    </div>
  );
}

type BubbleProps = {
  entry: LogEntry;
  submitText: (text: string) => void;
};

function Bubble({ entry, submitText }: BubbleProps) {
  if (entry.kind === "user") {
    return (
      <div className="self-end max-w-[85%] rounded-2xl rounded-tr-sm bg-ember-500 text-white px-4 py-2 text-base">
        {entry.text}
      </div>
    );
  }
  if (entry.kind === "xiexie") {
    return (
      <div className="self-start max-w-[85%] rounded-2xl rounded-tl-sm bg-white border border-ember-100 px-4 py-2 text-base">
        {entry.text}
      </div>
    );
  }
  if (entry.kind === "alert") {
    // The Verdict Card is rendered at 80% on screen so the 760px design
    // sits comfortably inside the 768px max-w-3xl conversation column.
    const SCALE = 0.8;
    return (
      <div className="self-center my-4">
        <VerdictCard
          variant={entry.variant}
          confidence={entry.confidence}
          speakAloud={entry.text}
          scale={SCALE}
          onTellFamily={() => submitText("Tell Lisa about this")}
          onArchive={() => submitText("Archive that email")}
          onShowDetails={() =>
            submitText("Show me the technical details")
          }
        />
      </div>
    );
  }
  return (
    <div className="self-start max-w-[85%] text-sm text-zinc-500 italic px-2">
      {entry.error ? (
        <>
          <code>{entry.name}</code> · error: {entry.error}
        </>
      ) : entry.result ? (
        <>
          <code>{entry.name}</code> → {entry.result}
        </>
      ) : (
        <>
          <code>{entry.name}</code> running…
        </>
      )}
    </div>
  );
}
