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

## Up next (J1 evening / J2 morning)

- Web Audio API mic capture → ship audio to backend `/transcribe`
  (or run STT in-browser via Whisper WASM if latency is fine)
- TTS playback of `speak` events (HTMLAudioElement + backend WAV stream)
- Live "wiki banner" panel showing the last-edited bullet (the **money shot**
  for the demo)
- Action log with skill icons + execution timing
