# Getting Started

## Requirements

- Python 3.10+ (the original audit used Python 3.13)
- Flask 3.0.3 and optional Gemini SDK (`requirements.txt`)
- Node.js for the JavaScript tests; Playwright + Chrome for browser checks
- No API key for stored-snapshot viewing; `YOUTUBE_API_KEY` only for explicit ingestion

## Scope of this public archive

This code package intentionally excludes frozen research artifacts and SQLite databases. The screenshot-based measured demo **cannot run after a clean clone** without those approved local artifacts. It is not a hosted or continuously updating app.

The measured demo needs the following paths *with original content and hashes*:

```text
reports/phase2-measured/pilot.sqlite3
reports/phase4d-lite/catalogue_hardened_v1.json
reports/phase4d-lite/predictions_after.json
reports/phase5c/final-v1/creator_profile_review_export.json
reports/phase5c/final-v1/creator_affinity_review_export.json
```

The project additionally uses tracked topic/product configuration under `data/` (included). Historical comprehensive test suites depend on further retained report fixtures and local review stores that are **not** published.

**Do not upload** credentials, raw social-media response dumps, review-session databases or any evidence without explicit redistribution/rights review. No fabricated substitute is provided by the measured launcher.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Measured demonstration requires the separately approved files above:
.\.venv\Scripts\python.exe scripts\run_demo.py --port 5000
```

On macOS/Linux use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`. Open `http://127.0.0.1:5000`. The launcher creates a disposable SQLite copy, and any local watchlist edits are temporary. Optional port: `--port 5022`.

`TRENDZ_DATA_MODE=real` uses observation-backed behavior; `demo` explicitly switches to historical synthetic screens and is **not** the measured portfolio demonstration. `TRENDZ_DB_PATH` overrides the writable database path. The Flask backend now loads a local `.env` file; see [Gemini explainer](GEMINI_ASSISTANT.md). Never commit `.env`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts\assistant_harness.py
node --test tests/*.test.cjs
```

Expect missing-evidence errors for workflows needing archived artifacts in a public clone. Browser checks need Chrome/Playwright, a running app, `TEST_BASE_URL` and a new `SCREENSHOT_DIR`. No test in this public package is claimed to have passed merely because an earlier private audit passed.

## Suggested first code-reading path

Read `services/intelligence_service.py`, `services/product_fit.py`, `services/creator_candidate_policy.py`, `services/campaign_economics.py`, then `services/assistant_grounding.py`. Use [ARCHITECTURE.md](../showcase/ARCHITECTURE.md) for the larger map and [DEMO_GUIDE.md](../showcase/DEMO_GUIDE.md) for the five-minute research walkthrough.
