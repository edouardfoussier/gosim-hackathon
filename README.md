# 🏆 GOSIM Agentic Hackathon 2026 — 1st place

### **Xiexie 谢谢 — an AI grandchild for seniors who get scammed online**

**1st place · GOSIM Agentic Hackathon 2026 (Paris, Station F, May 5–6) · Z.AI Innovation track**

Swift · macOS 14+ · Cloudflare Workers · Z.AI GLM-4.6 + GLM-4.5V · AssemblyAI · ElevenLabs · openWakeWord

**Hold ⌃⌥ on a Mac to ask Xiexie *"is this email a scam?"* — GLM-4.5V reads the screen, GLM-4.6 writes the verdict in your grandparent's voice, and an ember-orange cursor flies to the suspicious link with a 20 pt label they can read from across the kitchen.**

![Xiexie landing — when your grandchild is busy, your computer can be the next best thing](docs/assets/landing-hero.png)

Live: **[getxiexie.com](https://getxiexie.com)** · 3-min demo: **[getxiexie.com/demo](https://getxiexie.com/demo)**

---

## TL;DR — what the jury saw

> **As a 78-year-old retiree living alone in Anglet, France, I want a voice-first companion on my Mac that protects me from the daily phishing emails I now get in fluent French, reads my screen out loud when I can't see well, and points my cursor at exactly where I should — or *should not* — click.**

Xiexie turns a senior's Mac into a voice-first AI grandchild that:

1. **Sits in the menu bar** — no Dock icon, no Cmd-Tab clutter, nothing for Michel to accidentally drag into the trash.
2. **Wakes up on hold-to-talk** (Control + Option, global hotkey) — or, on the `feat/wakeword-realtime` branch, on a custom-trained *"Xiexie"* wake word (openWakeWord ONNX, 944 user recordings, 13.7 KB on disk).
3. **Sees the screen** with **GLM-4.5V** via ScreenCaptureKit — auto-routed by the Worker on any request that includes a screenshot.
4. **Reasons over the email** with **GLM-4.6** — sender-domain typosquats, SPF/DMARC mismatch, urgency-and-fear language, Cialdini-tactic patterns from `data/wiki/scam_alerts.md`.
5. **Replies in a warm French voice** (ElevenLabs, with a native macOS Thomas fallback) — verdict-first, jargon-free, with numbers and amounts always repeated twice.
6. **Points the cursor** at the suspicious link via inline `[POINT:x,y|label]` tags emitted by the LLM — the ember triangle flies across the screen with a 20 pt label so Michel sees it from a metre away.
7. **Side-screen warning glyphs** — a red `!` or amber `?` slides in from the screen edge when the verdict drops, so the alert is unmissable even with hearing loss.
8. **Remembers** — a Karpathy LLM-Wiki (`data/wiki/`) is the agent's plain-markdown memory: who Michel's children are, when his daughter visits, which scam patterns he's already been warned about. It grows after every conversation.

A design choice we leaned on hard: **don't rebuild Clicky, fork it.** The voice loop, the global hotkey, the cursor overlay, the ScreenCaptureKit plumbing, the menu-bar lifecycle — that's all Farza's MIT-licensed Clicky, kept verbatim. Our contribution is layered cleanly on top: a Cloudflare Worker that swaps the LLM seam from Anthropic to Z.AI on the wire (Swift code unchanged), a senior-scaled visual rewrite (2.25× cursor + labels, 1.6× panel, ember/cream palette), and a scam-shield system prompt with European phishing fixtures.

That fork strategy is what let one person ship a real native `.app` in 36 hours instead of fighting Xcode for two days and demoing in a browser tab.

---

## The flagship beat — scam shield

The judging-floor signature is one prompt: **"Xiexie, est-ce que cet email est une arnaque ?"** Michel says it while a phishing email impersonating his grandson Edouard ("stuck in Lisbon, send 480€ Western Union") is open in Mail.app. Xiexie answers, in Marin's voice:

> *"Michel, this is a scam. The sender pretends to be your grandson Edouard, but the email comes from a free protonmail address with no DKIM signature. Your wiki says I am in Paris this week, not stuck in Lisbon. Don't reply, don't send money. If you're worried, hang up and call my real number — six, zero, six, dot, eight, two, dot…"*

…and the ember cursor flies to `wu-paiement-securise.com/...` with a 20 pt label that says *"the fake link"*. Three things make the beat land:

1. **Verdict first.** Plain language. No jargon. No "phishing-likelihood score: 0.92" — just *"this is a scam"*.
2. **The cursor flies to the bad link.** Michel doesn't have to hunt. The model emits `[POINT:x,y|the fake link]` inline; the Swift overlay parses it, animates the triangle, and pins the label until Michel acknowledges.
3. **Cross-referenced memory.** Xiexie's response *"Your wiki says I am in Paris this week, not stuck in Lisbon"* came from `data/wiki/family.md`. The LLM-Wiki pattern (Karpathy, April 2026) is the agent's plain-markdown memory — owned by the user, editable in TextEdit, growing after every conversation.

That single beat is what we optimised the entire build for landing reliably under judging-floor lighting.

---

## What's different from upstream Clicky

| Layer | Clicky | Xiexie |
|---|---|---|
| LLM orchestrator | Anthropic Claude Sonnet 4.6 | **Z.AI GLM-4.6** (text) + **GLM-4.5V** (vision, auto-routed by the Worker on image input) |
| Worker proxy | direct passthrough to Anthropic | **Anthropic ↔ OpenAI translator**: Swift app's payload format unchanged, Worker rewrites to Z.AI ChatCompletions and re-emits the upstream OpenAI SSE as Anthropic events |
| Persona | "AI teacher" for general computer help | "AI grandchild" for a 78-year-old, scam-shield as the top mission |
| UI scale | tuned for millennials | every cursor + label + waveform **2.25× larger**; panel **1.6× wider**; ember/cream warm palette instead of tech-blue |
| Wake | only ⌃⌥ push-to-talk | ⌃⌥ *and* a custom-trained openWakeWord ONNX for *"Xiexie"* (training pipeline + 944 user recordings ship in `training/wakeword/` — runtime integration on `feat/wakeword-realtime`) |
| Side-screen alerts | none | red `!` / amber `?` warning glyph slides in from the screen edge on scam verdicts |
| Demo data | none | six RFC822 `.eml` fixtures of currently-active 2026 European scam patterns, drag-droppable into Mail.app for the judging panel |
| Memory | none | Karpathy-style LLM-Wiki (`data/wiki/`) seeded with the Michel Antoine persona |

The Swift code change for the LLM swap is **one line** — the heavy lifting is in the Worker (`worker/src/index.ts`). That keeps upstream Clicky the source of truth on everything voice + cursor + screen capture, and isolates Xiexie's contributions as a small, reviewable diff.

---

## Architecture

```
                ┌──────────────────────────┐
                │  Xiexie.app (Swift)      │
                │  • menu bar panel        │
                │  • ScreenCaptureKit      │
                │  • ⌃⌥ push-to-talk       │
                │  • ember cursor overlay  │
                │  • [POINT:x,y] pointing  │
                │  • side-screen glyph     │
                └────────────┬─────────────┘
                             │ HTTPS / SSE
                             ▼
                ┌──────────────────────────┐
                │  Cloudflare Worker        │
                │  • /chat (LLM)           │
                │  • /tts (TTS)            │
                │  • /transcribe-token     │
                └──┬──────────┬──────────┬─┘
                   │          │          │
        ┌──────────┘          │          └──────────┐
        ▼                     ▼                     ▼
  Z.AI GLM-4.6           ElevenLabs            AssemblyAI
  Z.AI GLM-4.5V             (TTS)            (streaming STT)
  (auto-routed by
   the Worker on
   image input)
```

The Worker's `/chat` route is the only non-trivial piece. It accepts the Mac app's existing Anthropic Messages payload, walks the content blocks, translates `image/source/base64` to OpenAI's `image_url/data:` form, forwards to Z.AI's OpenAI-compatible endpoint with `thinking: { type: "disabled" }` (otherwise GLM-4.6's chain-of-thought prefix burns the token budget before the actual reply lands), and re-emits the OpenAI SSE stream back to Swift as Anthropic-shaped `content_block_delta` events. The Mac app stays unchanged on the LLM seam.

---

## Setup (15 minutes from a fresh Mac)

### Prerequisites

- macOS 14.2+ (for ScreenCaptureKit)
- Xcode 15+ — App Store
- Node.js 18+ — `brew install node`
- A free Cloudflare account
- Three API keys (all have free tiers; combined ≈ €0 for a few demos):
  - **Z.AI** — https://docs.z.ai/api-reference/introduction
  - **AssemblyAI** — https://www.assemblyai.com/app/account/keys (streaming STT)
  - **ElevenLabs** — https://elevenlabs.io/app/settings/api-keys (warm TTS)

### Clone + Worker

```bash
git clone https://github.com/edouardfoussier/gosim-hackathon.git xiexie
cd xiexie

cd worker
cp .dev.vars.example .dev.vars
# Edit .dev.vars and paste the three keys.
npm install
npx wrangler dev
```

Wrangler runs the Worker locally at `http://127.0.0.1:8787`. Leave that terminal open for the rest of the session.

### Build the Mac app

```bash
open leanring-buddy.xcodeproj
```

In Xcode:

1. Select the `leanring-buddy` scheme (yes, the typo's intentional — Clicky's original project name was *Learning Buddy*; we keep the path so the upstream patch surface stays small).
2. Signing & Capabilities → set your Team (a free Apple ID is fine for local builds).
3. Cmd-R.

The app installs in the menu bar (no Dock icon, no Cmd-Tab entry). Click the tray icon, grant the four permission prompts (Microphone, Accessibility, Screen Recording, Screen Content), and you're live.

### Drop the demo emails into Mail.app (optional, for the scam-shield path)

```bash
cd data/demo/eml
python3 build_mbox.py
# Then in Mail.app: File → Import Mailboxes → Files in mbox format
# → select data/demo/eml/ → Continue → drag the imports into your Inbox.
```

`data/demo/eml/README.md` has the full recipe + an `osascript` to mark all six unread in one shot.

---

## Project structure

```
leanring-buddy/                  # Swift sources (typo kept from Clicky)
  CompanionManager.swift           # Central state machine (Xiexie persona system prompt)
  CompanionPanelView.swift         # Menu bar panel UI (Xiexie-rebranded, GLM-4.6 chip)
  ClaudeAPI.swift                  # LLM streaming client (now talks to Z.AI via Worker)
  ElevenLabsTTSClient.swift        # Text-to-speech playback (warm French Marin voice)
  OverlayWindow.swift              # Ember cursor + 2.25× labels (was 1× blue)
  WarningGlyphOverlay.swift        # Side-screen ! / ? phishing glyph
  AssemblyAI*.swift                # Real-time push-to-talk transcription
  DesignSystem.swift               # Color tokens — ember palette overrides Clicky's blue scale
  Assets.xcassets/                 # Ember-recolored AppIcon (was Clicky's blue triangle)
worker/
  src/index.ts                     # Anthropic ↔ Z.AI/OpenAI streaming SSE translator
  wrangler.toml                    # Public vars (model names, voice ID)
  .dev.vars.example                # Template for the three secret keys
data/
  demo/eml/                        # Six 2026 European scam .eml fixtures (Michel persona)
  wiki/                            # Karpathy LLM-Wiki seed (family, accounts, scam_alerts)
docs/
  assets/landing-hero.png          # Repo hero image
  demo-script-3min.md              # The 3-minute Loom script we recorded for judging
xiexie.onnx                        # Custom-trained "Xiexie" wake-word model (13.7 KB)
appcast.xml                        # Sparkle update feed (inherited from Clicky)
XIEXIE_SETUP.md                    # Quick setup reference
XIEXIE_LEGACY.md                   # Pre-fork engineering log (decisions, ADRs, the journey)
AGENTS.md                          # Original Clicky architecture doc (kept verbatim)
```

---

## How we scored against the GOSIM rubric

The judges weighted four columns at 20 % each. Here's how we framed each one — for ourselves, and for the panel.

- **Innovation (20 %)** — Forty-six teams registered; zero of them target elder protection on macOS. The framing — *"AI grandchild that protects, remembers, and never sleeps"* — is the moat, not the tech stack underneath it. *"One in three Europeans over seventy lives alone"* is the line we opened the close with.
- **Technical depth (20 %)** — End-to-end across the stack: a custom-trained openWakeWord ONNX classifier (`training/wakeword/xiexie_wakeword_training.ipynb`), a Cloudflare Worker that translates two LLM API contracts in streaming SSE without ever buffering the response, GLM-4.5V vision auto-routed by the same Worker on image-bearing requests, and a Karpathy LLM-Wiki memory pattern in `data/wiki/` so the agent's context grows after each conversation.
- **Practicality (20 %)** — The fork strategy itself was the practicality beat. Rather than build a Mac app from scratch in 36 hours, we forked Clicky's MIT-licensed shell, rebranded the surfaces a senior actually sees, and swapped the LLM seam. That gave us a real `.app` with ScreenCaptureKit, global push-to-talk, multi-monitor cursor pointing, and Cmd-Q lifecycle on **day one** — features that would have eaten the whole hackathon to rebuild from scratch.
- **Presentation (20 %)** — The demo lives or dies on one beat: Michel asks *"est-ce que cet email est une arnaque ?"* about a real-looking phishing fixture, GLM-4.5V reads the screen, the verdict drops in plain French, the side-screen glyph slides in, and the ember cursor flies to the fake link with a 20 pt label. We optimised the entire build for that one moment landing reliably under judging-floor lighting.

We're a one-person team. There's a long list of follow-on work (`feat/wakeword-realtime` is wired but not yet shipped on `main`; the wiki linter pipeline isn't running yet; the French dub-track on the demo prompt is hand-tuned, not data-driven). Treat this README as a checkpoint, not a finished product.

---

## What's next

- Ship the custom *"Xiexie"* wake-word on `main` once it survives a week of noisy-kitchen field testing.
- Open the wiki linter (`data/wiki/` markdown self-maintenance) so the LLM-Wiki actually grows after every conversation instead of staying frozen at the seed.
- Localise the system prompt + voice for English / Spanish / Italian seniors — the framing is universal, the dub track isn't.
- Generate per-scam-pattern *prevention cards* the family can post on the fridge — Xiexie already has the data; it's a templating pass away.

If any of that sounds interesting, my GitHub DMs are open and the **Call Edouard** button inside the app is a live FaceTime to my phone.

---

## Credits + license

This project is a fork of [Clicky by Farza](https://github.com/farzaa/clicky) and inherits its **MIT license** verbatim. Every Swift source file under `leanring-buddy/` is a derivative of Clicky; please give Farza credit if you build on top.

The Xiexie persona, the scam-shield system prompt, the Worker LLM translator, the ember palette, the senior-scale UI rewrite, the side-screen warning glyph, the openWakeWord-Xiexie training pipeline, and the European demo fixtures are by **Edouard Foussier**, also under MIT. Pull requests welcome.

Powered by **Z.AI** credits (GLM-4.6 + GLM-4.5V), **AssemblyAI** credits (streaming STT), and **ElevenLabs** credits (warm French Marin voice). Sparkle update feed and DMG packaging inherited from Clicky.

🏆 **1st place · GOSIM Agentic Hackathon 2026 · Z.AI Innovation track · Paris, Station F, May 5–6.**
