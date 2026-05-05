---
slug: scam_alerts
title: Scam alerts
last_updated: 2026-05-05T08:00:00Z
last_updated_by: linter
confidence: high
related: [accounts, healthcare, family, preferences]
---

# Scam alerts

> Knowledge base maintained by the wiki linter from periodic web searches of
> FTC consumer alerts, FBI IC3 monthly digest, AARP Fraud Watch, Reddit
> r/Scams, Krebs on Security, and Action Fraud (UK). The `analyze_email`
> skill cross-references this file when scoring an inbound message.
>
> Format: one entry per active pattern, dated when first observed, with
> Cialdini tactics, sender/link tells, and a one-line "Margaret-friendly"
> warning the agent can read aloud at the end of a verdict.

---

## 2026-04-28 — Aetna fake renewal phishing (active Q2-2026)

**Vector**: email
**Targets**: US Medicare-age Aetna members; volume spikes during open-enrolment windows (April–June, October–December)
**Tactics** (Cialdini): urgency ("expires today"), authority ("required by CMS regulations"), fear (loss of medical coverage)

**Tells**:
- Typosquat domain: `aetnna-secure.com` (double-n) — also seen: `aetna-renew.net`, `aetna.support`, `aetnacare-portal.com`
- Real Aetna mail only originates from `aetna.com`
- `Return-Path` mismatched, often pointing to a bulk-mail relay (`mailgrid-bulk.ru`, `sendgrid-bounce.cn`)
- SPF=fail, DKIM=none, DMARC=fail
- Body asks for SSN + DOB + member ID + credit card on a single web form (real Aetna never asks for SSN at renewal — renewals happen on aetna.com/member after sign-on)
- Sometimes references a real partial member ID stolen from the 2025 healthcare-data breach to look credible
- 24-hour deadline; "do not reply" instruction (suppresses verification)
- Fake CMS regulation references (e.g. "CMS-9912-F") — the rule numbers do not exist

**Source**: FTC consumer alert 2026-04-28; AARP Fraud Watch confirmation 2026-04-30; Reddit r/Scams thread 2026-05-01 (43 reports in 6 days)
**Last seen**: 2026-05-05 (Margaret's inbox)

**Margaret-friendly warning**: "This is the fake-Aetna-renewal scam doing the rounds. Your real Aetna sign-on is at aetna.com — never click the link in the email. If you're worried, call Aetna at the number on your insurance card."

---

## 2026-04-22 — USPS / parcel redelivery fee scam (long-running, persistent)

**Vector**: email + SMS
**Targets**: anyone expecting a package; success rate spikes around holidays, Mother's Day, and major shopping events

**Tactics** (Cialdini): urgency (48-hour return-to-sender), small-ask commitment (only $1.99 — a number psychologically too low to refuse), social-proof ("you've already paid for shipping")

**Tells**:
- Lookalike domains: `notifyparcel-services.net`, `usps-track.com`, `usps-delivery.support`, `uspsfedex-tracking.com`
- Real USPS mail originates from `usps.com` and `email.usps.com`; **USPS never charges a redelivery fee for missed packages**
- Tracking number format usually correct (22 digits) — copied from a real USPS template to look authentic
- SPF=softfail or none; DKIM=none
- Originating IPs frequently from APAC blocks
- Landing page captures full name + address + credit card "for the $1.99 fee" — the card is then charged for thousands and resold on dark-web markets
- Same template recycled for FedEx, DHL, La Poste, Royal Mail variants

**Source**: USPS Inspection Service alert 2026-03-14; FTC monthly digest April 2026; documented continuously since 2023
**Last seen**: 2026-05-04 (Margaret's inbox)

**Margaret-friendly warning**: "USPS never charges a re-delivery fee by email. If a real package is missing, go to usps.com and look up the tracking number directly — never click the link in the email."

---

## 2026-03-15 — Widow/widower romance scam ("trapped abroad needs travel money")

**Vector**: email (typically after Facebook, Instagram, or dating-app contact moves to private email)
**Targets**: recently widowed seniors, especially women aged 65+ who are active on Facebook; meet-cute usually online, builds for months before the ask

**Tactics** (Cialdini): liking (months of warm correspondence), reciprocity ("I love you, you've made me believe in love again"), commitment-and-consistency (after 6+ months invested, walking away feels like betraying the relationship), scarcity (one-time travel window, flight leaves tomorrow)

**Tells**:
- Free-tier email: `@protonmail.com`, `@gmail.com`, `@aol.com`, sometimes `@yahoo.com`
- **Headers usually pass** (SPF/DKIM/DMARC all green) — content is the only signal, so header-only filters miss it entirely
- Persona: widower, military veteran, contractor abroad, oil-rig engineer, surgeon with Doctors Without Borders; always "stuck" overseas (Lagos, Accra, Dubai, Kabul, Damascus)
- Inheritance / project-payment / customs-clearance "stuck in escrow" — needs a few thousand dollars to unlock
- Payment requested via Western Union, MoneyGram, Apple/Google Play gift cards, or crypto — **never** a method that can be reversed
- Flight booked but card "declined due to fraud hold"
- Promises to repay "the minute the money clears"; after Margaret pays, a fresh emergency materializes within 48 hours (medical bill, customs fee, hotel hold)
- Recipient name is usually different from the sender's claimed identity (Western Union recipient is "the agent")

**Source**: FBI IC3 confidence-fraud report 2026-Q1 (\$740M lost in 2025 to elder romance fraud, US only); AARP BankSafe initiative 2026-04
**Last seen**: 2026-05-04 (Margaret's inbox — "Robert Sullivan", widower from Accra, requesting \$2,400 for a flight)

**Margaret-friendly warning**: "Anyone you have only met online who asks you for money is almost certainly a scammer — even when it feels real. Please don't send anything, and tell Lisa before you do. I can show you the pattern."

---

## 2026-04-18 — Bank wire-transfer alert phishing (sophisticated, two flavors)

**Vector**: email
**Targets**: bank customers — especially Wells Fargo, Chase, Bank of America, USAA

**Tactics** (Cialdini): fear (large unknown wire on your account), urgency ("scheduled for tomorrow morning"), authority (mimics real bank template byte-for-byte), social-proof ("we blocked the attempt to protect you")

**Tells** (two flavors of this attack — they look identical to the user):
1. **Spoof variant**: From-address spoofs the bank but `Return-Path` / SPF reveals the lie (e.g. `alerts@chase-secure.com` instead of `chase.com`). Link points to a credential-grabber.
2. **Account-takeover variant**: a *real* bank email about a wire/transfer the user did not initiate — the email is genuine (SPF/DKIM/DMARC all pass, link goes to the real bank), but the underlying activity means the account is **already compromised** and the wire needs to be cancelled by phone.

- Always names a recipient the user does not recognize and an unusual amount in the \$2,000–\$5,000 range (sized to slip under most fraud-alert thresholds)
- Always offers two CTAs: "click to cancel" and a real phone number — scammers hope the user clicks the link instead of calling
- For the legitimate-email variant, the user should still ignore the link and call the number on the back of their card (not the number in the email)

**Source**: Krebs on Security 2026-04-12 ("Wire fraud at scale"); FTC Sentinel Network Q1 2026 report
**Last seen**: 2026-05-04 (Margaret's inbox — Wells Fargo \$2,847 to "DAVID YOO", email itself appears legitimate but the wire is unauthorized — likely account-takeover variant)

**Margaret-friendly warning**: "If your bank emails about a transfer you didn't set up, do not click anything in the email — even links that look correct. Call the number on the back of your card and ask them to look up the wire by reference number."

---

## 2026-02-09 — Apple / Microsoft tech-support callback scam (long-running)

**Vector**: email + browser pop-up + cold call
**Targets**: any senior; pop-ups frequently triggered by typo'd domains or malicious ads

**Tactics** (Cialdini): fear ("your iCloud has been compromised"), authority (impersonates Apple Support / Microsoft Defender), urgency (countdown timer on the pop-up, "your data will be wiped in 5 minutes")

**Tells**:
- Toll-free callback number in the email or pop-up — real Apple Support never gives a callback number this way; the user always initiates support via support.apple.com or the Genius Bar
- Caller asks for remote-desktop access (TeamViewer, AnyDesk, Quick Assist) "to diagnose the threat"
- Once in, payment requested via gift cards (Apple, Google Play, Amazon) — **the** signature tell of this scam
- Email often spoofs `noreply@apple.com` or `support@microsoft.com`; SPF=fail
- Pop-up version uses sound + flashing red banner to panic the target into calling
- After payment, the scammer leaves remote-access tools installed for re-entry

**Source**: AARP Fraud Watch 2026-02-09; Apple Support advisory HT204759 (active); Microsoft Security Response Center monthly
**Last seen**: 2026-04-22 (Reddit r/Scams)

**Margaret-friendly warning**: "Apple and Microsoft never call you, and they never ask you to install software to fix your computer. If a pop-up tells you to call a number, close the browser and tell Lisa — I'll help you check that everything is fine."

---

## Linter notes

- Last refresh: 2026-05-05T08:00:00Z (added Wells Fargo wire-alert pattern; refreshed Aetna and USPS confidence after Margaret's inbox today confirmed both)
- Sources scanned: FTC consumer alerts, FBI IC3 monthly, AARP BankSafe, Reddit r/Scams (top weekly), Krebs on Security, Action Fraud UK, Cybermalveillance.gouv (FR)
- Patterns retired this cycle: none
- Next refresh scheduled: 2026-05-12T08:00:00Z
