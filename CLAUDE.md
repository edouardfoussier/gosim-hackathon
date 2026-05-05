# CLAUDE.md — Xiexie dev harness

> This file is the **single source of truth** for how we build Xiexie during the
> GOSIM Agentic Hackathon (May 5–6, 2026, STATION F, Paris).
> Two days, solo. Read this when you're stuck. Update this when you decide.
>
> Sister doc: `WIKI_SCHEMA.md` is the **runtime memory schema** for the agent
> itself (Karpathy LLM-Wiki pattern). This file is for the *humans* building it.

---

## 1. Mission

Xiexie is a **voice-first AI grandchild for seniors** that protects them
from online scams, helps them act on their computer with their voice, and
**learns the user a little more after every interaction** via a self-
maintained markdown wiki (Karpathy LLM-Wiki, April 2026).

The flagship use-case is **scam detection on incoming emails** — multi-tool
reasoning over sender headers, sandboxed URL captures, and web-grounded
scam intelligence — with graded verdicts in plain English and an option
to alert the user's family.

> "When your real grandchild is busy, your computer can be the next best
> thing. Just say… *Xiexie*."

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

### V1 — Scam Shield flagship + breadth beats

**Tier A — Scam Shield (THE flagship — must be flawless in demo):**

| # | Skill                  | Implementation                                                |
|---|------------------------|---------------------------------------------------------------|
| 1 | `read_emails`          | Reads from `data/demo/inbox.json` (fake) + AppleScript Mail   |
| 2 | `analyze_email`        | Composite: header forensics + URL sandbox + web search + GLM verdict |
| 3 | `check_url`            | Playwright headless redirect chain + landing capture (mock for demo URLs) |
| 4 | `search_scam_intel`    | Tavily web search wrapper (or fixture fallback)               |
| 5 | `archive_email`        | AppleScript Mail OR fake-inbox JSON mutation                  |
| 6 | `report_to_family`     | `mailto:` to family member from wiki                          |

**Tier B — Breadth beats (show Xiexie does more than scam-shield):**

| # | Skill                | Implementation                                  |
|---|----------------------|-------------------------------------------------|
| 7 | `open_app`           | `subprocess: open -a "Name"`                    |
| 8 | `find_file`          | `mdfind` (Spotlight) + filters from wiki        |
| 9 | `set_reminder`       | `osascript` Reminders.app                       |
| 10| `zoom_text`          | pyautogui Cmd+Plus / macOS zoom                 |

### NOT in V1 (do not build)

- **Form completion** — useful but not novel; demoted to "what's next" in pitch
- **Password manager via MCP** — postponed; the wiki's Keychain-ref pattern
  gestures at it
- **`login_site`** — stays as a stub; we do not implement live auth in V1
- **`daily_brief` composite** — degraded; we use the simpler `read_emails`
- **Generic computer-use fallback** — when no skill matches, Xiexie says
  *"I don't know how to do that yet — I'm taking a note so I can learn"* and
  appends to `data/raw/unhandled_asks.md`. The linter proposes new skills.
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

| Time          | Task                                                                   |
|---------------|------------------------------------------------------------------------|
| 12:00–13:00   | Lunch + finalize CLAUDE.md (post Scam-Shield pivot), seed wiki         |
| 13:00–14:00   | Backend up (already scaffolded); fake `data/demo/inbox.json` ready     |
| 14:00–15:30   | `read_emails` real impl (fake inbox) + `archive_email`                 |
| 15:30–17:00   | `check_url` (Playwright headless + mock for demo URL) + `search_scam_intel` (Tavily) |
| 17:00–17:50   | `analyze_email` composite — chains URL + intel + GLM verdict prompt    |
| 17:50–18:00   | **Checkpoint** — 1-min team update                                     |
| 18:00–20:00   | Voice loop in browser: Web Audio capture → POST `/transcribe` + TTS playback |
| 20:00–22:00   | Frontend: **Verdict Card** component (visual showpiece for beat 1:30→3:00) |
| 22:00–24:00   | Frontend: **Wiki-growing banner** + scam_alerts panel; rehearsal #1    |

### Day 2 — Wed May 6 (morning → submission)

| Time          | Task                                                                   |
|---------------|------------------------------------------------------------------------|
| 08:30–10:00   | `report_to_family` real (mailto / Mail.app); breadth skills `zoom_text`, `find_file` polish |
| 10:00–11:30   | Linter wired live: scam_alerts.md weekly refresh, demo button "Lint now" |
| 11:30–13:00   | UI polish: animations on verdict reveal, signs-list reveal one by one   |
| 13:00–14:30   | Lunch + scenario rehearsal **×3** — record 1st take of demo video      |
| 14:30–16:00   | Buffer: fix bugs / Tauri wrap if all green / final inbox content tweaks |
| 16:00–17:00   | Final demo video (3–5 min) — script in §7                              |
| 17:00–18:00   | Submission + slides + Q&A prep                                         |

### Hard cut list (in order — when we're behind)

Cut from the bottom up:
1. ✂️ Tauri wrap → leave as web tab
2. ✂️ Real Playwright in `check_url` → use mock fixture for demo URL only
3. ✂️ Tavily live in `search_scam_intel` → use fixture intel for demo only
4. ✂️ `report_to_family` real send → fake confirmation toast
5. ✂️ Live wiki linter button → show pre-baked diff in slides
6. ✂️ Voice TTS premium (ElevenLabs) → Kokoro / `say` only
7. ✂️ Tier-B breadth beats (`zoom_text`, `find_file`) → narrate, screenshot
8. ✂️ Wiki-growing banner animation → static screenshot in slides
9. ✂️ ~~Verdict Card visual~~ — **never cut, it is the money shot**
10. ✂️ ~~Voice STT live~~ — **never cut, it is the demo**
11. ✂️ ~~`analyze_email` flagship~~ — **never cut, it is the project**

If we're cut down to **just** `read_emails + analyze_email + verdict card`,
the demo still works and still wins on innovation + practicality.

---

## 7. Demo script (5 min, English) — "Scam Shield"

Persona: **Margaret, 74, USA, Mac user, daughter Lisa in London.**

| Beat              | Voice / state                                                | Xiexie does                                                                 |
|-------------------|--------------------------------------------------------------|-----------------------------------------------------------------------------|
| **0:00 Hook**     | (voice-over, B-roll of an inbox)                             | "Last year, US seniors lost **$3.4 billion** to online scams. My grandmother almost lost $3,000. This is for her."                  |
| **0:30 Inbox**    | *"Xiexie, did I get any new emails?"*                        | `read_emails` from `data/demo/inbox.json` → "3 new. **One looks unusual to me.** Want me to take a closer look?"                  |
| **1:30 Analysis (showpiece)** | *"Yes, please."*                                | `analyze_email` runs three tools in parallel — UI shows live timeline:  ✓ sender headers · ✓ URL sandbox · ✓ web scam intel  |
| **3:00 Verdict**  | (silent — Verdict Card animates in)                          | "**This is almost certainly a phishing scam.** Three signs:  1. Sender domain is `aetnna-secure.com`, not `aetna.com`.  2. The link redirects through 4 hops to an IP in Russia.  3. This template was reported on FTC last week. **Don't click. Don't pay.** Want me to archive it and tell Lisa?" |
| **3:45 Action**   | *"Yes."*                                                     | `archive_email` (fixture mutation) + `report_to_family` → mailto Lisa with summary |
| **4:00 Memory**   | (silent)                                                     | Wiki banner re-renders: `scam_alerts.md` adds the template; `family.md` notes "alerted Lisa 2026-05-05 13:23". |
| **4:15 Breadth**  | *"Make this bigger."* + *"Open Mail."*                       | `zoom_text` + `open_app` rapid-fire — show breadth in <10 s                |
| **4:45 Close**    | (voice-over)                                                 | "Xiexie. The AI grandchild that protects, remembers, and never sleeps. Open source. Local-first. Built on **GLM-4.6**." |

**The money shot** = beat 1:30 → 3:00. The Verdict Card with three signs
revealing one by one, evidence chips highlighted, action buttons emerging.
That single 90-second sequence is the entire pitch.

**Backup track** for Q&A: switch from fake-inbox demo to real Mail.app —
analyze a real recent email Edouard plants the night before. Proves it's
not a slideshow.

---

## 8. Risk log

| Risk                                   | Probability | Mitigation                                                  |
|----------------------------------------|-------------|-------------------------------------------------------------|
| Z.AI API rate limits in demo           | M           | Cache responses; fallback OpenAI key; pre-record backup vid |
| Voice latency too high                 | M           | Local-only pipeline (faster-whisper + Kokoro)               |
| `check_url` Playwright flakey on stage | H           | **Mock fixture for the demo URL**; real Playwright = bonus  |
| Tavily rate limit / down               | M           | **Fixture intel for demo URL**; real Tavily = bonus         |
| **False positive on a real email**     | H           | Verdict gradation (`safe`/`suspicious`/`phishing`); confidence shown; never assert "scam" below high conf |
| **False negative (miss a real scam)**  | M           | Multi-signal weighing in analyze_email prompt; demo doesn't hide this — pitch acknowledges "we're a second pair of eyes, not infallible" |
| macOS perms (mic, accessibility)       | H           | Pre-grant in System Settings; see §9                        |
| Demo crashes live at Q&A               | M           | Pre-recorded backup video ready; "let me show the take"     |
| Privacy concern from jury              | M           | Address proactively: local wiki, no upload, family alerts opt-in |
| Skill scope creep                      | H           | This file. Read §3 before adding anything.                  |
| Spending 4h on Tauri packaging         | M           | Forbidden in V1. Web tab only. Tauri = J2 14:30+ only.      |
| Form-fill / passwd-mgr scope creep back| M           | Both belong to V2 only. Mention in pitch ("what's next") only. |

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

### 2026-05-05 (afternoon) — **PIVOT: Scam Shield as flagship use-case**
Emerging from Edouard's Q on protective use-cases. Reasons for the pivot:
1. *Hook*: "$3.4B lost to elder scams in 2023 (FTC)" + grandmother story is
   far stronger emotionally than "fill a form".
2. *Innovation*: multi-tool reasoning (headers + sandbox + web search +
   verdict) is a much richer architecture than form-fill autofill.
3. *Z.AI fit*: GLM-4.6 excels at multi-step tool composition with grounded
   reasoning — exactly the muscle Scam Shield exercises.
4. *Differentiation*: 0 of the 46 registered teams target elder protection.
5. *Family angle*: `report_to_family` adds a tear-jerker beat that no other
   demo will have.

What pivots:
- Demo arc rewritten in §7 around scam analysis as the showpiece.
- New Tier-A skills: `read_emails` (real, fake-inbox-backed), `analyze_email`,
  `check_url`, `search_scam_intel`, `archive_email`, `report_to_family`.
- Tier-B "breadth beats" reduced to `open_app` + `zoom_text` (+ optional
  `find_file`, `set_reminder` if time).
- Form-fill and password-manager use-cases moved to "what's next" in pitch.
- New wiki section: `data/wiki/scam_alerts.md` — populated by linter weekly.

### 2026-05-05 (afternoon) — Name locked: **Xiexie**
Considered "GrandChAId" (clever pun, but visual-only and weaker wake-word).
Kept Xiexie because (a) team name continuity, (b) phoneme-distinct wake-word,
(c) sponsor-cultural alignment, (d) the *user thanks the protector* arc.
Pitch narrative still uses "AI grandchild" framing without renaming.

### 2026-05-05 (afternoon) — Demo inbox: fake primary + real Mail.app backup
Primary demo runs against `data/demo/inbox.json` for full reproducibility.
For Q&A robustness, Edouard also plants a real test email in his Mail.app
the night before; we can swap to Mail.app live if a judge asks.

---

## 11. Bug log (append only, prevent re-introducing)

> When you fix something tricky, write 1 line here so future-you doesn't
> redo the same hour of debugging.

- (none yet)

---

## 12. Pitch one-pager (cheat sheet for video)

**Hook (0:00–0:30)**
> "Last year, US seniors lost **$3.4 billion** to online scams. My grand-
> mother almost lost three thousand. The fake email looked exactly like
> her bank. Her hand was hovering over the click. **This is for her.**"

**Demo (0:30–4:15)** — see §7

**Tech reveal (4:15–4:45)**
> "Xiexie reasons over email headers, sandboxed URLs, and live web scam
> intelligence — composed by GLM-4.6 in a single multi-tool agent loop.
> Its memory is plain markdown — Karpathy's LLM-Wiki pattern, owned by
> the user, growing every conversation. Open source. Local-first."

**Close (4:45–5:00)**
> "When your real grandchild is busy, your computer can be the next best
> thing. **Xiexie** — the AI grandchild that protects, remembers, and
> never sleeps."

---

## 13. Quick reference

- Run backend: `cd backend && uv run uvicorn xiexie.main:app --reload`
- Run app: `cd app && pnpm dev`
- Wiki linter (manual): `cd backend && uv run python -m xiexie.memory.linter`
- Test a skill: `cd backend && uv run python -m xiexie.skills.<name>`
- Env vars: see `.env.example`. Copy to `.env` (gitignored).

