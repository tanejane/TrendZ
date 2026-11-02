# Local Interview Demo

## Start

From the folder containing `app_backend.py`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\run_demo.py --port 5000
```

Open `http://127.0.0.1:5000/`. Use another port if occupied. No source API or LLM
credential is required. This is a dated measured snapshot, not a live feed. The
launcher uses a temporary database copy and does not preserve watchlist edits.

## Five-Minute Journey

1. **Dashboard:** distinguish 18 configured topics from the eight-topic pilot and
   from topics with stored observations. Show source coverage, not score/rank.
2. **Glass Skin:** follow its topic link in the same tab. Inspect Demand Momentum,
   Evidence Quality and an unavailable dimension. Explain the dates and scope.
3. **Product Fit context:** select `mb-fresh-unspecified` in the frozen product
   selector. Its supporting compatibility is indirect, not evidence of efficacy.
4. **Creator Candidates:** select View candidates. Expand evidence/review provenance.
   Show unknown audience and the distinction between qualified and manual-only.
   Presentation order is not relative merit.
5. **Campaign:** open Build Campaign Scenario on a qualified card. No reach, fee or
   conversion assumptions are pre-filled from the creator's views.
6. **Economics:** enter the illustrative assumptions below, calculate, then change
   one input and show stale displayed results clearing. Demonstrate sensitivity and
   break-even; do not describe any output as a predicted campaign result.
7. **Assistant:** show Provider not configured. Explain the frozen nine-tool gateway
   and deterministic fixtures, not a live model or mock answer.

### Explicit Synthetic Planning Assumptions

These values are only a reproducible UI/calculator demonstration, not observations,
benchmarks, recommended budgets or forecasts. They are unrelated to the sampled creator's popularity.

| Field | Example |
| --- | --- |
| Objective / format / channel | conversion / short-form demonstration / YouTube |
| Start / exclusive end | 2026-11-01 / 2026-12-01 |
| Creator fee / media / production / other | MYR 600 / 200 / 150 / 50 |
| Budget ceiling | MYR 1,200 |
| Assumed reach / net AOV / gross margin | 1,000 people / MYR 50 / 40% |
| Low / base / high assumed conversion | 2% / 5% / 8% |

Under these assumptions only: cost MYR 1,000; base revenue MYR 2,500; base net
profit MYR 0; ROI -60% / 0% / 60%; break-even conversion 5%. These are algebraic
consequences of inputs, not confidence bounds, measured performance or a recommendation.

## Required Runtime Evidence Assets

Preserve the exact relative paths and hashes in `demo/verified_facts.json`:

```text
reports/phase2-measured/pilot.sqlite3
reports/phase4d-lite/catalogue_hardened_v1.json
reports/phase4d-lite/predictions_after.json
reports/phase5c/final-v1/creator_profile_review_export.json
reports/phase5c/final-v1/creator_affinity_review_export.json
```

Configuration in `data/tracked_topics.json`, `data/demo_trends.json`,
`data/product_intents.json` and `data/products/catalogue.json` is also required by
the existing services, even when demo seeds are not displayed. The full regression
suite additionally uses historical report/review artifacts and local review stores;
a minimal runtime bundle is not a full research/test archive.

`reports/` and SQLite are ignored by Git. A source-only clone will not have the
full frozen demo. Include evidence privately with the local demo, or separately
review redistribution permissions and packaging before publishing raw metadata.
Do not publish credentials or private review-session databases. The launcher fails
clearly if its assets are absent or invalid; it does not fabricate substitutes.

## Screenshot Provenance

The captures in `demo/` use the measured snapshot and frozen candidate policy.
`product-fit.png` shows the hardened Product Fit selector, not a new matching
method. Campaign and sensitivity screenshots use the synthetic assumptions above.
`hero.png` is an actual first-viewport dashboard capture, not a fabricated UI mockup.
Architecture HTML is a diagram source; its PNG is rendered by the audit browser.

## Boundaries To Say Aloud

Reviews are assisted, not independent gold. Geography is not inferred from region.
Snapshots are dated. One-video matches do not establish sustained affinity.
Saturation and velocity may be unavailable. No live LLM, combined score,
endorsement inference, campaign prediction or production deployment is claimed.
