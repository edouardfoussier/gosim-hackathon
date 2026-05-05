---
slug: scam_alerts
title: Scam alerts
last_updated: 2026-05-04T22:00:00Z
last_updated_by: linter
confidence: high
related: [accounts, healthcare, preferences]
---

# Scam alerts

> Knowledge base populated automatically by the wiki linter from periodic
> web searches of FTC, Cybermalveillance.gouv, AARP, and Action Fraud feeds.
> The `analyze_email` skill cross-references against this file.
>
> Format: one block per pattern, with sender heuristics, link heuristics,
> and a one-line "Margaret-friendly" warning the agent can read aloud.

---

## Aetna phishing — fake renewal (active 2026-Q2)

- **Pattern**: email claims your Aetna plan is expiring "today" and demands
  you renew via a link.
- **Sender heuristics**:
  - Domain typosquats: `aetnna-secure.com`, `aetna-renew.net`, `aetna.support`
  - Real Aetna sender domain is `@aetna.com` only
  - Display name often "Aetna Customer Service" with mismatched return-path
- **Link heuristics**:
  - Multi-hop redirects ending on a free hosting service (`.netlify.app`,
    `.vercel.app`, `.glitch.me`) or a TLD mismatch (`.ru`, `.cn`)
  - Landing page asks for SSN + credit card *and* member ID (real Aetna
    portal never asks for SSN at renewal)
- **First reported**: FTC alert 2026-04-28, AARP confirmation 2026-04-30
- **Confidence**: high
- **Margaret-friendly warning**: "This is the fake-Aetna-renewal scam that
  has been going around. Your real Aetna login is at aetna.com — never click
  the email."

## Bank "frozen account" SMS / email (long-running)

- **Pattern**: urgent message claiming your bank account has been frozen
  due to suspicious activity; click to verify.
- **Sender heuristics**: spoofed display name ("Chase Security", "Bank of
  America Alerts") with non-bank domains
- **Link heuristics**: short URLs (`bit.ly`, `t.co`) or IP-address links
- **Reported by**: Action Fraud UK 2026-04, FTC monthly digest
- **Confidence**: high
- **Warning**: "Your bank will never email you to click a link. If in doubt,
  call them at the number on the back of your card."

## IRS / tax refund scam (US, peaks April + October)

- **Pattern**: "You are owed a refund of $X — click to claim within 24 hours"
- **Sender heuristics**: never `@irs.gov`; common spoofs `@irs-refund.com`,
  `@us-treasury.net`
- **Confidence**: high
- **Warning**: "The IRS does not initiate refunds by email. Ignore."

## Microsoft / Apple support phone-back

- **Pattern**: pop-up or email claiming your computer has a virus, with a
  toll-free number to call. Caller asks for remote access (TeamViewer, AnyDesk).
- **Confidence**: high
- **Warning**: "Apple and Microsoft never call you. Hang up and tell Lisa."

## Fake delivery (USPS / FedEx / La Poste)

- **Pattern**: "Your package couldn't be delivered, click to reschedule"
- **Sender heuristics**: lookalike domains (`usps-track.com`, `fedex-redelivery.org`)
- **Link heuristics**: forms requesting credit card "for a small redelivery fee"
- **Confidence**: high
- **Warning**: "Real delivery services never charge a re-delivery fee by email."

## Romance / grandchild emergency call

- **Pattern**: phone call (sometimes voice-cloned) claiming to be a grandchild
  in jail / hospital / abroad needing emergency money.
- **Confidence**: medium (voice cloning getting more convincing)
- **Warning**: "If a grandchild calls in distress, hang up and call them back
  on the number you already have."

---

## Linter notes

- Last refresh: 2026-05-04T22:00:00Z (3 new entries since 2026-04-27 baseline)
- Sources scanned: FTC consumer alerts, FBI IC3 monthly, AARP fraud watch,
  Cybermalveillance.gouv (FR), Action Fraud (UK)
- Next refresh scheduled: 2026-05-11T22:00:00Z
