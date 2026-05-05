# Xiexie 谢谢

> The AI grandchild that protects, remembers, and never sleeps.

**GOSIM Agentic Hackathon 2026 · STATION F · Paris**
**Team: Xiexie (solo) · targeting Z.AI Innovation Award**

---

## TL;DR

Last year, US seniors lost **$3.4 billion** to online scams (FTC). Xiexie
sits on a senior's Mac as a voice-first AI grandchild that:

1. **Reads inbound emails out loud** and flags anything that looks unusual.
2. **Forensically analyses suspicious emails** — multi-tool reasoning over
   sender headers, sandboxed link captures, and live web scam intelligence,
   composed by GLM-4.6 into a graded plain-English verdict.
3. **Acts on Margaret's behalf** — archives the scam, drafts a heads-up
   email to her daughter Lisa, opens apps, sets reminders, makes text bigger.
4. **Learns Margaret a little more** after every conversation, via
   Andrej Karpathy's [LLM-Wiki pattern](https://newclawtimes.com/articles/karpathy-llm-knowledge-bases-agent-memory-beyond-rag) — plain markdown the user owns, that compounds across sessions instead of resetting.

> "When your real grandchild is busy, your computer can be the next best
> thing. Just say… *Xiexie*."

---

## The pitch in 5 minutes — "Scam Shield"

**Persona:** Margaret, 74, Palo Alto. Daughter Lisa in London.

```
00:00 ─ Hook (voice-over)
        "Last year, US seniors lost $3.4 billion to online scams. My
        grandmother almost lost three thousand. This is for her."

00:30 ─ "Xiexie, did I get any new emails?"
        → read_emails: 3 unread. One looks unusual.
          "Want me to take a closer look?"

01:30 ─ "Yes please."  ← THE SHOWPIECE
        → analyze_email runs three tools in parallel, UI shows live timeline:
          ✓ sender headers (SPF/DKIM/DMARC fail)
          ✓ URL sandbox (4-hop redirect to .ru → netlify fake login)
          ✓ web scam intel (FTC alert 2026-04-28 matches this template)

03:00 ─ Verdict Card animates in:
        VERDICT: phishing  (confidence: high)
        SIGNS:
          1. Sender domain `aetnna-secure.com` typosquats `aetna.com`.
          2. Link redirects 4 hops, asks for SSN + credit card.
          3. Pattern matches FTC alert from last week.
        RECOMMENDED:
          - Don't click. Don't pay.
          - Archive the email.
          - Tell Lisa.

03:45 ─ "Yes."
        → archive_email + report_to_family (mailto: drafted to Lisa)

04:00 ─ Wiki banner re-renders:
        scam_alerts.md  +1 entry · family.md  "alerted Lisa 13:23"

04:15 ─ "Make this bigger." + "Open Mail."
        → zoom_text + open_app — breadth in <10 s

04:45 ─ Close
        "Xiexie. The AI grandchild that protects, remembers, and never
        sleeps. Open source. Local-first. Built on GLM-4.6."
```

---

## Architecture (one diagram)

```
voice in → faster-whisper (local)
       ↓
   Planner (GLM-4.6) ◀── Wiki Reader (Karpathy LLM-Wiki, markdown)
       ↓
   ┌─── Tier-A · Scam Shield ──────────────────────────────────────┐
   │                                                                │
   │   read_emails  ─►  analyze_email  ◀─  search_scam_intel       │
   │                          │            (Tavily / fixture)      │
   │                          ◀────────  check_url                 │
   │                                     (no-JS fetch, redirect    │
   │                                      chain, form fields)      │
   │                          ▼                                    │
   │                   verdict (graded) ─►  archive_email          │
   │                                       report_to_family        │
   └────────────────────────────────────────────────────────────────┘
   ┌─── Tier-B · Breadth ───────────────────────────────────────────┐
   │   open_app · find_file · set_reminder · zoom_text             │
   └────────────────────────────────────────────────────────────────┘
       ↓                                          ↓
   no skill matched?                       Wiki Updater + Linter ◀── data/raw/
       ↓                                          ↓
   log to unhandled_asks.md                  scam_alerts.md auto-refresh
       ↓                                          ↓
       └──────────► Kokoro TTS (local) ──────────► spoken reply
```

See [`CLAUDE.md`](./CLAUDE.md) for the dev harness, scope, and risk log.
See [`WIKI_SCHEMA.md`](./WIKI_SCHEMA.md) for the runtime memory schema.

---

## Why this wins on the judging rubric

| Criterion (20% each) | How Xiexie scores                                                                  |
|----------------------|------------------------------------------------------------------------------------|
| **Innovation**       | Multi-tool scam forensics + LLM-Wiki memory + voice grandchild — combo unseen in the 46 teams |
| **Technical Depth**  | Composite agent: header forensics · URL sandbox · web grounding · GLM verdict · self-curating markdown memory · weekly linter |
| **Completeness**     | 9 working skills + Verdict Card + visible memory updates + voice round-trip       |
| **Practicality**     | $3.4B/yr elder-fraud problem, real persona, real macOS demo + Mail.app backup     |
| **Presentation**     | Emotional opening (grandmother story), Verdict Card showpiece, GLM as backbone     |

---

## Stack

- **LLM:** [GLM-4.6](https://z.ai) (Z.AI), GLM-4V for vision · OpenAI fallback for dev
- **Voice:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (STT) · [Kokoro](https://github.com/hexgrad/kokoro) (TTS)
- **Computer use:** [`browser-use`](https://github.com/browser-use/browser-use) · pyautogui · AppleScript via `osascript` · `mdfind`
- **Scam forensics:** httpx (no-JS URL sandbox) · [Tavily Search](https://tavily.com) (web scam intel, fixture fallback) · header-auth heuristics
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
│       ├── skills/       # Tier-A (scam-shield) + Tier-B (breadth) + stubs
│       ├── memory/       # wiki R/W + linter
│       └── planner/      # voice → skill selection
├── app/                  # Next.js overlay UI
│   ├── app/              # routes
│   └── components/       # voice button, transcript, verdict card, wiki banner
└── data/
    ├── demo/             # fake inbox fixture for the live demo
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
