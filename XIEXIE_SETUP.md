# Xiexie setup — fork of Clicky for the GOSIM 2026 demo

> The canonical setup walk-through is now in [`README.md`](README.md). This
> file is the quick-reference cheat sheet we kept open during judging.

This is a fork of [Clicky](https://github.com/farzaa/clicky)
adapted for the **Z.AI Innovation track** at GOSIM 2026: a senior-
friendly AI grandchild that protects from email scams, all running
through Z.AI GLM-4.6 and GLM-4.5V. The hard parts (menu-bar app,
push-to-talk, ScreenCaptureKit, cursor pointing) are all Clicky's
MIT-licensed work; we layer on top:

- ``worker/`` — Anthropic-compatible proxy that translates the Mac
  app's Claude payload into Z.AI ``/chat/completions`` and re-emits
  the SSE stream back as Anthropic events. The Swift code is
  **untouched** for LLM calls.
- ``data/`` — Michel Antoine persona seed in ``data/wiki/``, six
  2026 European scam ``.eml`` fixtures in ``data/demo/eml/``, and
  dated scam-pattern entries in ``data/wiki/scam_alerts.md``.
- ``XIEXIE_LEGACY.md`` — the pre-fork dev harness, kept as a
  journey log (decisions, ADRs, skill prompts).

## One-time setup (15 minutes)

### 1. Get the three API keys

| Provider | Free tier? | Where |
|----------|-----------|-------|
| Z.AI (GLM-4.6, GLM-4.5V) | $0.50 free credits | https://docs.z.ai/api-reference/introduction |
| AssemblyAI (streaming STT) | 100 hours free | https://www.assemblyai.com/app/account/keys |
| ElevenLabs (warm TTS) | 10k chars/month free | https://elevenlabs.io/app/settings/api-keys |

### 2. Local Worker — copy + fill the keys

```bash
cd worker
cp .dev.vars.example .dev.vars
# Edit .dev.vars and paste:
#   ZAI_API_KEY=<your z.ai key>
#   ASSEMBLYAI_API_KEY=<your assemblyai key>
#   ELEVENLABS_API_KEY=<your elevenlabs key>
```

(``.dev.vars`` is gitignored. Never commit it.)

### 3. Boot the Worker

```bash
cd worker
npm install
npx wrangler dev
```

Wrangler will say something like:

```
⛅️ wrangler 3.x.x
Local server: http://localhost:8787
```

Leave this terminal running for the rest of the demo.

### 4. Open + build the Xcode project

```bash
open leanring-buddy.xcodeproj
```

In Xcode:
1. Select the ``leanring-buddy`` scheme (yes, the typo's intentional —
   it's Clicky's original project name from the days it was called
   "Learning Buddy")
2. Signing & Capabilities → set your Team (your Apple ID is fine for
   local builds, no paid developer account needed)
3. Cmd-R to build and run

The app will appear in the menu bar (no Dock icon). Click it once to
open the panel, grant the **3 macOS permission prompts** as they
appear:

- **Microphone** (push-to-talk)
- **Accessibility** (global Cmd+Option hotkey)
- **Screen Recording** (ScreenCaptureKit for the scam-shield vision)

### 5. First conversation

Hold **Control + Option** anywhere on macOS to talk. Release to send.
Xiexie sees your screen + hears you, replies via TTS, and can fly the
cursor to specific UI elements (``[POINT:x,y:label:screenN]`` tags).

For the scam-shield demo path:

1. Open Mail.app and view one of the six scam emails (drag-dropped
   from ``data/demo/eml/`` per the legacy
   ``XIEXIE_LEGACY.md`` setup notes)
2. Hold Cmd+Option, say *"Is this email a scam?"*, release
3. Xiexie reads the screen, calls out the typosquat / SPF fail /
   Cialdini tactics in plain English, and points the cursor at the
   suspicious link

## Architecture cheat sheet

```
                   ┌────────────────────────┐
                   │  Xiexie.app (Swift)    │
                   │  ─ menu bar panel      │
                   │  ─ ScreenCaptureKit    │
                   │  ─ ⌃⌥ push-to-talk     │
                   │  ─ cursor overlay      │
                   └────────────┬───────────┘
                                │  HTTP / WS
                                ▼
                   ┌────────────────────────┐
                   │  Cloudflare Worker     │
                   │  ─ /chat (LLM)         │
                   │  ─ /tts (TTS)          │
                   │  ─ /transcribe-token   │
                   └────┬──────┬──────┬─────┘
                        │      │      │
              ┌─────────┘      │      └─────────┐
              ▼                ▼                ▼
        Z.AI GLM-4.6      ElevenLabs       AssemblyAI
        Z.AI GLM-4.5V       (TTS)        (streaming STT)
        (vision)
```

## What's different from upstream Clicky

- ``worker/src/index.ts`` rewritten: ``/chat`` now translates
  Anthropic Messages → OpenAI ChatCompletions for Z.AI and re-emits
  the OpenAI SSE stream back as Anthropic ``content_block_delta``
  events. Swift code is unchanged on this path.
- ``leanring-buddy/Info.plist`` — Xiexie-branded permission strings,
  AppleEvents added (we use AppleScript for Mail.app + Reminders.app),
  ATS localhost exception so ``wrangler dev`` works over plain HTTP.
- ``leanring-buddy/CompanionManager.swift`` — workerBaseURL now
  defaults to ``http://127.0.0.1:8787`` for local development.
- ``leanring-buddy/AssemblyAIStreamingTranscriptionProvider.swift``
  — same.

The Swift LLM payload format is unchanged (still Anthropic Messages),
which is why the model identifier ``claude-sonnet-4-6`` still appears
in ``ClaudeAPI.swift``. The Worker translates it to ``glm-4.6`` (or
``glm-4.5v`` if any image block is present) before forwarding.
