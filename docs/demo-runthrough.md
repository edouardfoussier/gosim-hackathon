# Demo run-through — the 1am sweat sheet

> Two sections. **Part 1** is your solo rehearsal recipe. **Part 2** is
> the 5-minute live storyboard for the judging room.
> Print Part 2 on the second monitor. Don't improvise — you're solo.

---

## Part 1 — Solo rehearsal recipe (the night before)

### 0. Pre-flight (60 s)

**Permissions.** macOS Sequoia silently substitutes the wallpaper for
the actual screen pixels when Screen Recording isn't granted to the
process that launches `uvicorn`. Verify with:

```bash
screencapture -x -t jpg /tmp/check.jpg && file /tmp/check.jpg
# Want: JPEG 2880x1800 (or whatever your retina is).
# If "could not create image from display" → System Settings →
# Privacy & Security → Screen Recording → enable Terminal,
# then Cmd+Q the WHOLE Terminal (not just the window) and reopen.
```

Other perms (set once, never touch again): Microphone, Accessibility,
Automation, Input Monitoring, Full Disk Access — all granted to
Terminal. See `CLAUDE.md` §9 if any failed last time.

**.env sanity** (one line, fast):

```bash
grep -E "ZAI_BASE_URL|ZAI_MODEL|OPENAI_API_KEY|MAIL_SOURCE" \
  /Users/edouardfoussier/code/gosim-hack/.env
# Want:
#   ZAI_BASE_URL=https://api.z.ai/api/paas/v4
#   ZAI_MODEL=glm-4.6
#   OPENAI_API_KEY=sk-proj-...     ← required for continuous voice
#   MAIL_SOURCE=mailapp            ← live Mail.app; flip to demo for fixture
```

**Reset the demo state** (between takes):

```bash
git checkout data/demo/inbox.json   # restore archived flags
pkill -9 -f "uvicorn xiexie" 2>/dev/null
pkill -9 -f "overlay" 2>/dev/null
lsof -t -i:8787 | xargs -r kill -9 2>/dev/null
lsof -t -i:3000 | xargs -r kill -9 2>/dev/null
```

**Same Space rule (critical for cursor pointing).** `read_screen` with
`app="Mail"` only emits `[POINT:x,y|label]` markers when GLM-4.5V
sees real Mail pixels. If Mail.app is on a different macOS Space than
Chrome, `_capture_app_window` returns an off-screen buffer,
`pointable=False`, and the model is told **not** to emit POINTs. Drag
Mail.app into the same Space as Chrome before recording. Verify:

```bash
osascript -e 'tell application "System Events" to tell process "Mail" \
  to get position of front window'
# Want: {non-negative-x, non-negative-y}. If x is wildly negative
# (e.g. -2000) Mail is on the next Space — drag it back.
```

---

### 1. Boot the three services (3 terminals)

Each stays open. Don't background them — you want to read the logs.

**Terminal 1 — backend:**

```bash
cd /Users/edouardfoussier/code/gosim-hack/backend
uv run --active uvicorn xiexie.main:app --port 8787 --log-level info
```

Wait for `Uvicorn running on http://127.0.0.1:8787`. The faster-whisper
warmup runs in a daemon thread; the first real STT call is instant.

**Terminal 2 — pointer/halo overlay (PyQt6, native macOS layer):**

```bash
cd /Users/edouardfoussier/code/gosim-hack
source overlay/.venv/bin/activate
python -m overlay
```

Wait for `[overlay] backend WS connected`. This is the desktop-level
cursor pointer + soundwave halo (mirrors the in-browser `<CursorHalo>`
and `<CursorPointer />`). If you only have the Chrome tab visible
during the demo, you can skip Terminal 2 — the browser overlays are
sufficient.

**Terminal 3 — Next.js:**

```bash
cd /Users/edouardfoussier/code/gosim-hack/app
pnpm dev
```

Open `http://localhost:3000` in **Chrome** (Safari's `webkitSpeech-
Recognition` is patchy and the offline TTS voices are worse). Grant
mic when prompted. Once the page mounts you should see, in the
header:

- a green dot + `connected`
- a pulsing ember dot + `listening for "Xiexie" or "computer"…`

That second pill confirms the passive wake listener is armed. If it's
missing, the browser's `SpeechRecognition` failed (not Chrome, or no
network for Chrome's speech servers) — still fine, click the mic
button manually.

---

### 2. Scenarios — what to say, what to see, what the log proves

Every scenario assumes you start with the wake listener armed and the
chat empty. If the chat has stale content, just refresh the page.

#### 2.1 — Voice loop smoke test (~3 s)

| | |
|---|---|
| **Say** | "Hey Xiexie, what time is it?" |
| **See in chat** | user bubble, then a Xiexie bubble with the current time spoken back. The cursor halo flashes a tiny pulsing dot with `thinking` for ~1 s, then bars when Marin replies. |
| **Log** | `INFO: ... POST /voice/session HTTP/1.1 201` (continuous mode opened) and a Marin transcript line. No skill_start fires — `narrate` is the sentinel. |
| **Fallback** | If no audio plays: Marin probably refused due to a missing `OPENAI_API_KEY`. Confirm `capabilities.continuous=true` in DevTools → Network → `/voice/capabilities`. If false, fall back to mic-button click + Whisper — still works, just not continuous. |

Note: there is no `time_of_day` skill. The model just says it from
context. The point of this beat is to prove the wake → realtime →
Marin → audio loop is alive.

#### 2.2 — "Open Mail" (~2 s)

| | |
|---|---|
| **Say** | "Open Mail." |
| **See** | cursor halo: pulsing dot + `opening the app`. Chat: a `open_app` skill line. Mail.app comes to front. |
| **Log** | `skill_start name='open_app'` then `skill_result name='open_app' ... 'Opened Mail.'` |
| **Fallback** | If Mail doesn't focus, run `open -a "Mail"` in Terminal 1 by hand and pretend you said it twice. |

#### 2.3 — "Make this text bigger" (~2 s)

`zoom_text` is real now (it sends `Cmd++` via System Events keystroke,
layout-agnostic — works on AZERTY too). Whatever app is frontmost gets
zoomed. Best demoed with Mail.app frontmost from 2.2.

| | |
|---|---|
| **Say** | "Make this text bigger." |
| **See** | text in Mail jumps two notches. Halo: `adjusting the text size`. Spoken reply: *"Made the text bigger for you."* |
| **Log** | `[zoom_text] called with amount='bigger'` |
| **Fallback** | If the planner picks `amount='smaller'` (it sometimes mis-routes "agrandir" — see the bug fix in the skill description), say "make it bigger" rather than any French/ambiguous phrasing. |

#### 2.4 — "Did I get any emails today?" (~6 s)

This reads from the live Mail.app inbox (`MAIL_SOURCE=mailapp`). The
phishing email you planted as `msg-003` should be UNREAD.

| | |
|---|---|
| **Say** | "Did I get any emails today?" |
| **See** | Halo: `checking your inbox`. Xiexie reads each subject + sender out loud, ending with *"…one looks unusual to me — want me to take a closer look?"* The unusual one is flagged by cheap header heuristics (typosquat domain + ALL-CAPS subject + SPF fail), no LLM call needed. |
| **Log** | `skill_start name='read_emails'` → `skill_result` with the 3-line summary. |
| **Fallback** | `osascript -e 'tell application "Mail" to count messages of inbox whose read status is false'` returns `0`? Right-click the bait email in Mail → Mark as Unread (`⇧⌘U`). Or just flip `MAIL_SOURCE=demo` in `.env`, restart uvicorn, and the fixture takes over. |

#### 2.5 — "What does this third email say?" (~8 s)

This is the cursor-pointing money beat *outside* the verdict. You're
asking GLM-4.5V to read Mail.app pixels (occlusion-tolerant via
`CGWindowListCreateImage`) and emit a `[POINT:x,y|label]` marker on
the suspicious link.

| | |
|---|---|
| **Say** | "What does this third email say?" |
| **See** | Halo: `looking at your screen`. After ~2 s, Xiexie speaks the email body in plain English, **and** a chevron + label flag animates onto the suspicious link in Mail (works on either the in-browser `<CursorPointer />` or the native `PointerOverlay` from Terminal 2). The label is short — typically `"the link"` or `"this link"`. |
| **Log** | `[read_screen] post-activate bounds=(x, y, w, h) owner='Mail'` then `[read_screen] reply='…[POINT:1240,820\|the link]…'…` then `[read_screen] pointable=True`. |
| **Fallback** | `pointable=False` in the log? Mail is on a different Space — drag it back and retry (see Pre-flight §0). Or the screenshot is wallpaper (perms) — re-verify with `screencapture -x` and Cmd+Q Terminal. If the chevron lands in the wrong place, GLM rounded the coords wrong; just narrate over it. |

#### 2.6 — "Take a closer look at it" (~12 s) — the flagship

Stay quiet during this one. `analyze_email` fans out three tools
(`check_url`, `search_scam_intel`, header forensics) and feeds the
results to GLM-4.6 for the verdict. ~10–14 s on a warm cache.

| | |
|---|---|
| **Say** | "Take a closer look at it." (or "Analyze it.") |
| **See** | Halo: `studying that email` for the whole duration. Then: a full `<VerdictCard />` lands in the chat with VERDICT, three numbered SIGNS cards, the URL sandbox panel (redirect chain + landing fields), Cialdini pressure chips, and the "Tell Lisa about this" CTA. Marin reads the warm `speak_aloud` paragraph (*"Margaret, this is the fake Aetna renewal scam…"*). |
| **Log** | `skill_start name='analyze_email'` → after ~10 s `skill_result name='analyze_email'` and a `bus.broadcast_alert` line with `level='phishing'`. |
| **Fallback** | If GLM-4.6 times out or returns junk: planter restart not needed — just say "try again" and the planner re-fires. If the VerdictCard renders without confidence chips, the alert text didn't include "high confidence" — cosmetic only, plough through. **Don't** retry against a real URL — `aetnna-secure.com` is the fake fixture, urlscan + GSB are unkeyed in `.env`, latencies are unpredictable on real domains. |

#### 2.7 — "Yes, tell my daughter" (~3 s)

Right after the verdict lands, a `confirm` bubble appears under the
card: *"Want me to send Lisa a heads-up about this?"* Answer it.

| | |
|---|---|
| **Say** | "Yes, tell my daughter." (or click the **Tell Lisa** CTA on the card.) |
| **See** | Halo: `drafting the family note`. Mail.app comes to front with a fresh draft to Lisa, pre-filled with a 3-bullet summary of the verdict signs. **Xiexie does not click Send** — that's a Margaret-only action. |
| **Log** | `skill_start name='report_to_family'` (early-return path: ~200 ms, no fresh GLM call — the planner detects the affirmative + stashed follow-up). |
| **Fallback** | If Mail draft doesn't open, run `open mailto:lisa.chen@example.co.uk?subject=Heads-up` in Terminal 1 and narrate. |

#### 2.8 — "Thank you" + "Good night Xiexie" (~5 s)

Closes continuous mode and proves the breadth one last time.

| | |
|---|---|
| **Say (1)** | "Thank you." |
| **See (1)** | Header pill flips back to `listening for "Xiexie" or "computer"…`. The realtime channel is closed; passive wake listener re-armed. |
| **Say (2)** | "Xiexie, set a reminder for tomorrow 9am to call Lisa." |
| **See (2)** | Halo: `setting your reminder`. Reminders.app gets a new entry. |
| **Log** | wake-fire entry in chat, then `skill_start name='set_reminder'` with an ISO-8601 `when_iso`. |
| **Fallback** | Reminders.app permissions denied? `osascript -e 'tell application "Reminders" to make new reminder with properties {name:"smoke test"}'` will fail loudly — re-grant Automation in System Settings. |

---

### 3. Sanity checklist before you press record

Run through this once. Each line should be a visible "yes":

- [ ] `lsof -i:8787` shows one uvicorn
- [ ] `[overlay] backend WS connected` in Terminal 2
- [ ] Browser header: green dot `connected` + ember dot `listening for "Xiexie" or "computer"…`
- [ ] First wake-fire pulses the mic crimson and the realtime-mic claim succeeds (no `getUserMedia` red banner in DevTools)
- [ ] `data/demo/inbox.json` clean (`git status` shows no diff) — only relevant if you're on `MAIL_SOURCE=demo`
- [ ] No stale chevron/halo on screen from a previous run (`pkill -f overlay` then re-launch if there's a ghost)
- [ ] Mail.app on the SAME Space as Chrome (Mission Control swipe-up to confirm)
- [ ] Mail.app inbox has the bait email UNREAD (`⇧⌘U`)

---

## Part 2 — Live judging storyboard (5 minutes flat)

Print this. Stand up. Don't ad-lib.

| Time | What you say (verbatim) | What judges see | Why it scores |
|---|---|---|---|
| **0:00–0:10** | *"Last year, US seniors lost $3.4 billion to online scams. My grandmother almost lost three thousand. The fake email looked exactly like her bank. Her hand was hovering over the click."* | B-roll of an inbox, then cut to your Mac with Mail.app visible and the Xiexie tab open. | Practicality (real $3.4B problem). Presentation (emotional hook). |
| **0:10–0:30** | *"This is for her. We built Xiexie — an AI grandchild that lives on her Mac. Open source, voice-first, runs on GLM-4.6 from Z.AI."* | Header showing `connected` + `listening for "Xiexie" or "computer"…`. | Innovation (positioning — no other team is building for seniors). |
| **0:30–0:50** | *"Hey Xiexie, what time is it?"* (pause for reply) *"Open Mail."* | Wake fires → continuous channel opens. Marin replies in <1 s. Cursor halo bars dance while she speaks. Then `opening the app` halo + Mail.app comes forward. | Tech depth (wake → gpt-realtime → Marin TTS in one loop). Presentation (ambient halo = polish). |
| **0:50–1:30** | *"Make this text bigger."* (pause) *"Did I get any emails today?"* | Mail zooms in two notches. Halo flips to `checking your inbox`. Marin reads the 3-line inbox summary, ending *"…one looks unusual to me — want me to take a closer look?"* | Completeness (breadth + flagship in 40 s). Practicality (accessibility — bigger text is the senior killer feature). |
| **1:30–1:45** | *"What does this third email say?"* | Halo: `looking at your screen`. Marin reads the email aloud. **Chevron + label flag animates onto the suspicious link** in Mail. | Tech depth (GLM-4.5V `read_screen` with per-app `CGWindowListCreate-Image` capture, inline `[POINT:x,y]` parsing, image→screen-space coordinate translation). |
| **1:45–3:00** | *"Take a closer look at it."* (then **shut up** for 12 s — let the halo do the work) | Halo: `studying that email` for the whole duration. Then the **VerdictCard** lands: VERDICT phishing · 3 signs cards animate in one by one · URL sandbox panel reveals the 4-hop redirect · Cialdini pressure chips · "Tell Lisa about this" CTA. Marin reads the warm Margaret-friendly summary. | **All four criteria.** Innovation (multi-tool scam forensics composed by GLM-4.6). Tech depth (composite skill, parallel tools, graded verdict, three coordinated surfaces). Completeness (chat + halo + voice all firing in sync). Presentation (the Verdict Card is the money shot). |
| **3:00–3:30** | *"Yes, tell my daughter."* | Halo: `drafting the family note`. Mail.app draft opens to Lisa with a 3-bullet summary. Pause and read out: *"And critically — Xiexie never clicks Send. That's Margaret's call."* | Practicality (the family-loop angle no other team has). Presentation (the safety-by-design caveat lands trust). |
| **3:30–4:00** | *"This is what makes Xiexie different from a chatbot."* (open `data/wiki/preferences.md` in your editor) *"Every conversation, the agent edits a plain markdown file. Karpathy's LLM-Wiki pattern. We learned today that Margaret prefers larger text — see this commit. Next time, Xiexie offers it without being asked."* | Editor showing a recent diff in `preferences.md` (something like `+ prefers text two notches larger`). | Innovation (Karpathy LLM-Wiki — the technical signature, contrasts with everyone's RAG). Tech depth (auditable, user-owned memory). |
| **4:00–4:30** | *"Today this runs on GLM-4.6 for the verdict reasoning, GLM-4.5V for the screen pointing, OpenAI gpt-realtime for the voice, and faster-whisper as a fallback. Tomorrow it's all GLM — Z.AI ships glm-asr-2512 for STT, and we're packaging the .app via Tauri with a custom 'Xiexie' wake-word from openWakeWord."* | Stay on the editor / wiki view. Don't re-demo. | Tech depth (named the swap-out path). Innovation (sponsor lock — GLM end-to-end). |
| **4:30–5:00** | *"Xiexie. The AI grandchild that protects, remembers, and never sleeps. Open source, local-first, built on Z.AI. Thanks to the Z.AI mentor for the API access — if you'd like to chat about a Z.AI integration, find me at Station F all day."* | Cut to repo / README on screen. | Presentation (clean close + sponsor thank you + Edouard-as-a-person ask). |

**Backup beats** if you have 10 s of dead air during the verdict wait
(1:45–3:00):

- "While GLM-4.6 thinks, three tools are running in parallel — header
  forensics, URL sandbox, scam-intel grounding."
- "The model emits a graded verdict — phishing, suspicious, or clear —
  with confidence."
- "We never tell Margaret to click. Xiexie always asks."

---

## Part 3 — 30-second panic recipe (read top-down, do not skip)

If something crashes 60 seconds before you go on:

```bash
# 1. nuke everything
pkill -9 -f "uvicorn xiexie"; pkill -9 -f "overlay"
lsof -t -i:8787 | xargs -r kill -9; lsof -t -i:3000 | xargs -r kill -9

# 2. backend
cd /Users/edouardfoussier/code/gosim-hack/backend && \
  uv run --active uvicorn xiexie.main:app --port 8787 &

# 3. frontend
cd /Users/edouardfoussier/code/gosim-hack/app && pnpm dev &

# 4. hard-refresh Chrome (⌘⇧R) to re-mount the WS + wake listener.
# 5. if voice is still dead: flip MAIL_SOURCE=demo in .env and use the
#    mic button — the click-mic Whisper path bypasses gpt-realtime entirely.
```

If the verdict skill won't fire on stage, fall back to the curl
shortcut — it goes through the exact same bus, so the VerdictCard and
the alert pill still appear in the browser:

```bash
curl -s -X POST http://127.0.0.1:8787/plan-and-run \
  -H 'content-type: application/json' \
  -d '{"text":"analyze the suspicious email msg-003"}' | jq .
```

谢谢 🍀
