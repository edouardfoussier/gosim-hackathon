# Xiexie demo inbox — drag-droppable .eml fixtures

Six RFC822 plain-text emails for the live demo. Drag them into the **Inbox**
of `edouardfoussier@me.com` in macOS Mail.app and Xiexie's `analyze_email`
skill will read them via AppleScript like any other message.

## Drag-drop steps (90 seconds, do this once before rehearsal)

1. Open **Mail.app** and select the **Inbox** of `edouardfoussier@me.com` in the
   left sidebar (not All Inboxes).
2. In Finder, open `data/demo/eml/`.
3. Cmd-A to select all six `.eml` files. Drag them onto the Mail.app message
   list pane (not the sidebar — drops onto folders sometimes route to All
   Mail or Junk).
4. Mail.app marks dragged emails **read by default**. Run the AppleScript
   below from Terminal to mark all six as unread in one shot:

   ```bash
   osascript -e 'tell application "Mail"
       set demoSubjects to {¬
           "Mom please read this is Lisa I lost my phone", ¬
           "FINAL DISCONNECT NOTICE - PG&E account mchen1951 (action required within 60 minutes)", ¬
           "Action required - replacement Medicare card on hold (DOB 09/18/1951)", ¬
           "Re: Funds recovery case #BARC-2026-0518 - confirmed match (response required)", ¬
           "NOTICE OF DELINQUENT PROPERTY TAX - Lien preparation in progress", ¬
           "We'\''ve redesigned wellsfargo.com - sign on once before May 31 to confirm your preferences"}
       repeat with subj in demoSubjects
           set msgs to (every message of inbox whose subject is subj)
           repeat with m in msgs
               set read status of m to false
           end repeat
       end repeat
   end tell'
   ```

5. **Spam check.** Mail's junk filter sometimes routes the SPF=fail messages
   into Junk despite the drag-drop. Click **Junk** in the sidebar; if any
   demo emails landed there, right-click → Move to → Inbox. The four scams
   (`01`, `02`, `03`, `05`) are most at risk; `04` (crypto, no Subject caps)
   and `06` (Wells Fargo, all auth passes) usually stay in Inbox.

6. Sanity-check the date sort. With the inbox sorted by date desc, the top
   three should be (newest first):

   - `01-grandchild-bail.eml`        — Wed 09:18
   - `02-pge-shutoff-60min.eml`      — Wed 07:42
   - `04-crypto-recovery-followup`   — Wed 06:24

## Expected demo arc

- **Open with** `01-grandchild-bail` — voice-clone-flavoured family emergency
  is the freshest 2026 pattern (FBI IC3 reported $5M+ losses in 2025 alone,
  released March 2026). Margaret's wiki knows Lisa landed at SFO yesterday,
  so Xiexie can also surface the "your wiki says Lisa is already here" beat.
- **Beat 2** — `02-pge-shutoff-60min` shows the utility-shutoff pattern
  (PG&E reported ~$301k in customer losses in 2025) with a 60-minute
  deadline. Quick to verdict.
- **Beat 3** — `04-crypto-recovery-followup` is the predator-on-victims
  pattern; demonstrates Xiexie reasoning across multiple signals (no prior
  thread, fake IC3 partner, "pay to receive money" tell).
- **The benign control** — `06-bank-redesign-legit` is the "and this one?"
  email. Authentication passes, link goes to bare wellsfargo.com, no
  personal-info ask. Xiexie should rate it `clear` or `unclear`, not
  `phishing`. Use it to prove the agent is not trigger-happy.
- **Backup beats** — `03-medicare-replacement` and `05-property-tax-overdue`
  are reserves if a judge asks for a different category in Q&A.

## Mail.app gotchas (saving you future-me time)

- **The .eml files must be valid RFC822** — Mail's importer silently fails
  on malformed headers. All six in this folder pass
  `python3 -c "import email; email.message_from_file(open('FILE.eml'))"`
  with `policy=email.policy.default`. If you hand-edit one, re-validate.
- **`Date:` header drives sort order.** Today's three are dated
  `2026-05-06` PDT; the other three are spread across May 4-5 PDT. Adjust
  if you re-run the demo on a different day — you want the freshest scam
  on top so `read_emails(unread_only=true, limit=3)` surfaces it first.
- **Mail respects `Authentication-Results`** for its own spam classification.
  We deliberately put SPF/DKIM/DMARC failures in the four scams so Mail's
  built-in scoring agrees with Xiexie's verdict — but it also means Mail
  may move them to Junk on import. See step 5 above.
- **Mail.app may "verify" the From address on import** by attempting a DNS
  lookup. The typosquat domains in these emails (`pge-pay-portal.com`,
  `gov-portal.com`, etc.) resolve fine because they're plausible — if you
  ever swap one for a domain that doesn't exist, Mail may reject the drop.
  Stick to live but unrelated hosts.
- **Don't forget to mark them unread** (step 4) — `read_emails` filters
  `unread_only=true` by default and the demo opens with "Xiexie did I get
  any new emails?".
