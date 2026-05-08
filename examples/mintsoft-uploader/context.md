# Project Context Pool

Shared memory across Claude, Kiro, and Claude Code.
Append entries below. Newest at the bottom.

---


## 2026-05-06T09:14:00+00:00 — claude

Kicked off the Mintsoft uploader project. Goal: take order CSVs from
PepsiMax / VIEVE brand emails and produce upload-ready CSVs for
Mintsoft, then eventually push via the REST API.

Decisions:
- Stage 1: CSV in -> CSV out (manual upload to Mintsoft)
- Stage 2: CSV in -> direct API push
- Build Stage 1 first, validate output against a known-good Mintsoft import, then move to Stage 2

Open questions:
- Do all brands use the same source CSV schema? (Need to check 3+ recent files)
- Does Mintsoft API rate-limit? (Will hit docs once Stage 1 works)

---

## 2026-05-06T16:42:00+00:00 — claude-code

Built the Stage 1 CSV transformer. Took the three sample files Falah
dropped in /samples and reverse-engineered the column mapping.

What I did:
- Created `src/transform.py` with a `to_mintsoft(rows)` function
- Handled the two date formats I saw (DD/MM/YYYY and YYYY-MM-DD)
- Mapped `customer_ref` -> `External Order Reference`
- Stripped £ symbols from price columns and cast to float

Surprise: PepsiMax CSVs have a trailing empty column from Excel exports.
Pandas reads it as `Unnamed: 14`. Dropped it explicitly.

Next: Falah needs to do a manual Mintsoft import with the output to
confirm the schema is right before we automate the push.

---

## 2026-05-07T11:08:00+00:00 — kiro

Falah confirmed the manual import worked for PepsiMax (95 orders, all accepted).
VIEVE failed — 12 of 60 orders rejected. Looked at the Mintsoft error log:

> "Postcode format invalid"

Cause: VIEVE source CSV has postcodes without spaces ("SW1A1AA" instead
of "SW1A 1AA"). Mintsoft is strict about this.

Fixed in `transform.py` — added a `normalize_postcode()` helper that
inserts the space before the last 3 chars. Re-ran VIEVE: 60/60 accepted.

Next: start on Stage 2 (API push). Mintsoft docs are at
https://api.mintsoft.co.uk/swagger — need to look at the
`POST /api/Order` endpoint specifically.

---
