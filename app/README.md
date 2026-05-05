# Xiexie overlay (Next.js)

The voice-first overlay UI Margaret talks to. Connects to the Python backend
on `ws://localhost:8787/ws`.

## Run

```bash
pnpm install   # or npm install / bun install
pnpm dev       # http://localhost:3000
```

Make sure the backend is up first:

```bash
cd ../backend && uv run uvicorn xiexie.main:app --reload --port 8787
```

## What's wired today

- WebSocket bridge to `/ws` (see `lib/ws.ts`)
- Single-page conversational UI with text input fallback
- Senior-friendly type scale + warm "ember" palette
- Skill-result + transcript bubbles
- Browser-native voice loop (mic → `/transcribe` → WS → TTS) — see **Voice**

## Voice

The mic button drives a full duplex voice loop without any extra
dependencies:

1. **Click the mic** — Chrome asks for microphone permission the first time
   only. The button switches to a pulsing red state and a small 5-bar
   equaliser appears under the input, driven by a Web Audio
   `AnalyserNode` reading the live RMS level.
2. **Click again** — `MediaRecorder` stops, the captured WebM/Opus blob is
   POSTed as multipart `audio` to `${NEXT_PUBLIC_BACKEND_URL}/transcribe`
   (faster-whisper on the backend), and the resulting text is sent down the
   already-open `/ws` socket as a `user_text` event — exactly the same
   path as typed input.
3. **Backend replies** stream back as `transcript`, `speak`, `confirm`,
   `skill_*`, `alert`, and `done` events. `speak` and `confirm` events are
   both rendered in the chat **and** queued through the browser's
   `SpeechSynthesis` API so Margaret hears Xiexie speak. A small
   "🔊 speaking…" indicator appears next to the connection dot while TTS
   is mid-utterance.

The text input and Send button keep working unchanged — they're the
"type-instead" lane for the demo and a fallback when the mic is
unavailable.

### Voice selection

The TTS picker prefers, in order:

1. The voice named by `NEXT_PUBLIC_TTS_VOICE` (optional, see
   `.env.example`).
2. `Samantha` (warm female, default on macOS).
3. `Karen` (Australian, also warm) as a second pick.
4. Any `en-US` voice flagged `localService === true` (offline preferred).
5. The first available voice.

Defaults: `rate: 0.95` (slightly slower than browser default — easier to
follow for seniors per `data/wiki/preferences.md`) and `volume: 1.0`.

### Browser support

| Browser            | STT (mic capture) | TTS (`SpeechSynthesis`) |
|--------------------|-------------------|--------------------------|
| Chrome (desktop)   | ✅ recommended    | ✅ Google + system voices |
| Edge (desktop)     | ✅                | ✅ system voices          |
| Safari 17+ (macOS) | ✅                | ⚠️ limited offline voices — usually only `Samantha`/`Alex` are local; others stream from Apple |
| Firefox            | ✅                | ⚠️ no `localService` voices on macOS, falls through to whatever is available |

Chrome / Edge are the demo target. Safari works but the warm "Samantha"
voice is one of the only offline options; some voices may stutter on the
first utterance while the browser fetches the model.

### Permissions

Chrome will ask once for microphone access. It is also worth verifying
in **System Settings → Privacy & Security → Microphone** that the
browser is allowed (Edouard already pre-granted this in §9 of
`CLAUDE.md`).

## Up next (J1 evening / J2 morning)

- Live "wiki banner" panel showing the last-edited bullet (the **money shot**
  for the demo)
- Action log with skill icons + execution timing
- Optional: stream `speak` events from a backend Kokoro/ElevenLabs WAV
  endpoint when offline TTS quality is too thin for the recorded video
