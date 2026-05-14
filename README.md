# Xiexie 谢谢 — an AI grandchild for seniors

> Built solo in 36 hours at the **GOSIM Agentic Hackathon 2026**
> (Paris, Station F, May 5–6). Very grateful — and still a bit in
> shock — to have come in 🏆 **1st** in the **Z.AI Innovation track**.

A voice-first macOS companion that helps seniors spot email scams, reads their
screen out loud, and points at things they can't find. Forked from
[Farza's Clicky](https://github.com/farzaa/clicky) (MIT) and re-tuned for
**Z.AI's GLM-4.6 + GLM-4.5V**.

![Xiexie landing — when your grandchild is busy, your computer can be the next best thing](docs/assets/landing-hero.png)

Live: **[getxiexie.com](https://getxiexie.com)** · 3-min demo: **[getxiexie.com/demo](https://getxiexie.com/demo)**

The persona is **Michel Antoine**, 78, retired in Anglet, France, who lives
alone since his wife passed two years ago. His daughter lives in London. Most
days, the riskiest thing on his computer is the next email pretending to be
the *Caisse Primaire d'Assurance Maladie*.

> *"When your grandchild is busy, your computer can be the next best thing.
> Just say… Xiexie."*

---

## What it does

Hold **Control + Option** anywhere on macOS to talk to Xiexie. Release to
send. Xiexie sees the screen, hears you, replies in a warm voice, and can fly
an ember-orange cursor to specific UI elements you should look at — including
the suspicious link inside a phishing email.

The flagship beat is the **scam shield**. When Michel asks *"Xiexie, est-ce
que cet email est une arnaque ?"*, GLM-4.5V reads the Mail.app screenshot,
spots the typosquat domain, the SPF/DMARC mismatch, the urgency-and-fear
language, and replies in plain French:

> *"Michel, this is a scam. The sender pretends to be your grandson Edouard,
> but the email comes from a free protonmail address with no DKIM signature.
> Don't reply, don't send money. If you're worried, hang up and call my real
> number."*

…then the cursor flies to the suspicious link with a 20 pt label that says
*"the fake link"*, so Michel sees it from across the kitchen.

A small Karpathy-style LLM-Wiki (`data/wiki/`) is the agent's plain-markdown
memory: who Michel's children are, when his daughter visits, which scam
patterns he's already been warned about. Editable in TextEdit, ideally
growing after every conversation (the linter that closes the loop is on the
follow-up list, not in `main` yet).

---

## What's different from upstream Clicky

| Layer | Clicky | Xiexie |
|---|---|---|
| LLM orchestrator | Anthropic Claude Sonnet 4.6 | **Z.AI GLM-4.6** (text) + **GLM-4.5V** (vision, auto-routed by the Worker on image input) |
| Worker proxy | direct passthrough to Anthropic | **Anthropic ↔ OpenAI translator**: the Mac app's payload format is unchanged, the Worker rewrites to Z.AI ChatCompletions and re-emits the upstream OpenAI SSE as Anthropic events |
| Persona | "AI teacher" for general computer help | "AI grandchild" for a 78-year-old; scam-shield as the top mission |
| UI scale | tuned for millennials | every cursor + label + waveform 2.25× larger; panel 1.6× wider; ember/cream warm palette instead of tech-blue |
| Wake | only ⌃⌥ push-to-talk | ⌃⌥ *and* a custom-trained openWakeWord ONNX for *"Xiexie"* (training pipeline + 944 user recordings; runtime integration lives on `feat/wakeword-realtime`, not on `main` yet) |
| Side-screen alerts | none | a red `!` / amber `?` warning glyph slides in from the screen edge when the scam verdict drops |
| Demo data | none | six RFC822 `.eml` fixtures of currently-active 2026 European scam patterns, drag-droppable into Mail.app |
| Memory | none | Karpathy-style LLM-Wiki seeded with the Michel Antoine persona |

The Swift code change for the LLM swap is **one line** — the heavy lifting is
in the Worker (`worker/src/index.ts`). That keeps upstream Clicky as the
source of truth on everything voice + cursor + screen capture, and isolates
Xiexie's contributions as a small, reviewable diff.

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

The Worker's `/chat` route is the only non-trivial piece. It accepts the Mac
app's existing Anthropic Messages payload, walks the content blocks,
translates `image/source/base64` to OpenAI's `image_url/data:` form, forwards
to Z.AI's OpenAI-compatible endpoint with `thinking: { type: "disabled" }`
(otherwise GLM-4.6's chain-of-thought prefix tends to eat the token budget
before the actual reply lands), and re-emits the OpenAI SSE stream back to
Swift as Anthropic-shaped `content_block_delta` events.

---

## Setup (≈15 minutes from a fresh Mac)

### Prerequisites

- macOS 14.2+ (for ScreenCaptureKit)
- Xcode 15+
- Node.js 18+
- A free Cloudflare account
- Three API keys (all have free tiers):
  - **Z.AI** — https://docs.z.ai/api-reference/introduction
  - **AssemblyAI** — https://www.assemblyai.com/app/account/keys
  - **ElevenLabs** — https://elevenlabs.io/app/settings/api-keys

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

Wrangler runs the Worker locally at `http://127.0.0.1:8787`. Leave that
terminal open for the rest of the session.

### Build the Mac app

```bash
open leanring-buddy.xcodeproj
```

In Xcode:

1. Select the `leanring-buddy` scheme (yes, the typo's intentional — Clicky's
   original project name was *Learning Buddy*; we kept the path so the
   upstream patch surface stays small).
2. Signing & Capabilities → set your Team (a free Apple ID is fine for local
   builds).
3. Cmd-R.

The app installs in the menu bar (no Dock icon, no Cmd-Tab entry). Click the
tray icon, grant the four permission prompts (Microphone, Accessibility,
Screen Recording, Screen Content), and you're live.

### Drop the demo emails into Mail.app (optional)

```bash
cd data/demo/eml
python3 build_mbox.py
# Then in Mail.app: File → Import Mailboxes → Files in mbox format
# → select data/demo/eml/ → Continue → drag the imports into your Inbox.
```

`data/demo/eml/README.md` has the full recipe.

---

## Project structure

```
leanring-buddy/                  # Swift sources (typo kept from Clicky)
  CompanionManager.swift           # Central state machine + Xiexie system prompt
  CompanionPanelView.swift         # Menu bar panel UI (Xiexie-rebranded, GLM-4.6 chip)
  ClaudeAPI.swift                  # LLM streaming client (talks to Z.AI via the Worker)
  ElevenLabsTTSClient.swift        # Text-to-speech playback (warm French Marin voice)
  OverlayWindow.swift              # Ember cursor + 2.25× labels
  WarningGlyphOverlay.swift        # Side-screen ! / ? phishing glyph
  AssemblyAI*.swift                # Real-time push-to-talk transcription
  DesignSystem.swift               # Ember palette overrides Clicky's blue scale
  Assets.xcassets/                 # Ember-recolored AppIcon
worker/
  src/index.ts                     # Anthropic ↔ Z.AI/OpenAI streaming SSE translator
  wrangler.toml                    # Public vars (model names, voice ID)
  .dev.vars.example                # Template for the three secret keys
data/
  demo/eml/                        # Six 2026 European scam .eml fixtures
  wiki/                            # Karpathy LLM-Wiki seed (Michel Antoine persona)
docs/
  assets/landing-hero.png          # Repo hero image
  demo-script-3min.md              # The 3-minute Loom script recorded for judging
xiexie.onnx                        # Custom-trained "Xiexie" wake-word model (13.7 KB)
XIEXIE_SETUP.md                    # Quick setup reference
XIEXIE_LEGACY.md                   # Pre-fork engineering log (decisions + journey)
AGENTS.md                          # Original Clicky architecture doc (kept verbatim)
```

---

## Honest caveats

A few things I'd want to fix before calling this "done":

- The wake-word integration is wired on `feat/wakeword-realtime` but not on
  `main` — it needs a week of noisy-kitchen field testing first.
- The LLM-Wiki linter that's supposed to grow `data/wiki/` after every
  conversation isn't running yet. Right now the wiki is frozen at the seed.
- The French dub-track on the demo prompt is hand-tuned, not data-driven.
- I'd love to localise the system prompt + voice for English / Spanish /
  Italian seniors. The framing is universal; the dub track isn't.

Treat this README as a hackathon checkpoint, not a finished product. There's
a lot I still want to learn (Swift concurrency, ScreenCaptureKit's nuances,
ONNX runtime in Swift, evals on multimodal LLMs), and a lot more to ship.

---

## Credits + license

Xiexie is a fork of [Clicky by Farza](https://github.com/farzaa/clicky) and
inherits its **MIT license** verbatim. Every Swift source file under
`leanring-buddy/` is a derivative of Clicky's work — huge thanks to Farza
for open-sourcing such a clean and well-engineered base. If you build on
this, please credit him first.

The Xiexie persona, the scam-shield system prompt, the Worker LLM translator,
the ember palette, the senior-scale UI, the side-screen warning glyph, the
openWakeWord-Xiexie training pipeline, and the European demo fixtures are by
**Edouard Foussier**, also under MIT.

Powered by **Z.AI** credits (GLM-4.6 + GLM-4.5V), **AssemblyAI** credits
(streaming STT), and **ElevenLabs** credits (warm French Marin voice). Thanks
to the GOSIM team for hosting the hackathon at Station F, and to the Z.AI
mentors for taking the time to talk us through GLM's quirks during the night.

Feedback, corrections, ideas — DMs open on [GitHub](https://github.com/edouardfoussier).
