# WIKI_SCHEMA.md — Xiexie runtime memory schema

> This file defines the schema and conventions of the **agent's own memory**
> (not our dev harness — that's `CLAUDE.md`).
>
> Pattern: **Andrej Karpathy's LLM-Wiki** (April 2026). Three-layer
> architecture where the agent reads raw sources, compiles them into a
> structured wiki, and reasons over the compiled layer.
>
> The wiki is **plain markdown**. It is owned by the user. It is auditable
> and editable by hand. Xiexie reads it before every plan and writes to it
> after every interaction.

---

## 1. The three layers

```
data/
├── raw/                          # LAYER 1: immutable inputs
│   ├── transcripts/              #   <ts>-<intent>.md   (one per session)
│   ├── screenshots/              #   <ts>-<context>.png (vision captures)
│   └── unhandled_asks.md         #   user requests Xiexie could not fulfil
│
├── wiki/                         # LAYER 2: LLM-curated, cross-referenced
│   ├── INDEX.md                  #   table of contents + last-updated stamps
│   ├── user.md                   #   identity, age, location, contacts
│   ├── family.md                 #   relatives + relationships
│   ├── healthcare.md             #   doctors, plans, meds, allergies
│   ├── files.md                  #   where things live, naming conventions
│   ├── accounts.md               #   websites + Keychain refs (no plaintext!)
│   ├── preferences.md            #   accessibility, defaults, habits
│   └── recurring_tasks.md        #   monthly bills, weekly calls, etc.
│
└── (this file: WIKI_SCHEMA.md)   # LAYER 3: schema & conventions
```

**Layer 1** is append-only and the source of truth.
**Layer 2** is the agent's compiled understanding.
**Layer 3** (this doc) is the grammar.

---

## 2. Front matter (every wiki file)

```markdown
---
slug: healthcare
title: Healthcare
last_updated: 2026-05-05T14:23:00Z
last_updated_by: agent          # agent | user
confidence: high                # high | medium | low
related: [user, family, recurring_tasks]
---
```

Required keys: `slug`, `title`, `last_updated`. Others optional.

---

## 3. Body conventions

### 3.1 Atomic facts as bullets, never prose

```markdown
- Primary care physician: **Dr. Sarah Smith** (since 2026-04-12)
  - Clinic: Stanford Health · Palo Alto, CA
  - Phone: (650) 555-0188
  - Replaces: Dr. Patel (was PCP 2022–2026-04)
```

Each fact = one bullet, one line of prose max. Sub-bullets for context.
**Edits are append-friendly**; old facts stay as struck-through history when
relevant.

### 3.2 Cross-references with `[[wiki:slug#anchor]]`

```markdown
- Daughter: **Lisa** ([[wiki:family#lisa]]) lives in London
- Aetna login at [[wiki:accounts#aetna]]
- Pays EDF on the 5th of each month — see [[wiki:recurring_tasks#edf]]
```

Linter resolves these and warns on dangling references.

### 3.3 Confidence and provenance

When the agent infers (not directly told), tag it:

```markdown
- (inferred, low conf) Likely prefers larger text after 2pm
  — observed 3× in transcripts/2026-05-{03,04,05}*.md
```

User-confirmed facts have no tag.

### 3.4 Secrets — never in plaintext

```markdown
- Aetna login
  - Username: m.smith@example.com
  - Password: [Keychain ref: `xiexie/aetna`]   # NEVER plaintext
```

Skill `login_site` reads the Keychain at runtime, not the wiki.

---

## 4. INDEX.md — agent's table of contents

Auto-maintained by the linter. Looks like:

```markdown
# Xiexie wiki — INDEX

| File                  | Title              | Last updated         |
|-----------------------|--------------------|----------------------|
| user.md               | User profile       | 2026-05-05T14:23:00Z |
| family.md             | Family             | 2026-05-05T13:55:00Z |
| healthcare.md         | Healthcare         | 2026-05-05T14:23:00Z |
| files.md              | Files & locations  | 2026-05-05T11:00:00Z |
| accounts.md           | Online accounts    | 2026-05-04T18:00:00Z |
| preferences.md        | Preferences        | 2026-05-05T14:25:00Z |
| recurring_tasks.md    | Recurring tasks    | 2026-05-04T20:00:00Z |
```

The planner reads INDEX.md first, then opens only the wiki files relevant to
the current intent — keeps context lean.

---

## 5. The linter (compounding pass)

A standalone GLM-4.6 call run after each session (and on demand):

**Input:**
- All of `data/wiki/*.md`
- Recent `data/raw/transcripts/*.md` (last N sessions)
- Recent `data/raw/unhandled_asks.md` entries

**Output (structured):**
```jsonc
{
  "patches": [
    {
      "file": "wiki/healthcare.md",
      "kind": "add",
      "anchor": "primary-care",
      "content": "- Switched PCP from Dr. Patel to Dr. Smith on 2026-05-05",
      "confidence": "high",
      "evidence": "transcripts/2026-05-05T14-21-aetna.md L42"
    }
  ],
  "contradictions": [
    { "files": ["preferences.md", "transcripts/..."], "summary": "..." }
  ],
  "skill_proposals": [
    { "ask": "summarize this article aloud", "frequency": 3, "name_hint": "read_article" }
  ]
}
```

- High-confidence additions auto-apply.
- Contradictions surface as TODO bullets in the relevant file.
- `skill_proposals` are the **wow factor at the demo**: Xiexie shows it
  noticed it failed at the same kind of ask 3 times and proposes adding a
  new skill called `read_article`.

---

## 6. Privacy and ownership

- Wiki and raw layers live **only** on the user's machine.
- They are markdown — open, portable, deletable, exportable in one click.
- The user can edit the wiki by hand at any time; the linter respects manual
  edits (it diffs against the previous LLM-generated baseline).
- Secrets are Keychain refs, not values.
- Nothing is uploaded except the LLM API calls themselves.

---

## 7. Why this is our technical signature

Most "memory" implementations are vector DBs — opaque, lossy, model-coupled.
The wiki is:
- **Auditable** — Margaret can read it
- **Portable** — markdown moves anywhere
- **Compounding** — knowledge grows, not resets, across sessions
- **Self-correcting** — the linter catches its own mistakes
- **Skill-generative** — gaps become new capabilities

This is the architectural twist that earns the *Innovation* and *Tech Depth*
20% buckets at judging.

