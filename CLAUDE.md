# CLAUDE.md — Xiexie dev harness

> This file is the **single source of truth** for how we build Xiexie during the
> GOSIM Agentic Hackathon (May 5–6, 2026, STATION F, Paris).
> Two days, solo. Read this when you're stuck. Update this when you decide.
>
> Sister doc: `WIKI_SCHEMA.md` is the **runtime memory schema** for the agent
> itself (Karpathy LLM-Wiki pattern). This file is for the *humans* building it.

---

## 1. Mission

Xiexie is a **voice-first, screen-aware computer-use agent for seniors** that
takes plain-English voice commands, executes them on the user's Mac (apps,
files, OS, websites), confirms before anything destructive, and **learns the
user a little more after every interaction** via a self-maintained markdown
wiki (Karpathy LLM-Wiki, April 2026).

> "Because the right answer to elderly tech anxiety is a computer
> you can simply thank."

---

## 2. Hackathon context (do not forget)

- **Event**: GOSIM Agentic Hackathon — STATION F, Paris — May 5–6, 2026
- **Team**: Xiexie (solo — Edouard Foussier)
- **Sponsor we target**: **Z.AI** (GLM-4.6 + GLM-4V). The Z.AI mentor is on-site
  and friendly. We optimise for **Z.AI Innovation Award ($2,000)**.
  GOSIM Builder/Architect awards are bonus, do not over-fit.
- **Submission**: GitHub repo + README + 3–5 min demo video. Top 10 do live
  demo (3 min + 2 min Q&A). Deployed demo is a plus, not required.
- **Judging (20% each)**: Innovation · Technical Depth · Completeness ·
  Practicality · Presentation. **Innovation is our signature lever** (per
  Edouard's call).

### What competing teams are doing (avoid overlap)

Scanned 46 registered teams. Adjacent but **different** angles already taken:
- *Showrunner* — multi-agent writers room for short drama
- *AIDO-Runtime* — typed action primitives for AI agents (infra)
- *DeepCritical* — biomedical critical analysis
- *Agentic Community Manager* — local community building
- *OpenClaw for Companies* — OpenClaw skill extension

**Nobody is doing computer-use for seniors.** That is our moat.

---

## 3. Scope — what we build, what we cut

### V1 skills (must work in demo)

7 named, deterministic skills wired to the planner:

| # | Skill                | Implementation (macOS)                          |
|---|----------------------|-------------------------------------------------|
| 1 | `open_app`           | `subprocess: open -a "Name"`                    |
| 2 | `find_file`          | `mdfind` (Spotlight) + filters from wiki        |
| 3 | `read_emails`        | AppleScript Mail OR Gmail via browser-use       |
| 4 | `set_reminder`       | `osascript` Reminders.app                       |
| 5 | `zoom_text`          | pyautogui Cmd+Plus / macOS zoom                 |
| 6 | `login_site`         | browser-use + creds from Keychain ref in wiki   |
| 7 | `daily_brief`        | composite (emails + calendar + wiki recurring)  |

### NOT in V1 (do not build)

- **Generic computer-use fallback** — when no skill matches, Xiexie says
  *"I don't know how to do that yet — I'm taking a note so I can learn"* and
  appends to `data/raw/unhandled_asks.md`. The wiki linter reviews these and
  proposes new skills. **This is on-brand** with the compounding-knowledge
  pitch. We do **not** code a vision+pyautogui open loop in V1.
- Windows port. macOS only for demo.
- Mobile. Desktop only.
- Multi-user. Single Margaret persona.
- Cross-language. English UX only (FR is post-hack).

---

## 4. Architecture

```
                      User voice
                          │
                  Whisper STT (faster-whisper local)
                          │
                          ▼
              ┌─────────────────────┐
              │  Planner (GLM-4.6)  │ ◀── Wiki Reader (memory/wiki.py)
              │  picks: skill X /   │
              │  none-of-the-above  │
              └────────┬────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
  ┌──────────┐              ┌────────────────────┐
  │  SKILLS  │              │  unhandled_asks.md │
  │ (named,  │              │  (logged + linter  │
  │ atomic)  │              │   proposes skills) │
  └────┬─────┘              └──────────┬─────────┘
       │                               │
       ▼                               │
  Confirmation gate (TTS asks)         │
       │                               │
       ▼                               │
  Skill executes (browser-use,         │
  AppleScript, mdfind, etc.)           │
       │                               │
       ▼                               ▼
       └──────────► Wiki Updater + Linter ◄──── data/raw/
                            │
                            ▼
                 Kokoro TTS spoken reply
```

### Why two-tier (skills + log-and-learn)

- **Skills** = reliable demo. Tested. Fast. Safe.
- **Log-and-learn** = on-brand wow factor. Even when Xiexie *can't* do
  something, the system **compounds knowledge about its own gaps** —
  perfectly aligned with the LLM-Wiki narrative.

### Memory: Karpathy LLM-Wiki literal

Three layers (see `WIKI_SCHEMA.md` for full schema):

```
data/
├── raw/               # immutable inputs
│   ├── transcripts/   # voice transcripts
│   ├── screenshots/   # vision captures
│   └── unhandled_asks.md
└── wiki/              # LLM-curated markdown, cross-referenced
    ├── user.md
    ├── family.md
    ├── healthcare.md
    ├── files.md
    ├── accounts.md
    ├── preferences.md
    └── recurring_tasks.md
```

After each session a **linter agent** (GLM-4.6 with the wiki + recent raw)
proposes patches: new facts, contradictions, gaps. We auto-apply low-risk
patches and surface high-risk ones.

---

## 5. Stack — committed

| Layer        | Choice                                  | Why                                             |
|--------------|-----------------------------------------|-------------------------------------------------|
| LLM          | `glm-4.6` (Z.AI)                        | Sponsor lock + best open OSS for tool-use       |
| Vision       | `glm-4v` (Z.AI)                         | Same provider; reads screenshots when needed    |
| LLM fallback | OpenAI `gpt-4o`                         | Dev-time only (until Z.AI key in hand)          |
| STT          | `faster-whisper` (local)                | Sub-second latency; zero network                |
| TTS          | Kokoro (local)                          | Warm voice, hackathon-friendly                  |
| TTS premium  | ElevenLabs                              | Optional final-video upgrade                    |
| Browser auto | `browser-use`                           | Mature, LLM-agnostic                            |
| OS auto      | pyautogui + AppleScript subprocess      | macOS demo target                               |
| Backend      | FastAPI + WebSockets                    | Async, simple, well-known                       |
| Frontend     | Next.js + shadcn/ui + Tailwind          | Clean overlay, deployable Vercel for jury       |
| Repo         | Monorepo, no Turborepo (overkill for 2d)| Simplicity                                      |

**No Electron / Tauri in V1.** UI runs as a normal Chrome PWA tab in a
corner of the screen. If we have spare time J2 morning, wrap in **Tauri** (1h
of work) for the final demo video aesthetic.

---

## 6. Time-boxed plan

> Today is **Tuesday May 5** (Day 1). Opening was 10:30; we are late-morning.
> Day 2 is Wednesday May 6, submission/demo same day evening.

### Day 1 — Tue May 5 (afternoon → night)

| Time          | Task                                                            |
|---------------|-----------------------------------------------------------------|
| 12:00–13:00   | Lunch + finalize CLAUDE.md, WIKI_SCHEMA, pre-seed Margaret wiki |
| 13:00–14:30   | Backend: FastAPI + LLM provider abstraction + GLM client        |
| 14:30–15:30   | Skill registry + skill 1: `open_app` (full E2E test)            |
| 15:30–17:00   | Voice loop: Whisper in + Kokoro out wired to Next.js UI         |
| 17:00–17:50   | Skill 2: `find_file` (mdfind) + skill 3: `set_reminder`         |
| 17:50–18:00   | **Checkpoint** — 1-min team update                              |
| 18:00–22:00   | Skill 4: `read_emails` (AppleScript Mail) + skill 5: `zoom_text`|
| 22:00–24:00   | Memory wiki R/W + planner picking skill from voice              |

### Day 2 — Wed May 6 (morning → submission)

| Time          | Task                                                            |
|---------------|-----------------------------------------------------------------|
| 08:30–10:00   | Skill 6: `login_site` (browser-use) + skill 7: `daily_brief`    |
| 10:00–11:30   | Wiki linter pass (compounding memory)                           |
| 11:30–13:00   | UI polish: voice waveform, action log, **wiki-growing banner**  |
| 13:00–14:30   | Lunch + scenario rehearsal (Margaret arc) — record 1st take     |
| 14:30–16:00   | Buffer / fix bugs / Tauri wrap if all green                     |
| 16:00–17:00   | Final demo video (3–5 min) — script in `docs/demo-script.md`    |
| 17:00–18:00   | Submission + slides + Q&A prep                                  |

### Hard cut list (in order — when we're behind)

Cut from the bottom up:
1. ✂️ Tauri wrap → leave as web tab
2. ✂️ Skill 6 (`login_site`) → fake login from wiki textually
3. ✂️ Skill 7 (`daily_brief`) → fake compose from skills 3+4
4. ✂️ Wiki linter live demo → show pre-baked diff in slides
5. ✂️ Voice TTS premium → use Kokoro only
6. ✂️ Skill 5 (`zoom_text`) → just narrate
7. ✂️ Skill 4 (`read_emails`) → narrate; show Mail.app screenshot
8. ✂️ ~~Voice STT live~~ — **never cut this, it is the demo**

If we're cut down to skills 1–3 only, the demo still works:
*open_app → find_file → set_reminder* + memory updating in real time.

---

## 7. Demo script (5 min, English) — "A morning with Margaret"

Persona: **Margaret, 74, USA, Mac user, daughter Lisa in London.**

| Beat            | Voice from Margaret                                | Xiexie does                                                               |
|-----------------|-----------------------------------------------------|---------------------------------------------------------------------------|
| 1. Wake & brief | *"Xiexie, what's on my plate today?"*              | `daily_brief`: 3 emails (Aetna, Lisa, promo); reminders; Lisa flight 4pm |
| 2. File find    | *"Find my last EDF bill, how much was it?"*        | `find_file` via mdfind → opens PDF → GLM-4V reads amount → "€87"          |
| 3. Email + form | *"Read me the Aetna email"*                        | `read_emails` → reads aloud → "want me to do the renewal together?"       |
| 4. Form fill    | *"Yes please"*                                     | `login_site` Aetna → asks fields plain English → wiki provides defaults → user corrects ("Dr. Smith now") → wiki updates **live, on screen** → submit |
| 5. OS skill     | *"Set me a reminder for 3:30pm to leave for SFO"*  | `set_reminder` → osascript Reminders → confirmed                          |
| 6. Accessibility| *"My eyes are tired, make this bigger"*            | `zoom_text` → screen scales                                               |
| 7. Wrap         | *"Xiexie."*                                        | Wiki linter pass shown: "Learned: Dr. Smith ; Lisa visits monthly ; prefers larger text after 2pm" |

**Money shot for the jury**: at beat 4, the wiki banner on screen literally
re-renders with the new fact Margaret just told the agent. That single
animation is the entire pitch in 2 seconds.

---

## 8. Risk log

| Risk                                   | Probability | Mitigation                                                  |
|----------------------------------------|-------------|-------------------------------------------------------------|
| Z.AI API rate limits in demo           | M           | Cache responses; fallback OpenAI key; pre-record backup vid |
| Voice latency too high                 | M           | Local-only pipeline (faster-whisper + Kokoro)               |
| Aetna/EDF real sites change/captcha    | H           | **Use a fake-form static page hosted locally** for demo     |
| macOS perms (mic, accessibility)       | H           | Pre-grant in System Settings; document in CLAUDE.md (§9)    |
| Demo crashes live at Q&A               | M           | Pre-recorded backup video ready; "let me show the take"     |
| Privacy concern from jury              | L           | Address proactively in pitch: local wiki, encrypted at rest |
| Skill scope creep                      | H           | This file. Read §3 before adding anything.                  |
| Spending 4h on Tauri packaging         | M           | Forbidden in V1. Web tab only. Tauri = J2 14:30+ only.      |

---

## 9. macOS perms checklist (do this before coding)

System Settings → Privacy & Security:
- [ ] Microphone → Terminal + Cursor + (Tauri later)
- [ ] Accessibility → Terminal + Cursor (for pyautogui keyboard)
- [ ] Automation → Terminal → System Events, Mail, Reminders, Calendar, Chrome
- [ ] Screen Recording → Terminal + Cursor (if vision agent reads desktop)
- [ ] Full Disk Access → Terminal (mdfind across `~/Documents/` etc.)

Test command:
```bash
osascript -e 'tell application "Reminders" to make new reminder with properties {name:"test xiexie"}'
```

---

## 10. Decisions log (ADR-style, append only)

### 2026-05-05 — Sponsor lock: Z.AI / GLM
Edouard knows the Z.AI mentor; GLM-4.6 is among the strongest open-source
LLMs for tool-use, which is *exactly* the muscle Xiexie exercises. We optimise
the architecture and pitch for the Z.AI Innovation Award ($2,000).

### 2026-05-05 — No robotics
SO-101 demo not feasible at Station F. Drop. Keep computer-use as the
embodiment angle.

### 2026-05-05 — Senior accessibility focus over generic productivity
The senior angle is universally relatable, emotionally compelling, and not
covered by any other registered team. Higher EV than another productivity bot.

### 2026-05-05 — Karpathy LLM-Wiki pattern as memory primitive
The agent's memory is plain markdown files, edited by the agent itself, with
a periodic linter pass. Auditable by the user. Compounds across sessions.
This is our **technical signature**.

### 2026-05-05 — No generic computer-use fallback in V1
Replaced by elegant log-and-learn pattern: "I don't know how yet — I'm taking
a note so I can learn." Logs to `data/raw/unhandled_asks.md`. Linter proposes
new skills. On-brand, lower risk than building a vision-driven click loop.

### 2026-05-05 — macOS-only demo, web-tab UI (no Tauri V1)
Save 1 day of dev. Acknowledge Windows port in pitch.

### 2026-05-05 — AMD hackathon: fork later
We focus 100% on GOSIM. Edouard will fork after submission for AMD.

---

## 11. Bug log (append only, prevent re-introducing)

> When you fix something tricky, write 1 line here so future-you doesn't
> redo the same hour of debugging.

- (none yet)

---

## 12. Pitch one-pager (cheat sheet for video)

**Hook (0:00–0:15)**
> "My grandmother spent 40 minutes trying to renew her health insurance
> online last month. She gave up and called me. This is for her."

**Demo (0:15–4:00)** — see §7

**Tech reveal (4:00–4:30)**
> "Xiexie's memory is plain markdown — Karpathy's LLM-Wiki pattern.
> It learns Margaret a little more every conversation. Auditable, portable,
> hers. Built on GLM-4.6 — the best open-source agentic model on the planet."

**Close (4:30–5:00)**
> "Today, computers expect humans to learn them. Xiexie flips it:
> the computer learns the human. Open source, local-first. Xiexie."

---

## 13. Quick reference

- Run backend: `cd backend && uv run uvicorn xiexie.main:app --reload`
- Run app: `cd app && pnpm dev`
- Wiki linter (manual): `cd backend && uv run python -m xiexie.memory.linter`
- Test a skill: `cd backend && uv run python -m xiexie.skills.<name>`
- Env vars: see `.env.example`. Copy to `.env` (gitignored).

