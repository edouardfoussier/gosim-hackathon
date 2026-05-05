"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, Sparkles, Volume2 } from "lucide-react";
import { connect, send, type ServerEvent } from "@/lib/ws";
import { MicRecorder, TtsPlayer } from "@/lib/audio";

type LogEntry =
  | { kind: "user"; text: string }
  | { kind: "xiexie"; text: string }
  | { kind: "skill"; name: string; result?: string; error?: string }
  | {
      kind: "alert";
      level: "phishing" | "suspicious" | "clear" | "warning" | "danger";
      text: string;
    };

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

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MicRecorder | null>(null);
  const ttsRef = useRef<TtsPlayer | null>(null);
  const levelRafRef = useRef<number | null>(null);

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
      case "alert":
        setLog((l) => [
          ...l,
          {
            kind: "alert",
            level: e.level ?? "suspicious",
            text: e.message,
          },
        ]);
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

    const pollSpeaking = window.setInterval(() => {
      const isSpeaking = ttsRef.current?.isSpeaking() ?? false;
      setSpeaking((prev) => (prev !== isSpeaking ? isSpeaking : prev));
    }, 150);

    return () => {
      window.clearInterval(pollSpeaking);
      ttsRef.current?.cancel();
      recorderRef.current?.cleanup();
      if (levelRafRef.current !== null) {
        cancelAnimationFrame(levelRafRef.current);
      }
      ws.close();
    };
  }, [onEvent]);

  const submitText = useCallback((text: string) => {
    if (!wsRef.current || !text.trim()) return;
    setThinking(true);
    send(wsRef.current, { type: "user_text", text: text.trim() });
    setDraft("");
  }, []);

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

  const onMicClick = useCallback(() => {
    if (recording) {
      void stopRecording();
    } else {
      void startRecording();
    }
  }, [recording, startRecording, stopRecording]);

  const micBusy = transcribing || thinking;

  return (
    <main className="min-h-screen flex flex-col items-center px-6 py-10">
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
          <Bubble key={i} entry={e} />
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
              recording
                ? "bg-ember-500 pulse-ring"
                : "bg-ember-300 hover:bg-ember-400"
            }`}
            aria-label={recording ? "stop listening" : "start listening"}
          >
            {recording ? <MicOff size={22} /> : <Mic size={22} />}
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
          ) : transcribing ? (
            "transcribing…"
          ) : recording ? (
            "listening — click again to send"
          ) : thinking ? (
            "thinking…"
          ) : (
            <>
              Hot-mic STT runs through <code>/transcribe</code>; replies are
              spoken locally via the browser.
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

function Bubble({ entry }: { entry: LogEntry }) {
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
    const phishing = entry.level === "phishing" || entry.level === "danger";
    const safe = entry.level === "clear";
    let cls: string;
    let label: string;
    if (phishing) {
      cls = "border-rose-300 bg-rose-50 text-rose-800";
      label = "phishing alert";
    } else if (safe) {
      cls = "border-emerald-300 bg-emerald-50 text-emerald-800";
      label = "all clear";
    } else {
      cls = "border-amber-300 bg-amber-50 text-amber-900";
      label = "looks suspicious";
    }
    return (
      <div
        className={`self-stretch rounded-xl border px-4 py-2 text-sm ${cls}`}
      >
        ⚠️ {label}: {entry.text}
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
