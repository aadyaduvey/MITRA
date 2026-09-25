# MITRA QA report (M7)

**Date:** 26 Sep 2026 · **Base commit:** `8b40850` (M6) + M7 changes · **Machine:** Windows 11, Python 3.11.16 (uv), Node 24, pnpm 12

## Result: all green

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | **PASS**: 113 / 113 |
| Backend tests on a fresh clone | **PASS**: 112 passed, 1 skipped (needs the TrashNet dataset, which is not committed) |
| Dashboard type-check + build (`pnpm build`) | **PASS** |
| Dashboard lint (`pnpm lint`) | **PASS**: 0 warnings |
| One-command smoke test, `start.cmd -Smoke` (8 endpoint checks) | **PASS** |
| **Fresh clone → one command → working demo** | **PASS**: 27 s with warm package caches, clean shutdown |
| `start.sh --smoke` (macOS/Linux script, run in Git Bash) | **PASS** |

No red items. Everything that is not done is listed under *Known limitations* below.

## Automated tests by area (113)

| Area | Tests | Covers |
|---|---|---|
| API (`test_api.py`) | 28 | every endpoint, validation, 404/409/422, CSV/PDF/JSON, CORS, erasure |
| Telegram bot (`test_bot.py`) | 40 | full chat flows with fake Telegram objects, retries on dropped connections, persistence across restarts, `/forget`, offline demo |
| Photo classifier (`test_classify.py`) | 10 | label mapping, 70% gating, API routes, real model on held-out photos |
| Seed data (`test_seed.py`) | 9 | row counts, GPS in Jaipur, dispatch rule, no future timestamps, determinism |
| Passport (`test_passport.py`) | 8 | full / partial chain, no phone or Aadhaar leak, IST times, photo hash |
| Material flow (`test_material_flow.py`) | 7 | Sankey links, mass conservation, copper split from metal |
| EPR + summary (`test_epr_summary.py`) | 6 | eligibility (delivered vs in transit), empty period, PDF render |
| Pricing (`test_pricing.py`) | 5 | lookup, bad rows, quotes |

No test uses the network; Telegram, the API and the classifier are replaced by in-memory stand-ins.

## Edge cases (M7 list and others)

| Case | Behaviour | Evidence |
|---|---|---|
| Transaction with unknown material | HTTP 422 `unknown material_id N`; bot shows the message | `test_log_transaction_rejects_bad_input`, `test_client_errors` |
| Collector with no transactions | Detail returns 0 lots, empty list; dashboard shows "No lots logged yet" | `test_collector_with_no_transactions` |
| Empty EPR date range | JSON with zero totals; PDF still renders with "No lots in this period" | `test_epr_empty_range`, `test_pdf_renders_including_empty_and_markup_chars` |
| Start date after end date | HTTP 422; dashboard disables downloads and explains | `test_epr_bad_range`, `test_list_transactions_date_filter` |
| Missing GPS | Lot saved; passport `gps: null`; not drawn on the map (count shown); bot says "will not appear on the map" | `test_log_transaction_without_gps`, `test_passport_without_gps`, `test_log_without_photo_or_location` |
| Half a GPS fix (lat without lon) | HTTP 422 | `test_log_transaction_rejects_bad_input` |
| Weight 0, negative, text, over 2000 kg | API 422; bot asks again | `test_parse_weight`, `test_log_transaction_rejects_bad_input` |
| Duplicate phone number | HTTP 409 | `test_register_without_phone_and_duplicate_phone` |
| API down | Bot: "server not reachable"; dashboard: "Cannot reach the MITRA API" + Retry, red status dot | `test_api_down_is_reported_not_crashed`; screenshot check |
| Telegram connection drops mid-reply | Bot retries 4 times; conversation still advances | `test_reply_retried_after_dropped_connection` |
| Bot restarted | Registrations kept; API client not overwritten | `test_persistence_keeps_api_client_on_restart` |
| Database reseeded under a registered collector | Bot notices and asks to register again | `test_stale_registration_after_db_reset` |
| Classifier missing or below 70% | "in development"; logging continues with the plain list | `test_status_in_development_*`, `test_photo_when_classifier_in_development` |
| Camera suggests the wrong material | Collector's choice wins; override recorded on the lot | `test_collector_overrides_wrong_suggestion` |
| Non-image upload / photo over 10 MB | HTTP 422 / 413 | `test_classify_route_errors` |
| Collector asks to be forgotten | Name, phone, Aadhaar digits and photos deleted; lots kept anonymous; totals unchanged | `test_erase_collector_keeps_anonymous_lots`, `test_forget_flow_yes` |
| HTML in a collector's name | Escaped in bot messages and the PDF | `test_receipt_and_escaping` |
| Port already in use at start | Launcher stops with a clear message | manual run of `start.cmd` |
| A service crashes while running | Launcher prints its last log lines and stops everything | manual run (API killed while running) |

## Manual checks

- Dashboard viewed in Microsoft Edge at **1920×1080 and 1024×768**: all four views, no horizontal scroll, no console errors.
- **Live update:** a lot logged through the API appeared on the Collector Map after **2.9 s**.
- **Telegram on a real phone:** registration works (after fixing two bugs found this way: persisted bot data overwrote the API client, and one dropped connection lost a reply).
- EPR PDF opened and checked visually: one-page summary plus lot annex.
- Photo classifier: **90.5% held-out accuracy** on 378 TrashNet photos (report: `backend/data/models/mitra_cv_meta.json`).

## Known limitations (documented, not bugs)

1. **Demo data is synthetic.** Collectors, lots, aggregators and recyclers are invented; the latter two are marked "(synthetic)" and their registration numbers contain `SYN`.
2. **No login on the API.** It listens on `127.0.0.1` only, so nothing on the network can reach it. Production needs authentication before it is exposed.
3. **SQLite.** Fine for one laptop; Postgres is the Phase-2 swap.
4. **Internet needed for** Telegram and for the OpenStreetMap background tiles. Without it: pins still draw on a blank map, and `offline_demo` replaces the phone.
5. **Classifier limits (TrashNet):** no PET vs HDPE distinction (both suggested), no e-waste photos (never suggested), "trash" recall only 70%. Always a suggestion.
6. **First run on a new machine** downloads about 1 GB (mostly PyTorch). Do the first run on venue Wi-Fi well before the demo, or on a hotspot.
7. **Newly logged lots have no aggregator yet**, so they appear on the map and in totals but not in the Material Flow chart until an aggregator is recorded (no aggregator step in the bot yet).
8. **Reference prices** are indicative FY24-25 values from a CSV, not a live MCX feed.
