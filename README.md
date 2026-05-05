# Xiexie 谢谢

> A voice-first computer-use agent for seniors that learns its user, one
> conversation at a time.

**GOSIM Agentic Hackathon 2026 · STATION F · Paris**
**Team: Xiexie (solo) · targeting Z.AI Innovation Award**

---

## TL;DR

Xiexie sits on a senior's Mac, listens for plain-English voice commands, and
**does** things — opens apps, finds files, fills forms, replies to emails,
sets reminders. Nothing new there.

What is new: Xiexie's memory is a **markdown wiki it maintains itself**
(Andrej Karpathy's LLM-Wiki pattern, April 2026). Every session, the agent
learns Margaret a little more — her doctor's name, where she keeps her
invoices, what time her eyes get tired. The wiki is plain text. Margaret
owns it. She can read and edit it. It compounds across sessions instead of
resetting on every query.

> "Today, computers expect humans to learn them.
> Xiexie flips it: the computer learns the human."

---

## The pitch in 5 minutes

**Persona:** Margaret, 74, lives alone in California, daughter Lisa in London.

```
00:00 ─ "Xiexie, what's on my plate today?"
        → daily_brief: 3 emails, Lisa's flight at 4pm, EDF bill day

00:45 ─ "Find my last EDF bill, how much was it?"
        → mdfind → opens PDF → vision reads "€87"

01:45 ─ "Read me the Aetna email"
        → reads aloud → "want me to do the renewal together?"

02:15 ─ "Yes please"
        → opens form → asks fields in plain English →
          wiki provides defaults → Margaret corrects ("Dr. Smith now") →
          ★ wiki re-renders live with the new fact ★ → submits

03:30 ─ "Set a reminder for 3:30pm to leave for SFO"
        → osascript Reminders → done

04:00 ─ "My eyes are tired, make this bigger"
        → zoom → done

04:30 ─ "Xiexie."
        → linter pass: "Learned: Dr. Smith ; Lisa visits monthly ;
          prefers larger text after 2pm"
```

---

## Architecture (one diagram)

```
voice in → faster-whisper (local)
       ↓
   Planner (GLM-4.6) ←── Wiki Reader (Karpathy LLM-Wiki, markdown)
       ↓
   Skill registry ─────► open_app · find_file · read_emails ·
                         set_reminder · zoom_text · login_site ·
                         daily_brief
       ↓                       ↓
   no skill matched?    skill executes (browser-use, AppleScript, mdfind)
       ↓                       ↓
   log to unhandled_asks.md    Wiki Updater + Linter ←── data/raw/
       ↓                       ↓
       └────────► Kokoro TTS (local, warm voice) → spoken reply
```

See [`CLAUDE.md`](./CLAUDE.md) for the dev harness, scope, and risk log.
See [`WIKI_SCHEMA.md`](./WIKI_SCHEMA.md) for the runtime memory schema.

---

## Why this wins on the judging rubric

| Criterion (20% each) | How Xiexie scores                                                                  |
|----------------------|------------------------------------------------------------------------------------|
| **Innovation**       | Computer-use + LLM-Wiki memory + senior-first UX — combo unseen in the 46 teams    |
| **Technical Depth**  | Agent loop · vision · tool-use · self-curating markdown memory · linter agent      |
| **Completeness**     | 7 working skills + visible memory updates + voice round-trip end-to-end            |
| **Practicality**     | Real digital divide problem, real persona, real demo on real macOS                 |
| **Presentation**     | Emotional opening (grandmother), live wiki growth on screen, GLM as backbone       |

---

## Stack

- **LLM:** [GLM-4.6](https://z.ai) (Z.AI), GLM-4V for vision · OpenAI fallback for dev
- **Voice:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (STT) · [Kokoro](https://github.com/hexgrad/kokoro) (TTS)
- **Computer use:** [`browser-use`](https://github.com/browser-use/browser-use) · pyautogui · AppleScript via `osascript` · `mdfind`
- **Memory:** plain markdown (Karpathy LLM-Wiki, [Apr 2026](https://newclawtimes.com/articles/karpathy-llm-knowledge-bases-agent-memory-beyond-rag))
- **Backend:** Python 3.12 · FastAPI · WebSockets
- **Frontend:** Next.js 15 · shadcn/ui · Tailwind
- **Target OS for demo:** macOS (Sequoia)

---

## Repo layout

```
.
├── CLAUDE.md             # dev harness (read me first)
├── WIKI_SCHEMA.md        # runtime memory schema
├── README.md             # you are here
├── backend/              # Python — planner, skills, voice, memory
│   └── xiexie/
│       ├── main.py       # FastAPI + WebSockets
│       ├── llm/          # provider abstraction (GLM + OpenAI fallback)
│       ├── voice/        # STT + TTS
│       ├── skills/       # 7 named skills + registry
│       ├── memory/       # wiki R/W + linter
│       └── planner/      # voice → skill selection
├── app/                  # Next.js overlay UI
│   ├── app/              # routes
│   └── components/       # voice button, transcript, wiki banner
└── data/
    ├── raw/              # immutable transcripts + screenshots + unhandled
    └── wiki/             # the agent's living markdown memory
```

---

## Running locally

> macOS Sequoia tested. Pre-grant Mic, Accessibility, Automation, Screen
> Recording, Full Disk Access to your terminal — see [`CLAUDE.md` §9](./CLAUDE.md#9-macos-perms-checklist-do-this-before-coding).

```bash
# 1. Backend
cd backend
uv sync
cp ../.env.example ../.env  # fill ZAI_API_KEY (or OPENAI_API_KEY for dev)
uv run uvicorn xiexie.main:app --reload --port 8787

# 2. Frontend (in another terminal)
cd app
pnpm install
pnpm dev   # http://localhost:3000
```

Speak. Watch the wiki grow.

---

## Acknowledgements

- Inspiration: [Clicky](https://www.clicky.so/) (the "AI buddy on your Mac"
  paradigm) — we re-thought it for accessibility instead of pro creators.
- Memory pattern: [Karpathy LLM-Wiki](https://newclawtimes.com/articles/karpathy-llm-knowledge-bases-agent-memory-beyond-rag) (Apr 2026).
- Sponsors: **Z.AI** (GLM), MiniMax, Moonshot Kimi — for the open-source AI we love.

---

## License

MIT (see `LICENSE`).
