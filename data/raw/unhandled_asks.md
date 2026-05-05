# Unhandled asks log

> Voice requests Xiexie did not have a skill for. The wiki linter reviews
> this file periodically and proposes new skills (or improvements to existing
> ones) — that's the **compounding learning** loop.
>
> Append-only. One block per ask.

<!-- Format:
## YYYY-MM-DDTHH:MM:SSZ
- ask: "<verbatim transcript>"
- intent (LLM-inferred): "<short label>"
- planner attempt: "<which skills were considered>"
- response delivered: "I don't know how yet — taking a note."
- proposed skill (linter): "<name>" / null
-->

## 2026-05-04T11:42:00Z
- ask: "Xiexie, can you summarise this article for me out loud?"
- intent: read_article
- planner attempt: considered `read_emails`, no match
- response delivered: "I don't know how to do that yet — I'm taking a note."
- proposed skill (linter): `read_article`

## 2026-05-04T15:08:00Z
- ask: "Can you make this PDF say what I'm reading? Like, narrate it."
- intent: read_article
- planner attempt: considered `find_file`, then deferred
- response delivered: "I'll learn that for you. Adding it to my list."
- proposed skill (linter): `read_article` (same as above; frequency = 2)

## 2026-05-05T07:32:00Z
- ask: "Could you write back to Lisa for me? Tell her I said yes."
- intent: reply_email
- planner attempt: considered `read_emails`, only reads, no compose
- response delivered: "Not yet — I can read but not write emails. Taking a note."
- proposed skill (linter): `reply_email`

## 2026-05-05T17:22:15+00:00
- skill_attempted: daily_brief
- args: {}
- response: stub fallback ("taking a note so I can learn")
