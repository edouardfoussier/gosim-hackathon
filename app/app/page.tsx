"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, Sparkles } from "lucide-react";
import { connect, send, type ServerEvent } from "@/lib/ws";

type LogEntry =
  | { kind: "user"; text: string }
  | { kind: "xiexie"; text: string }
  | { kind: "skill"; name: string; result?: string; error?: string };

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8787/ws";

export default function Home() {
  const [connected, setConnected] = useState(false);
  const [listening, setListening] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [draft, setDraft] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const onEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
      case "transcript":
        setLog((l) => [...l, { kind: "user", text: e.text }]);
        break;
      case "speak":
        setLog((l) => [...l, { kind: "xiexie", text: e.text }]);
        break;
      case "confirm":
        setLog((l) => [...l, { kind: "xiexie", text: e.text }]);
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
      case "done":
        setListening(false);
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
    return () => ws.close();
  }, [onEvent]);

  const submitText = useCallback(
    (text: string) => {
      if (!wsRef.current || !text.trim()) return;
      setListening(true);
      send(wsRef.current, { type: "user_text", text: text.trim() });
      setDraft("");
    },
    []
  );

  return (
    <main className="min-h-screen flex flex-col items-center px-6 py-10">
      {/* Header */}
      <header className="w-full max-w-3xl flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-ember-500 flex items-center justify-center text-white font-semibold">
            谢
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Xiexie
            </h1>
            <p className="text-sm text-ember-700/70">
              your computer companion
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              connected ? "bg-emerald-500" : "bg-zinc-300"
            }`}
          />
          <span className="text-zinc-600">
            {connected ? "connected" : "offline"}
          </span>
        </div>
      </header>

      {/* Conversation */}
      <section className="w-full max-w-3xl flex-1 flex flex-col gap-3 mb-8 min-h-[40vh]">
        {log.length === 0 && (
          <EmptyState />
        )}
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
            onClick={() => setListening((l) => !l)}
            className={`relative w-12 h-12 rounded-full flex items-center justify-center text-white transition ${
              listening ? "bg-ember-500 pulse-ring" : "bg-ember-300 hover:bg-ember-400"
            }`}
            aria-label={listening ? "stop listening" : "start listening"}
          >
            {listening ? <MicOff size={22} /> : <Mic size={22} />}
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
        <p className="mt-3 text-xs text-zinc-500 text-center">
          Hot-mic STT and TTS plug in via /ws — see backend{" "}
          <code>main.py</code>.
        </p>
      </section>
    </main>
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
        Xiexie reads your wiki ({" "}
        <code>data/wiki/</code> ), picks a skill, asks before doing anything
        big, and learns a little after every conversation.
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
