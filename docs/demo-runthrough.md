# Demo run-through — "à la Clicky" but for Margaret

> Step-by-step recipe to test Xiexie end-to-end like a real user would.
> Print this on a second screen during rehearsal so you don't have to
> remember what to say.
>
> Compare points to Clicky:
> - Clicky activates with `ctrl+option` push-to-talk → we have a mic
>   button (and wake-word "Xiexie" once Picovoice is enabled)
> - Clicky has a blue cursor companion that follows you → we have a
>   warning glyph that *only appears when something needs attention*
>   (less ambient, more intentional — fits the protective use-case)
> - Clicky's verdict is voice + text → we add a structured
>   **Verdict Card** UI on top so Margaret can read at her own pace

---

## 0. Pre-flight (30 seconds)

Always start clean. From any terminal:

```bash
# kill anything still squatting our ports / processes
lsof -t -i:8787 | xargs -r kill -9 2>/dev/null
pkill -9 -f "overlay" 2>/dev/null
pkill -9 -f "uvicorn xiexie" 2>/dev/null

# verify .env is the direct Z.AI one (not the proxy)
grep "ZAI_BASE_URL\|ZAI_MODEL" /Users/edouardfoussier/code/gosim-hack/.env
# Expected:
#   ZAI_BASE_URL=https://api.z.ai/api/paas/v4
#   ZAI_MODEL=glm-4.6
```

---

## 1. Boot the three services (3 terminals, 30 seconds)

Each terminal stays open during the whole demo.

### Terminal 1 — Backend (the brain)

```bash
cd /Users/edouardfoussier/code/gosim-hack/backend
uv run --active uvicorn xiexie.main:app --port 8787 --log-level info
```

Wait for `Uvicorn running on http://127.0.0.1:8787`. The `--log-level info`
prints every WS connect / `POST /plan-and-run` so you see the chain in
real time. Bump to `warning` for a cleaner demo recording.

### Terminal 2 — Overlay daemon (the watcher)

```bash
cd /Users/edouardfoussier/code/gosim-hack         # ← repo root, NOT overlay/
source overlay/.venv/bin/activate
python -m overlay
```

Wait for `[overlay] backend WS connected`. The daemon stays silent until
the backend broadcasts an `alert`. Then it'll print
`[overlay] alert level='phishing' message='…'` and the glyph appears on
your screen.

### Terminal 3 — Next.js frontend (the conversation)

```bash
cd /Users/edouardfoussier/code/gosim-hack/app
pnpm dev
```

Wait for `ready - started server on http://localhost:3000`. Open that URL
in **Chrome** (Safari has stricter mic permissions and patchier offline
TTS voices). Grant mic when Chrome asks.

---

## 2. The four scenarios — what to say and what to expect

Each scenario tests a different layer. Walk through them in order; if one
breaks the next probably does too, so stop and debug.

### Scenario A — Simple OS-level skill (smoke test) · ~5 s

| Step | Action |
|---|---|
| 2A.1 | Click the **mic** button in the browser (it pulses crimson when listening) |
| 2A.2 | Say: **"Open Mail for me"** |
| 2A.3 | Click the **mic** again to stop |

**Expected, in order:**
1. The status line below the input shows `transcribing…`
2. A user bubble appears: `Open Mail for me`
3. A Xiexie bubble: `"I'll open Mail for you."` (or similar preamble)
4. A skill log line: `open_app({'name': 'Mail'}) → Opened Mail.`
5. **macOS Mail.app actually launches** (or comes to front)
6. The browser TTS speaks the preamble out loud

**If this fails:**
- Mic doesn't trigger → mic permission denied; relaunch Chrome and
  re-grant.
- Bubble shows `transcribing…` forever → faster-whisper model is still
  warming up on first call (~10 s). Try again.
- No tool call, just narration → planner is on the proxy without
  DeepSeek. Check `Planner.dispatch_model` shows `None` (direct Z.AI) and
  `model` shows `glm-4.6`.

### Scenario B — Voice-first inbox check · ~10 s

| Step | Action |
|---|---|
| 2B.1 | Mic on. Say: **"Did I get any new emails today?"** |
| 2B.2 | Mic off. |

**Expected:**
1. User bubble + Xiexie bubble preamble.
2. Skill log: `read_emails({}) →` followed by:
   ```
   You have 3 unread emails:
   - From Lisa Chen-Burrows: Landing at SFO at 4 — see you soon ❤️
   - From Aetna Member Services: Your Aetna plan renewal …
   - From Aetna Customer Service: URGENT: Your Aetna coverage expires…  ⚠ unusual

   One (msg-003) looks unusual to me — want me to take a closer look?
   ```
3. TTS reads the summary out loud, ending with the question.

**The "⚠ unusual" line is the one we want.** It means our cheap header
heuristics fired before the LLM was even invoked: SPF=fail + typosquat
domain + ALL-CAPS subject. Cheap-and-fast first pass, expensive
forensics next.

### Scenario C — The flagship: full forensic verdict · ~15 s

This is the demo's money beat. Stay quiet during the `analyze_email`
call — the planner is fanning out to `check_url`, `search_scam_intel`,
`email_rep` in parallel and the verdict takes 8–12 s on GLM-4.6.

| Step | Action |
|---|---|
| 2C.1 | Mic on. Say: **"Yes please, take a closer look at that one."** |
| 2C.2 | Mic off. |

**Expected:**
1. Skill log: `analyze_email({'message_id': 'msg-003'}) → …`
2. After ~10 s the result appears as a **Verdict Card** in the chat
   (not a small banner — the full Claude-Design layout with three
   numbered sign cards + Cialdini chips + "Tell Lisa about this" CTA).
3. **Simultaneously**, on your screen: a crimson triangle glyph in the
   top-right corner with a soft glow, **above your browser**. Click
   anywhere on the glyph to dismiss, or wait 5 s for fade-out.
4. Terminal 2 prints: `[overlay] alert level='phishing' message='…'`
5. The TTS reads Margaret-friendly speak_aloud:
   *"Margaret, this is the fake Aetna renewal scam … please delete it…"*

**The simultaneous-three-surface reveal is the wow shot.** Verdict Card
in the conversation, glyph on the desktop, voice in the speakers. All
fired by a single GLM-4.6 verdict.

### Scenario D — Chained follow-up + family alert · ~5 s

After Scenario C completes, Xiexie should automatically propose
contacting Lisa.

| Step | Action |
|---|---|
| 2D.1 | A Xiexie confirm bubble appears: *"Want me to send Lisa a heads-up about this?"* |
| 2D.2 | Mic on. Say: **"Yes please."** |
| 2D.3 | Mic off. |

**Expected:**
1. The planner recognises the affirmative + the stashed follow-up and
   skips a fresh GLM call (early-return, ~200 ms).
2. Skill log: `report_to_family({'summary': '…', 'recipient_hint': 'Lisa'}) → …`
3. **Mail.app opens with a draft to `lisa.chen@example.co.uk`** with a
   3-bullet summary of the verdict signs.
4. **The draft is NOT sent automatically** — Xiexie never sends; you
   click ⌘+⏎ in Mail to actually deliver. (Safety-by-design.)

---

## 3. Edge cases you can show off in Q&A

These aren't part of the 5-min recorded demo but are worth practicing —
judges *will* ask "what about X?".

### "Make this text bigger" — accessibility

```bash
# in the browser, click mic and say:
"Make this text bigger"
```

Expected: `zoom_text({'amount': 'bigger'}) → …` (skill is a stub today,
narrates politely; document this as "wired, real impl in V2"). The
narration honesty is the right answer — it's *exactly* the on-brand
log-and-learn pattern for unhandled asks (see `unhandled_asks.md`).

### "What does this say?" — vision (NEW today, GLM-4.5V)

Open any web page or a PDF in Preview. Mic on:
```
"What's the headline of this article?"
```

Expected: `read_screen({'question': '…'}) → "<the headline>"`. The
agent captures the screen, sends it to GLM-4.5V, returns plain text.
Nice live recovery if Mail.app demo glitches.

### "Tell me a joke about scams" — narrate sentinel

Tests that the planner uses the `narrate` escape hatch when no skill
matches. Expected: a joke as the spoken reply, no tool calls.

### Direct backend curl (for when the browser breaks)

If voice / mic flakes during the live demo, fall back to:

```bash
curl -s -X POST http://127.0.0.1:8787/plan-and-run \
  -H 'content-type: application/json' \
  -d '{"text":"Take a closer look at the suspicious email msg-003"}' \
  | jq -r '.steps[0].result' | head -10
```

Same end-to-end chain as Scenario C, just bypasses the mic. The glyph
still fires on the overlay.

---

## 3b. Planting the phishing email in Mail.app

The recorded video runs against the *real* macOS Mail.app inbox
(``MAIL_SOURCE=mailapp``). For the analysis beat to land, Margaret's
inbox needs one unread "Aetna" phishing email Edouard plants the night
before. The fixture (``data/demo/inbox.json``) stays as a backup —
flip ``MAIL_SOURCE=demo`` in ``.env`` and restart uvicorn to switch.

### Step 1 — send the bait to yourself

From any free webmail account (Outlook, iCloud, Gmail) that is *not*
Edouard's primary account, send a message to whatever inbox Mail.app is
configured to read:

| Field | Value |
|---|---|
| **From display name** | ``Aetna Customer Service`` |
| **Subject** | ``URGENT: Your Aetna coverage expires TODAY — verify identity now`` |
| **Body** | (paste the body of ``msg-003`` from ``data/demo/inbox.json``, including the ``aetnna-secure.com`` URL) |

Display-name spoofing is the only ingredient our cousin-domain heuristic
needs — the actual sending domain doesn't have to be ``aetnna-secure.com``,
and trying to spoof one will land you in the recipient's spam folder.
The body containing the typosquatted URL is what ``analyze_email`` chews
on (URL forensics + Cialdini extraction + GLM verdict).

### Step 2 — make sure it's UNREAD when you press record

If you previewed the email while testing, open Mail.app and right-click
→ **Mark as Unread** (or ``⇧⌘U``). The ``read_emails`` skill only ships
unread messages; a "read" email is invisible to it.

### Step 3 — verify before each take

```bash
# Counts unread inbox messages without opening Mail.app to the foreground.
osascript -e 'tell application "Mail" to count messages of inbox whose read status is false'
# Expect: a number ≥ 1 (the phishing email).
```

If the answer is ``0``, mark the email unread again before recording.

A second sanity check goes through Xiexie's own probe:

```bash
cd /Users/edouardfoussier/code/gosim-hack/backend
uv run python -m xiexie.skills._mail_app status
# Expect: {"available": true, "error": null, "inbox_count": "<n>"}
```

If ``available`` is ``false``, see §1 of ``MACOS_PERMS.md`` (or just
toggle ``MAIL_SOURCE=demo`` in ``.env`` and restart uvicorn for the
fixture-only path — the rest of the demo is identical).

---

## 4. Sanity checklist before you record / pitch

Run through this once just before the take. Each line should be a
visible "yes":

- [ ] `lsof -i:8787` shows uvicorn (one process)
- [ ] `[overlay] backend WS connected` printed in Terminal 2
- [ ] Browser shows `connected` next to the title and `🔊 speaking…`
      flashes when TTS plays
- [ ] First mic click pulses crimson (mic permission was granted)
- [ ] `data/demo/inbox.json` has `"archived": false` for msg-003 (run
      `git checkout data/demo/inbox.json` to reset between takes)
- [ ] No stale glyph on screen from a previous run (`pkill -f overlay`
      if there's a ghost)

---

## 5. Scenarios that intentionally fail (don't test these on stage)

Document these so we don't break a take by trying them:

- **"Did Lisa send me anything?"** — works but currently makes
  `read_emails` filter on Lisa, which our heuristics don't flag (legit
  email). Boring on stage.
- **Hot-mic with background noise (Station F)** — wake-word not enabled
  yet. Push-to-talk is the only entry point until Picovoice approves.
- **Real Aetna URL** — the demo URL `aetnna-secure.com` is a fake we
  control via the mock fixture. Don't try a real URL in the live demo
  (urlscan + GSB will reject as expected, but the latency is
  unpredictable).

---

## 6. The 5-min storyboard for the recorded video

| t (s) | Surface | What happens |
|---|---|---|
| 0–8   | Voice-over over a B-roll of an inbox | Hook: "$3.4B/yr to scams. My grandmother almost lost three thousand. This is for her." |
| 8–10  | Cut to Margaret's Mac, Mail.app inbox visible | Set the scene |
| 10–25 | Voice + chat panel | Scenario B (read_emails, "one looks unusual") |
| 25–28 | Voice | Scenario C trigger ("Yes please, take a closer look") |
| 28–60 | Live timeline | URL sandbox + sender headers + scam-intel reveal one by one (the analyze_email skill log unfolds) |
| 60–90 | Verdict Card animates in + glyph fires | The triple-surface reveal — the money beat |
| 90–120 | Voice "Yes" → Mail.app draft to Lisa | Scenario D, family alert |
| 120–140 | Wiki banner re-renders | "Learned: aetnna-secure pattern · alerted Lisa 13:23" |
| 140–155 | Quick breadth | "Open Mail" + "Make this bigger" rapid-fire |
| 155–180 | Voice-over close | "GLM-4.6 brain. Open source. Local-first. Xiexie." |

Print this table on your second screen. Hit your marks.

谢谢 🍀
