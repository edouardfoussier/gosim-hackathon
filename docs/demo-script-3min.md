# Xiexie demo — 3-minute Loom script

Recording target: **3:00 ± 0:10**. Loom screen + mic, 1080p, 30 fps.
Audience: GOSIM 2026 jury (Z.AI Innovation track).

## Pre-flight (90 s, BEFORE you hit record)

1. **Worker** — terminal 1, leave running:
   ```bash
   cd /Users/edouardfoussier/code/gosim-hack/worker && npx wrangler dev
   ```
2. **Mac**: System Settings → Privacy & Security → Screen Recording → enable Loom + Xiexie.
3. **Xcode**: Cmd-R, wait for the menu-bar icon to appear, click it once to open the panel, **dismiss** the panel (Cmd-W or click outside) so the demo starts with a clean menu bar.
4. **Mail.app**: open it, navigate to **Inbox**, click on `01-grandchild-bail.eml` (the AI-voice-clone "Edouard, ton petit-fils" email) so it's the visible message when you hit record. Make sure the suspicious link `http://wu-paiement-securise.com/...` is on screen — scroll up if not.
5. **Hide every other app**. Cmd-Option-H from Mail.app to hide all others.
6. **Loom**: choose "Screen + Cam + Mic", select primary display, frame Mail.app + space for cursor on the right.
7. Take three breaths. **Record**.

---

## SCRIPT — verbatim, slow pace

Speak slowly. Pauses are part of the demo. Aim for ~150 words/min. Dans le doute, ralentis encore.

### 0:00 – 0:18 · Hook (18 s)

> "I'm Edouard. This is Xiexie — my AI grandchild for my grandfather Michel."
>
> *(beat — let it land)*
>
> "Michel is 78, lives alone in Anglet since my grandmother passed two years ago. Every week he gets emails like this one." *(point cursor at the open Mail.app message)*

### 0:18 – 0:35 · Stake (17 s)

> "It says it's from me — his grandson — stuck in Lisbon, asking for four hundred and eighty euros by Western Union. Don't tell Tom, I love you. Send fast."
>
> "Two years ago, my actual grandfather almost wired three thousand to a scammer just like this. That's what Xiexie is here for."

### 0:35 – 0:55 · Reveal the app (20 s)

> "Xiexie lives in his menu bar. Always-on, never in the way." *(click tray icon, panel opens)*
>
> "It runs entirely on Z.AI's GLM. GLM-4.6 to talk, GLM-4.5V to see his screen." *(point at the GLM-4.6 + GLM-4.5V chip in the panel)*
>
> "And he calls it just by holding Control + Option."

### 0:55 – 2:05 · The money beat — scam shield (70 s)

*(close the panel by clicking outside — Mail.app is back in focus)*

> "Watch what happens when Michel asks Xiexie about this email."

*(hold Ctrl+Option, speak slowly into mic)*

> *"Xiexie, est-ce que cet email est une arnaque ?"*

*(release. Wait — processing spinner ember-orange near cursor. ~5-8 s. Then Marin's voice, ember bars dancing.)*

Marin says (paraphrase — actual response varies):

> *"Michel, this is a scam. The sender pretends to be your grandson Edouard, but the email comes from a free protonmail address with no DKIM signature. Your wiki says I am in Paris this week, not stuck in Lisbon. Don't reply, don't send money. If you're worried, hang up and call my real number."*

*(simultaneously: ember cursor flies to the suspicious link, label "the fake link" pops in 20 pt — let the cursor arrive, hold for 2 s)*

*(silent beat — let the judges read the response bubble)*

> "Notice three things." *(point with your real cursor as you list each)*
>
> "One — the verdict comes first. Plain language. **'This is a scam.'** No jargon, no acronyms."
>
> "Two — the cursor flew to the bad link. Michel doesn't have to hunt for it."
>
> "Three — Xiexie cross-referenced his memory. It knew where I, his grandson, am. That's the LLM-Wiki pattern — the agent's memory is plain markdown that grows after every conversation."

### 2:05 – 2:30 · Tech reveal (25 s)

> "Under the hood — Xiexie is a fork of Farza's Clicky. We swapped Anthropic for Z.AI's GLM via a Cloudflare Worker that translates Anthropic Messages to OpenAI ChatCompletions on the fly. The Swift app didn't change for the LLM swap."
>
> "We trained a custom 'Xiexie' wake-word — twelve thousand bytes of ONNX trained on nine hundred recordings — so Michel can summon it just by speaking, no hotkey." *(if wake-word works: demo it; if not: skip this line)*
>
> "And every glyph, every label, is two-and-a-quarter times Clicky's defaults — because seventy-eight-year-old eyes don't need a flat-design pixel-perfect UI. They need warmth and contrast."

### 2:30 – 2:55 · Close (25 s)

> "We targeted the Z.AI Innovation track because GLM-4.5V's vision plus GLM-4.6's reasoning made the 'see this email, judge this email, point at this link' loop feel like one model thinking, not three services taped together."
>
> "Forty-six teams registered for GOSIM. Zero of them target elder protection. One in three Europeans over seventy lives alone. Xiexie is for them."
>
> *(beat)*
>
> "Try it — getxiexie dot com. Thank you."

### 2:55 – 3:00 · Outro (5 s)

*(hold the closing frame — panel + Mail.app side by side, ember cursor still pointing at the bad link, your last sentence finishing)*

*(stop recording)*

---

## Fallback table — what to do if X breaks live

| If… | Do… |
|---|---|
| Wake-word doesn't fire | Just hold Ctrl+Option, never mention it. Skip the line at 2:18. |
| Marin says "out of credits" | Stop recording, paste the new ElevenLabs key into ``worker/.dev.vars``, restart wrangler, retry. |
| Cursor doesn't fly to the link | Don't sweat it. Read the verdict aloud yourself ("see how it nailed the protonmail tell?") — judges read the response bubble too. |
| GLM hallucinates "Sophie" instead of "Edouard" | Re-record. The Michel persona sub-agent might still be running; check git log. |
| Mail.app is on a different macOS Space | Cmd-` (backtick) to bring it forward, or just keep Mail in front while recording. |
| ElevenLabs voice sounds robotic | The free-tier voice is okay; pro plan voice is warmer. Edouard already swapped to pro this morning. |

## Loom export

- **Title**: `Xiexie — AI grandchild for seniors (GOSIM 2026)`
- **Description**:
  ```
  Voice-first macOS companion that protects seniors from email scams.
  Built on Z.AI GLM-4.6 + GLM-4.5V at the GOSIM 2026 Hackathon (Paris,
  May 5–6). Forked from Clicky (MIT). Repo:
  https://github.com/edouardfoussier/gosim-hackathon
  Landing: https://getxiexie.com
  ```
- **Privacy**: Anyone with the link
- **Add the Loom URL** to the GOSIM submission form's "Demo video link" field

---

## Final reminders before you hit record

- **Don't read the script verbatim** — read it three times beforehand, then talk to the camera. Sounds way warmer.
- **Slow down.** Pauses make the demo feel deliberate, not flustered.
- **Look at the camera at the start** ("I'm Edouard.") and at the end ("Thank you.") — the rest you can look at the screen.
- **One take is fine.** Two if you fluff a line. Three if you really need it. Don't spend an hour chasing perfection — judges value authenticity, not polish.

You've got this. Bonne chance.
