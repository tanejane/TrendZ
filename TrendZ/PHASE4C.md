# Phase 4C: Human Product Fit Validation

This phase adds a local review workflow, not new matching rules. The catalogue,
intents, deterministic matcher, production Product Fit API, trend intelligence,
ROI, cohorts, lifecycle boundaries and existing frontend are unchanged.

**Initial status: 0/256 human labels; validation pending.** No real validation
metrics, false-positive conclusions or methodology-adjustment recommendation have
been generated. Automated tests use synthetic judgments in temporary databases only.

## Start the Local Review

From the project directory, in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\product_review.py serve
```

Open http://127.0.0.1:5015/ and keep the terminal running. This is a separate
loopback-only Flask tool; the existing TrendZ app can stay on its current port.
No credentials, external service or new dependency is needed. Use `--port 5016`
if the default port is occupied. Never publish this review tool as a public service.

On first start, it freezes the existing 256 canonical topic/query/product identities,
family-disjoint dev/evaluation membership, source records, intent, predictions,
matching method and catalogue version. The current predicted fit state is separate
from the human label. Historical `sampling_stratum_machine_only` values are preserved
verbatim, even where they differ from the frozen current prediction; they are not gold.

The page shows topic/query/market, exact product name, brand, category/subcategory,
requested and matched ingredients, listed ingredient count/completeness, declared
benefit claims, format, application area, variants, supporting field/source evidence,
missing evidence, contradictions, full INCI/field quality, and source URLs.

1. Filter by topic or pending queue. Read product evidence and linked sources.
2. Choose exactly one human label: `direct_fit`, `supporting_fit`, `no_fit`, or
   `insufficient_evidence`. None is selected by default. Notes are optional (1000 characters).
3. For a **predicted match**, independently mark its explanation supported or
   unsupported by cited evidence. This is not inferred from your fit label. It can
   remain pending while you work, but is needed for the final unsupported-match rate.
4. Save or Save and next pending. Labels resume when the tool restarts. Reviewer name
   is optional; save timestamps are recorded automatically. Unsaved edits warn on navigation.
5. Finish the 256 labels and all predicted-match explanation checks, then Generate
   validation report. Download its JSON, or generate JSON plus Markdown using the CLI.

Suggested label rubric: direct means explicit configured-intent compatibility;
supporting means partial/proxy compatibility with a stated evidence boundary; no_fit
means incompatible or insufficient substantive connection; insufficient_evidence
means the catalogue evidence cannot support a defensible decision. These are human
judgments: do not copy predictions, infer clinical efficacy, or assume missing INCI
proves absence. A fit disagreement does not automatically mean the explanation is
unsupported, and a traceable citation does not automatically mean its claim is supported.

## Storage and Provenance

The authoritative local session is `data/products/review_sessions/local.sqlite3`.
The original `data/products/human_review.json` remains unchanged. Exported JSON
retains its schema, ordering, IDs, split and provenance; only human fields are updated.
The composite pair ID is `topic_id/query_id/product_id`; no new identity scheme
replaces the original fields.

Tables:

- `metadata`: immutable baseline, frozen model outputs, versions, source/code hashes,
  creation timestamp and stable session ID.
- `pairs`: immutable identity, original row, current prediction and intent/evidence snapshot.
- `labels`: four-state nullable human label, notes, independent nullable explanation
  judgment, optional reviewer, save timestamp and optimistic revision.
- `events`: append-only before/after human review changes, including explicit clearing.
- `reports`: immutable completed validation snapshots keyed by label/revision hash.

SQLite transactions prevent partial saves. Concurrent stale-tab updates return 409;
reload instead of overwriting another tab. Clear review is explicit and keeps history.
Changing any frozen catalogue, intent, tracked-topic, matcher or baseline file marks
the session stale, blocks writes/finalization and preserves the old evidence for reading
and export. Do not delete/reinitialize a session to hide its history.

GET requests never save labels or finalize reports. Write requests require a per-server
token, same-origin checks and loopback host/address. External text uses textContent;
source links permit HTTPS without embedded credentials. The app has a restrictive CSP
and no remote frontend dependencies. Review databases/exports may contain private notes;
keep them local and backed up. Stop the server before copying its SQLite file.

## Export and Final Report Commands

```powershell
.\.venv\Scripts\python.exe scripts\product_review.py status
.\.venv\Scripts\python.exe scripts\product_review.py export
# Only succeeds after all human judgments are complete:
.\.venv\Scripts\python.exe scripts\product_review.py report
```

`--db PATH` selects a session, `--output PATH` selects export/report output.
Export defaults to `reports/phase4c/human_review_export.json`; the session DB retains
all revisions. Final reports use session/revision-specific filenames. Repeated
finalization of unchanged judgments returns the same report, not fabricated new results.
Edited judgments create another immutable report revision. Pending review returns
nonzero exit status with null metrics/recommendation and writes no validation report.

The JSON export also works with the Phase 4B reporting command's `--review` argument;
the Phase 4C report adds the complete confusion/error analysis. Do not replace the
fixed baseline with your export while its session is active: it is a frozen input.

## Validation Definitions

No metrics or adjustment recommendation are finalized until all 256 human labels
and all independent explanation checks for predicted matches are complete.
All measures retain both full-catalogue descriptive results and separate
family-disjoint dev/evaluation results. Per-topic results include all four states.

- **Precision@5:** human direct/supporting matches in returned top five divided by 5.
  Empty positions stay empty when fewer than five are returned. Ranking is unchanged:
  direct before supporting, stable product-ID ties. Candidate pools are explicitly scoped.
- **nDCG@5:** human grades direct=2, supporting=1, no_fit/insufficient=0; gains
  `2^grade-1`, logarithmic discount, divided by ideal DCG in that same catalogue pool.
  Null if ideal DCG is zero.
- **Catalogue-bounded recall:** returned human-positive products / all human-positive
  products in that labelled pool. Null with no gold positives; never market-wide recall.
- **Unsupported-match rate:** predicted matches independently marked unsupported /
  all predicted matches. Null if the pool contains no predicted matches. A four-state
  fit label alone cannot supply this metric.
- **Abstention rate:** predicted insufficient_evidence / all pairs. Human
  insufficient-evidence rate is a separate field.
- **Confusion matrix:** rows are human labels, columns are predicted labels; four by
  four globally, per split and per topic. Direct/supporting disagreements remain visible.
- **Confirmed FP:** predicted positive, human no_fit. Predicted positives with human
  insufficient_evidence are reported separately as uncertain/overclaimed, not definitive FP.
- **FN:** human direct/supporting with prediction no_fit or insufficient_evidence;
  the abstained-positive subset is separated from explicit rejections.
- **Same-category overmatching:** confirmed FP among category-compatible human no_fit
  candidates, with denominator and rate. Zero observed errors is not proof of generalization.
- **Pattern analysis:** deterministic counts of recorded missing/conflicting fields,
  format/application disagreements, provisional look/occasion proxies and other explicit
  evidence tags among reviewed FP/FN/abstained pairs. Multi-tag counts overlap.
  Missing ingredient/benefit evidence is reported separately. These are evidence
  co-occurrences, not an AI explanation or proof of the reviewer's causal reasoning.

The report includes each disagreement's stable ID, prediction, human label, notes,
missing evidence and contradictions. Macro ranking means omit undefined topics and
report how many topics are defined. Do not compare split-pooled ranks to a different
full-catalogue candidate universe.

## Decision Boundary

Only after completed human review, a deterministic review recommendation is emitted:
inspect disagreements/unsupported explanations for targeted adjustment, or retain the
current baseline **within tested scope** when none are observed. Prioritized patterns
come from dev, not automatic tuning on held-out evaluation. No rules change automatically.
Single-reviewer judgments, catalogue bias, tiny dev pools and cached source freshness
remain limitations. Independent repeat review/inter-rater agreement is not implemented.
No embeddings, LLMs, Creator Fit, ROI, lifecycle classifier or forecasting are introduced.

## Files and Tests

New code: `services/product_review.py`, `services/product_validation.py`,
`scripts/product_review.py`, `templates/product-review.html`,
`static/css/product-review.css`, `static/js/product-review.js`.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests\product-review-ui.test.cjs tests\product-text.test.cjs tests\intelligence-ui.test.cjs
```

`tests/test_phase4c.py` uses temporary databases and explicitly synthetic human labels
to test blank labels, preservation, save/resume/export, four-label validation,
concurrency, stale versions, immutable history, completion gates, ranking math,
confusion matrices, patterns, same-category errors, missing evidence and local security.
Browser tests use a separate disposable session, never the real reviewer database.
Verification: 112 Python tests (17 new), 13 JavaScript unit checks and 14 browser
checks pass. The real review session remains 0/256 labelled, with 30 independent
predicted-match explanation checks pending. No final validation report exists yet.
# Assisted Review Consolidation

Review assistance is stored separately from immutable predictions, splits and human labels.
`assist_source`, `assist_label`, `assist_confidence`, `assist_evidence`, `assist_source_urls`
and unresolved uncertainty are exposed on the pair and queue APIs. Assist records and import
manifests are immutable; each manifest retains input CSV contents, paths, SHA-256 hashes and
session ID. Imports are idempotent and reject conflicting suggestions, duplicates, unmatched
strict topic/query/product triples or overlapping eligible sources. Imports do not write labels.

```powershell
# Preview first; add --apply only to persist assist metadata (not human labels).
.\.venv\Scripts\python.exe scripts\product_review.py assist-import --prescreen C:\Users\ejane\Downloads\product_fit_prescreen_256.csv --research reports\phase4c\research\product_fit_research_review_34.csv
.\.venv\Scripts\python.exe scripts\product_review.py assist-import --prescreen C:\Users\ejane\Downloads\product_fit_prescreen_256.csv --research reports\phase4c\research\product_fit_research_review_34.csv --apply
.\.venv\Scripts\python.exe scripts\product_review.py serve --port 5016
```

1. Open the high-confidence pre-screen panel, inspect a topic's rows and CSV reasons, then explicitly accept that topic's pending suggestions. Already saved human labels are skipped; individual rows can be inspected and manually labelled instead.
2. Select the Researched acceptance queue for the 28 medium/high-confidence proposals. Inspect citations, evidence and uncertainty; accept or choose your own label and save. Radio buttons are never automatically selected from assistance or predictions.
3. Select Low-confidence manual review for the six unresolved cases. Quick acceptance is disabled at both UI and API level; choose a manual human label only after inspecting evidence.
4. Complete independent predicted-match explanation checks. Neither assist import nor acceptance asserts that the machine's explanation is supported. Existing notes and checks survive acceptance.
5. Export human labels or explicitly generate validation only after all required judgments are complete. Assist metadata alone never contributes to evaluation.

Acceptance requires the displayed assist digest and human revision, preserves revision history,
records the accepted assist snapshot in the review event, and never overwrites an existing label.
Topic batches are atomic and limited to high-confidence pre-screen rows; research cannot be
batch-accepted. All writes retain the existing loopback, origin and review-token protections.

