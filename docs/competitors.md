# Competitor & prior-art landscape (internal — Q&A backup, not for public pitch)

> The public pitch (CLAUDE.md §12, README) deliberately does **not** name
> these. The decision is documented in CLAUDE.md §10 (ADR
> "2026-05-05 — Pitch positioning: do NOT name competitors"). This file
> exists so we have prepared answers if a jury member or attendee asks
> "isn't this just X?".

Last updated: 2026-05-05 (post initial scan).
Re-scan checklist: re-run after sub-agents complete to refine the diff.

---

## Direct open-source overlap (2026)

### ElderShield · [github.com/syrm4/eldershield](https://github.com/syrm4/eldershield)
- **What it is**: PHP/MySQL/Ollama platform where seniors *submit* a
  suspicious message and a caregiver dashboard reviews it.
- **License**: MIT.
- **Reactive vs proactive**: ElderShield = reactive (user uploads). Xiexie =
  proactive (scans inbound continuously).
- **Stack**: PHP web app vs our voice-first desktop agent.
- **Q&A answer**: "ElderShield is great for caregivers reviewing reported
  messages. Xiexie sits on the senior's machine and catches scams *before*
  they need to be reported. Different layer of the same problem."

### PhishNet — Check Before You Click · UC Berkeley i-School ([page](https://www.ischool.berkeley.edu/projects/2026/phishnet-check-you-click))
- **What it is**: Chrome extension for Gmail using a two-stage RAG pipeline
  on AWS Bedrock. Three risk tiers (safe / suspicious / dangerous).
- **Sub-agent reading source code in flight** — see
  `/tmp/xiexie-research/phishnet-report.md` once available.
- **Q&A answer**: "PhishNet's senior-friendly UX is excellent — we adopted
  the three-tier risk taxonomy from their work. Where we differ: voice-first
  (no Chrome extension required), works on native Mail.app too, runs on a
  local open-source model (GLM-4.6) instead of AWS Bedrock, and the wiki
  memory means it knows *this senior's* doctor, accounts, and family."

### Guardian Angel · [github.com/muhammadnavas/Guardian_Angel](https://github.com/muhammadnavas/Guardian_Angel)
- **What it is**: AutoGen multi-agent system (4–7 agents) analysing audio
  calls + screenshots. Gradio UI. MIT license, Python.
- **Sub-agent reading source code in flight** — see
  `/tmp/xiexie-research/guardian-angel-report.md` once available.
- **Closest architectural relative**.
- **Q&A answer**: "Guardian Angel showed us multi-agent scam analysis is
  the right pattern — we composed our skills around the same idea. Two
  things we add: (1) the Karpathy LLM-Wiki memory, so the agent learns
  *this user* over sessions; (2) it actually acts on the user's machine —
  archives the email, alerts family, opens apps."

### VerdictMail · [github.com/ascarola/verdictmail](https://github.com/ascarola/verdictmail)
- **What it is**: IMAP IDLE daemon, multi-stage enrichment (SPF/DKIM/DMARC
  + VirusTotal), supports OpenAI/Anthropic/Ollama. Web UI.
- **Sub-agent reading source code in flight** — see
  `/tmp/xiexie-research/verdictmail-report.md` once available.
- **Q&A answer**: "VerdictMail's enrichment pipeline is solid — we're using
  similar header-auth verification. Difference: we're not server-side. Xiexie
  lives on the senior's machine, talks to them in their voice, and acts."

### ReplyTrap · [github.com/mlapis/replytrap](https://github.com/mlapis/replytrap)
- **What it is**: Ruby scambaiting suite — engages scammers with fake personas.
- **Not relevant** — opposite use-case (offensive/research vs defensive/protective).

---

## Closed-source / commercial overlap

### Ask Grace · [askgrace.org](https://askgrace.org/)
- **What it is**: Free AI companion for seniors. Detects common scams (IRS
  calls, fake prizes, tech support fraud), warns before sharing money/info.
  Also: friendly conversation, health guidance, medication reminders,
  emergency calling.
- **The closest competitor to our pitch.** Acknowledge if asked.
- **Q&A answer**: "Ask Grace is wonderful — we share the values. Where Xiexie
  is different: (1) it runs as software *on the senior's existing computer*,
  not as a separate companion product, so it doesn't require a new device or
  account; (2) the Karpathy LLM-Wiki memory makes it auditable — Margaret can
  literally read what the agent knows about her in plain markdown; (3) it's
  open-source on a sovereign open-source LLM (GLM-4.6), with a local-first
  architecture that the user owns end-to-end."

### GrandPad + Grandie · [grandpad.net](https://grandpad.net)
- **What it is**: Senior-specific tablet with a built-in AI companion
  (Grandie). 60k+ chats since launch. No specific scam-shield feature.
- **Different segment**: dedicated hardware. Xiexie = on the existing Mac.

### Eldr + Elda
- Smart-glasses wearable AI companion. Different form factor.

### Telikin
- Simplified PC for seniors. Closest to Xiexie's *delivery surface* (a PC),
  but no AI agent — pre-AI product.

---

## Free-tier APIs we wire (already in code)

| API                        | Used in              | Free tier                                         |
|----------------------------|----------------------|---------------------------------------------------|
| urlscan.io                 | `check_url`          | Yes; key lifts rate limit                         |
| Google Safe Browsing v4    | `check_url`          | Yes (non-commercial)                              |
| EmailRep.io                | `read_emails`, `analyze_email` | Yes; key for higher limits             |
| Tavily (already wired)     | `search_scam_intel`  | Yes; fixture fallback for demo                    |

## Free-tier APIs we considered but didn't wire (V2)

| API                        | Why deferred                                        |
|----------------------------|-----------------------------------------------------|
| URLhaus (abuse.ch)         | Cross-references with urlscan transitively         |
| VirusTotal Public          | 4 req/min limit too tight for live demo            |
| FTC Consumer Blog RSS      | Linter automation post-hack                        |
| AARP Fraud Watch           | No public API; would need scrape                   |
| Cybermalveillance.gouv     | French only; wait for FR localisation             |

---

## How to refresh this file

1. After sub-agents complete, integrate their findings (especially the
   "what we should reuse" sections) into the relevant Q&A answers above.
2. Re-search GitHub `senior elder scam protection` quarterly post-hack.
3. Keep this file *internal* — never link it from the public pitch.
