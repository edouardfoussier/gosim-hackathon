---
slug: accounts
title: Online accounts
last_updated: 2026-05-04T18:00:00Z
last_updated_by: agent
confidence: high
related: [healthcare, recurring_tasks]
---

# Online accounts

> **Never** stores plaintext passwords. Each entry has a Keychain ref the
> `login_site` skill resolves at runtime. Margaret can revoke any ref by
> deleting the Keychain entry — Xiexie respects it.

## Aetna

- URL: https://www.aetna.com/member
- Username: m.chen@example.com
- Password: `[Keychain ref: xiexie/aetna]`
- 2FA: SMS to (650) 555-0188
- Used for: insurance renewal, claims, EOB downloads
- See [[wiki:healthcare#insurance]]

## PG&E

- URL: https://www.pge.com
- Username: mchen1951
- Password: `[Keychain ref: xiexie/pge]`
- Auto-pay enabled (no need to log in for monthly)

## Stanford MyHealth

- URL: https://stanfordhealthcare.org/myhealth
- Username: m.chen.1951
- Password: `[Keychain ref: xiexie/stanford-myhealth]`
- Used for: appointments, lab results, messaging Dr. Patel

## Apple ID

- m.chen@icloud.com
- Password: `[Keychain ref: xiexie/apple-id]`
- iCloud Photos enabled, Family Sharing with Lisa

## Gmail

- m.chen.1951@gmail.com
- Used for: personal email
- Password: `[Keychain ref: xiexie/gmail]`
- Alias of Mail.app account

## Amazon

- m.chen@example.com
- Password: `[Keychain ref: xiexie/amazon]`
- Default delivery: home address
