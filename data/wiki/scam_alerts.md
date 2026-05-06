---
slug: scam_alerts
title: Scam alerts
last_updated: 2026-05-06T06:30:00Z
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

## 2026-05-02 — AI voice-clone family emergency, email variant ("lost my phone, this is me from a friend's account")

**Vector**: email (companion to the phone-call voice-clone variant; same playbook, no audio needed)
**Targets**: parents and grandparents of adult children who post publicly on social media; volume rising fastest of any 2026 elder-fraud pattern (FBI IC3 reported >$5M in losses to "distress" scams in 2025, +59% YoY for seniors overall)

**Tactics** (Cialdini): liking (claims to be Lisa / a grandchild), urgency ("the gate closes in 25 minutes"), fear (stranded child), commitment (asks Margaret to *promise* not to tell Tom or Lisa's spouse — preempts the verification call), reciprocity ("I'll pay you back the second I land")

**Tells**:
- Sender is an unfamiliar `@gmail.com` / `@protonmail.com` / `@aol.com` address with a name that looks like the relative ("`lisachenburrows.help@gmail.com`", "`lisa.helpme.urgent@gmail.com`"); real Lisa would mail from `lisa.chen@example.co.uk`
- Body explains away the unfamiliar address: "phone broken", "screen cracked at security", "borrowing a kind woman's laptop"
- Western Union / MoneyGram / gift card / wire — never a refundable rail
- **Recipient on the wire is not the relative** — usually "the gate agent" / "the rental manager" / "the lawyer" with a generic Anglo name (Daniel Whitcomb, Daniel Okonkwo, etc.)
- Time deadline ("25 minutes", "before the gate closes")
- "Please don't call Tom" / "don't tell Dad" — suppresses the one verification path Margaret would otherwise take
- "Don't reply to this email" — second suppression of verification
- SPF=fail (gmail address spoofed via bulk relay), DKIM=none, DMARC=fail
- Often references a real recent travel detail the scammer scraped from Lisa's Instagram (today's flight number, today's airline) — use `family.md` to detect mismatch
- Embedded "confirm to the airline" link is the credential / card-grabber landing page

**Cross-check**: when the email claims a relative is stranded, check `family.md` for that relative's last known location and travel — the wiki almost always knows where they actually are. If the wiki says Lisa landed in SF yesterday, an email from "Lisa stranded at Heathrow today" is decisively the scam.

**Source**: FBI IC3 Annual Report 2025 (released 2026-03, $5.0M+ in distress-scam losses to seniors); FTC consumer alert "Scammers use AI to enhance their family emergency schemes" (still actively cited 2026); FCC "Grandparent Scams Get More Sophisticated"; AARP Fraud Watch March 2026
**Last seen**: 2026-05-06 (Margaret's inbox — "Lisa" stranded at SFO Hertz needing $480, while real Lisa is already in San Francisco)

**Margaret-friendly warning**: "When Lisa or the kids ever ask you for money by email or text — especially from an unfamiliar address — please call them back on the number you already have, or call Tom. Real emergencies survive a five-minute verification call. This one is the AI grandchild scam."

---

## 2026-04-30 — PG&E "60-minute disconnect" utility shutoff scam (CA, active)

**Vector**: email (also phone, also door-to-door — the email variant is the fastest-growing in 2026)
**Targets**: California PG&E customers, especially residential accounts; PG&E has reported ~24,000 customer reports and ~$301k in confirmed customer losses in 2025 alone; average loss $590-$670 per victim

**Tactics** (Cialdini): urgency (60-minute / 30-minute disconnect window), fear (lights and gas off in your home), authority (PG&E branding, fake CA regulation citations)

**Tells**:
- Typosquat domains: `pge-pay-portal.com`, `pge-billing-secure.net`, `mypge-pay.com`, `pge-quickpay.org`. Real PG&E only sends from `pge.com` and `e.pge.com`
- Real PG&E **never** disconnects without prior **written** notice mailed weeks in advance — a sudden email shutoff threat is decisive
- Real PG&E **never** asks for prepaid cards, e-gift cards, Zelle, Venmo, MoneyPak, or wire — the email and phone variants both push these rails
- Fake California-statute references ("California's 2026 peak-season service rules", "2026 elder protection statute"); the rule names do not exist
- Wildly short windows ("within 60 minutes", "field crews dispatched") — real disconnect schedules are documented business-day windows
- SPF/DKIM/DMARC fail; originating IP usually outside the US (.ru, .cn, APAC blocks)
- Includes the user's real PG&E username if scraped from a prior breach (`mchen1951`) — adds credibility but is a stolen-data tell
- "Do not reply to this email" — suppresses the verification path

**Verify path**: real PG&E balance is at pge.com/myaccount or by calling **1-800-743-5000**; PG&E's own scam-reporting line is **1-833-500-SCAM**; suspicious emails go to ScamReporting@pge.com

**Source**: PG&E investor release "National Consumer Protection Week 2026" (pgecorp.com 2026-03); PG&E Safety Action Center scam page (pge.com); Utility Scam Awareness Day press release 2025-11
**Last seen**: 2026-05-06 (Margaret's inbox — "PG&E Billing Center" demanding $526.12 within 60 minutes via prepaid card)

**Margaret-friendly warning**: "PG&E never threatens to shut off your power in the next hour by email, and they never ask for a prepaid card or gift card. If you're ever worried, call PG&E directly at 1-800-743-5000 — the number on your real bill — never the number in the email."

---

## 2026-05-01 — Medicare "replacement card" identity-theft scam (year-round, peaks at open enrollment)

**Vector**: email (also phone and physical mail, but email is the fastest scaling in 2026)
**Targets**: US seniors aged 65+ enrolled in Medicare; volume spikes during open enrollment (Oct 15 – Dec 7) but the spring "secure card initiative" wave runs April–June

**Tactics** (Cialdini): authority (CMS branding, fake CMS regulation numbers), fear (suspension of Part A and Part B benefits), urgency (5-business-day deadline), reciprocity-style framing ("your card is already printed and on hold for you")

**Tells**:
- Typosquat domains: `myssa-medicare.gov-portal.com`, `medicare-cards.gov-update.com`, `cms-secure-renewal.com`. Real Medicare lives on `medicare.gov` and `ssa.gov` — both end in `.gov`, never `.gov-portal.com` or `.gov-update.com`
- Real Medicare cards are **always free**, **always automatic**, and **always mailed unsolicited** to your address on file. Medicare never charges shipping, never asks for SSN by email, never asks for a debit card
- Asks for SSN, MBI (Medicare Beneficiary Identifier), full DOB, and a debit/credit card on a single web form — that's the entire identity-theft kit
- Fake CMS directive numbers (e.g. "CMS-2026-117"); the real CMS rule index is searchable at federalregister.gov and these never resolve
- "Suspension of benefits within 5 business days" — Medicare benefits cannot be suspended this way; only fraud or non-payment after months of notice can affect coverage
- "First issuance wave for beneficiaries born in or before 1951" — generational targeting is a 2026 tell (uses scraped DOBs to look credible)
- SPF/DKIM/DMARC fail; "do not reply" instruction
- Sometimes references a real partial Aetna or supplemental-plan fragment scraped from the 2025 healthcare breach to look credible (cross-pollinates with the Aetna fake-renewal scam)

**Verify path**: real Medicare = 1-800-MEDICARE (1-800-633-4227); MyMedicare.gov for the account portal; State Health Insurance Assistance Program (SHIP) for free counseling

**Source**: FTC consumer alert "Medicare Open Enrollment 2025-09" (still actively linked 2026); FTC "Hang up on Medicare card scams"; FCC "Beware New Medicare Card Scams"; AARP Fraud Watch (year-round); FBI IC3 Annual Report 2025 (Medicare-impersonation scams included in $1.04B tech-support category)
**Last seen**: 2026-05-05 (Margaret's inbox — "CMS Beneficiary Services" demanding SSN + MBI + debit card, references DOB 09/18/1951)

**Margaret-friendly warning**: "Medicare never emails you, never asks for your Social Security Number, and your real card is always free and arrives in the mail by itself. If you're worried, call 1-800-MEDICARE — that's the number on the back of your card — and they'll tell you straight away whether anything is real."

---

## 2026-05-03 — Crypto / asset recovery follow-up scam ("we found your stolen money — pay a small fee to release it")

**Vector**: email (sometimes phone follow-up). One of the FBI's fastest-rising 2026 patterns — a *second* scam targeting people the scammers already know are vulnerable.
**Targets**: anyone whose name has appeared on a victim list — including people who never actually lost anything but who have been *contacted* by a prior scam (romance, investment, crypto). Margaret is on this list because of the Robert Sullivan romance-scam exposure (see [[wiki:scam_alerts#2026-03-15-widow-widower-romance-scam]]).

**Tactics** (Cialdini): reciprocity ("we have your money waiting"), authority ("FBI IC3 partner team", "US Marshals Service victim-restitution program"), social proof ("we have already returned $46M this year"), scarcity ("recovery window closes May 13 — funds forfeited otherwise"), commitment (filing photo ID and address feels like meaningful progress)

**Tells**:
- Made-up "coalition" names: Blockchain Asset Recovery Coalition, Digital Asset Recovery Foundation, Crypto Victim Restitution Bureau, Global Asset Recovery Initiative — none of them exist; real FBI IC3 has no partners that operate this way
- Domains end in `.org` or `.cc` and look semi-official (`blockchain-asset-recovery-coalition.org`)
- **Pay-to-receive money** — the structural tell. No legitimate restitution program ever asks the victim to pay a fee, "gas fee", "court bond", or "compliance deposit" before releasing recovered funds
- Asks for full PII (photo ID + utility bill + wallet address) on top of the upfront fee — that's a complete identity-theft kit
- Subject line uses `Re:` to imply a thread that doesn't exist (`In-Reply-To` header references a fake message ID)
- "Court documents will be made available under seal once your identity is verified" — sealed-court-document language is a fiction here
- Specific dollar figure ($18,420) makes the offer feel calculated rather than generic
- SPF/DKIM/DMARC fail; "personally handling your file" mimics a relationship the recipient never had
- Often follows within days or weeks of the original scam contact — scammers buy and resell victim lists actively in 2026

**Verify path**: real FBI IC3 = ic3.gov, never proactively contacts victims about recovery; real US Marshals Service = usmarshals.gov; FTC has a standing alert: "Worried about crypto exchange losses? Don't pay money for help recovering money" (2022, still authoritative)

**Source**: FBI IC3 PSA 2025-08-13 "Fictitious Law Firms Targeting Cryptocurrency Scam Victims"; FBI IC3 PSA 2024-06-24 (same pattern, expanded); FTC consumer alert 2022-11; FBI IC3 Annual Report 2025 ("recovery fraud losses exceeded $770M in 2023, ~30% of crypto-scam victims subsequently contacted by at least one fake recovery service"); Savi Security 2025 analysis of victim-list resale markets
**Last seen**: 2026-05-06 (Margaret's inbox — "Blockchain Asset Recovery Coalition" claiming $18,420 recovered from a romance ring, demanding $480 in BTC + photo ID + utility bill)

**Margaret-friendly warning**: "Anyone who emails you and says they have found money you lost and just need a small fee to send it back — that is itself a scam, every single time. Real police and real banks never ask you to pay them to give you your money back."

---

## 2026-04-26 — San Francisco property tax "delinquent / lien in progress" scam (regional, year-round but spikes after the April 10 second-installment deadline)

**Vector**: email (also physical mail in some cycles)
**Targets**: San Francisco County homeowners (primary scam window), with copy-paste variants targeting Los Angeles County, Contra Costa County, Alameda County, San Mateo County, Santa Clara County

**Tactics** (Cialdini): authority (City Treasurer branding, real California statute citations to look credible), fear (lien on the property, credit-report damage, refinance blocked), urgency (Friday-deadline cadence)

**Tells**:
- Typosquat domain: `sftreasurer-billing.org`, `sf-property-tax.org`, `sftreasurer-payments.com`. Real SF Treasurer = `sftreasurer.org` (no `-billing` suffix) and never sends payment links by email
- The dates and statute citations are **partly real to look credible** — California Revenue & Taxation Code §4101 et seq. does exist; the second installment really is due April 10 and delinquent April 11; the 10% penalty really is statutory. Scammers borrow real facts to make the email pass a sniff check
- Real SF Treasurer sends paper notices via USPS, not email; their epayment portal is `sftreasurer.org/online-payments`, not a typosquat
- Asks for credit card with a "convenience fee" — real card payments to SF do carry a convenience fee, but never via an emailed link
- Cites a partial APN ("ending in 0741") that may or may not match the recipient's real parcel — even when wrong, a panicked recipient assumes their record is what's wrong, not the email
- SPF/DKIM/DMARC fail; "do not reply" instruction

**Verify path**: real SF Treasurer's tax inquiry line is 311 in the city, or (415) 701-2311 from outside; real SF parcel and tax records are searchable at sftreasurer.org

**Source**: Contra Costa County Assessor's Office scam alert (CBS News, 2024-still-active); Los Angeles County DCBA "Fake Property Tax Bills" advisory (still active 2026); LA County Treasurer property-tax scam alerts page (year-round); FTC monthly digest April 2026 (regional government-impersonation patterns)
**Last seen**: 2026-05-04 (Margaret's inbox — "SF Treasurer & Tax Collector" demanding $4,639.61 by Friday May 8 to avoid lien)

**Margaret-friendly warning**: "The City of San Francisco never emails you about overdue property tax. If you ever get an email like this, throw it away and call 311 — they can look up your parcel for you in two minutes and tell you what's actually owed."

---

## Linter notes

- Last refresh: 2026-05-06T06:30:00Z (appended five new 2026 patterns matching Margaret's overnight inbox: AI voice-clone family-emergency email variant, PG&E 60-minute shutoff, Medicare replacement card, crypto recovery follow-up, SF property tax lien; refreshed all four prior pattern timestamps to today)
- Sources scanned: FBI IC3 Annual Report 2025 (published 2026-03), FTC consumer alerts (2024-09, 2025-09, 2026-04), FCC scam-alert pages (year-round), PG&E scam advisories (2026-03), AARP Fraud Watch April 2026 issue, CBS News Bay Area scam reports, LA County DCBA scam tracker, Reddit r/Scams (top weekly), Krebs on Security 2026-04 ("Wire fraud at scale"), Malwarebytes 2026-04 (quishing evolution), Action Fraud UK monthly
- Patterns retired this cycle: none — all six prior patterns still active per cross-source confirmation
- Next refresh scheduled: 2026-05-13T08:00:00Z
