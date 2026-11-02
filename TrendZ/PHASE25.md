# Phase 2.5: immutable YouTube runs and manual relevance

Google Trends collection, formulas and scaling are unchanged. No combined score,
lifecycle, forecasting, AI, recommendations or UI changes are introduced.

## Storage

The existing `pilot.sqlite3` gains these additive tables:

| Table | Purpose / key |
| --- | --- |
| youtube_runs | Immutable full capture JSON, SHA-256, kind, retrieval timestamp; run_id PK |
| youtube_discoveries | Raw search occurrences, topic/query/market/window, publication time, page and API position; run/topic/query/window/page/position PK |
| youtube_audit_candidates | Frozen audit sample with candidate ID, originating run, video ID and audit rank |
| youtube_audit_labels | Current human label, notes and label timestamp per candidate |
| youtube_label_events | Append-only history of label changes |
| youtube_cohorts | Frozen per-topic canonical cohort, audit ID and selection timestamp |
| youtube_cohort_members | Video ID, audit candidate ID and publication timestamp; cohort/video PK |
| youtube_video_snapshots | Retrieval-time views/likes, snapshot date, publication timestamp, status, reason and raw video response; run/cohort/video PK |

All tables except the current-label table reject UPDATE and DELETE through SQLite
triggers. Replaying an identical run ID/content is a no-op; different content under
that ID is rejected. Duplicate API appearances retain separate page/position rows;
publication counts and cohort memberships deduplicate by video ID. Different runs
retain repeated discoveries independently. Immutable full JSON includes failed
windows, request parameters without credentials, raw responses and missingness.

`youtube_runs/<run_id>.json` provides portable checksummed exports. Retrospective
query runs share a collection invocation ID. Latest lookup is derived from archived
runs, not a replacement of earlier captures. Existing normalized observation tables
remain a downstream projection; the new archives are the reproducibility authority.
Legacy `--snapshot` is archived too, but is explicitly NOT a relevance-selected cohort.

## Commands

Run from the repository root in PowerShell. Commands do not load `.env`; set the
environment variable in the invoking shell without committing it:

```powershell
$env:YOUTUBE_API_KEY = "YOUR_KEY"
.\.venv\Scripts\python.exe scripts/youtube_phase25.py archive-legacy
.\.venv\Scripts\python.exe scripts/youtube_phase25.py audit-summary
```

The bootstrap archives the nine surviving legacy captures, then freezes the existing
160 canonical candidates (20 per topic). It cannot reconstruct captures overwritten
before Phase 2.5. Re-running bootstrap preserves existing CSV edits.

Edit `reports/phase2-measured/canonical_relevance_audit.csv` in a spreadsheet editor.
Only edit `label` and `notes`. Labels are exactly `pending`, `relevant`,
`partially relevant`, `irrelevant`. Preserve IDs and save as UTF-8 CSV. The sample is
recency-ranked as in Phase 2; audit rank is NOT the original search API rank. Original
API page/position and window are available via the candidate's run ID in SQLite and
raw archives. URLs, titles, descriptions and channel information support manual review.

```powershell
.\.venv\Scripts\python.exe scripts/youtube_phase25.py audit-import
.\.venv\Scripts\python.exe scripts/youtube_phase25.py audit-summary
.\.venv\Scripts\python.exe scripts/youtube_phase25.py audit-export --file reports/phase2-measured/audit-fresh.csv
.\.venv\Scripts\python.exe scripts/youtube_phase25.py cohort-create --size 5
.\.venv\Scripts\python.exe scripts/youtube_phase25.py daily
# Explicit historical publication-day catch-up; counters are still measured TODAY:
.\.venv\Scripts\python.exe scripts/youtube_phase25.py daily --date 2026-10-14
```

`--output` selects another report directory/database. `--audit-id` identifies a frozen
audit; export refuses to overwrite existing files. Imports validate the entire file
before saving, allow partial files, and record label-change history. Labels are human
judgments, not inferred from keywords. `relevance_precision.json` is refreshed on
bootstrap, import and summary.

Strict precision = relevant / labelled; inclusive precision = (relevant + partially
relevant) / labelled. Labelled excludes pending. With zero labels, both are null,
not zero. Report counts include pending and all three judgments. This is precision
on a small selected sample, not population precision or recall.

## Fixed cohorts

Default size is five; configurable from one to ten. For each canonical topic select
only manually `relevant`, measured candidates, ascending frozen audit rank. Partially
relevant, pending and synthetic candidates are excluded. Fewer labels yield a smaller
cohort; zero labels yield no cohort. Selection is frozen on creation, including the
label evidence and publication date. Re-running creation doesn't replace membership.
Later label edits/discoveries do not silently change a cohort. The current canonical
audit remains entirely pending, so no real relevant cohort exists yet.

## Daily process and provenance

`daily` searches one completed UTC publication day, default yesterday, using the
eight original canonical queries and MY market. It requests one page per topic,
maximum 50 results. A next-page token marks a capped, incomplete lower-bound sample.
Empty successful searches are measured zero discovered matches, not an upload census.
Failed windows have null counts and explicit reasons. UTC local boundary filtering
and video-ID deduplication prevent boundary/duplicate inflation. Search is content
supply, not demand. Late indexing, removed/private videos and capped pages cause
missingness; this mode does not claim to enumerate all uploads.

One `videos.list` request per nonempty fixed topic cohort saves current counters for
each member. Publication timestamp and retrieval/snapshot date stay separate; current
views are NEVER historical views. Missing videos/counters remain null with reasons,
not zero. Cohort IDs preserve comparability; daily raw data stays separate from the
retrospective metric series and is not added to existing dashboard metrics yet.

The default once-per-day/configuration command skips an existing daily run without
API calls. `--retry` explicitly creates another immutable run and spends quota again.
Changing cohort/configuration also permits a new run; do not run concurrent collectors.
There is no scheduler; invoke once daily yourself or via your own scheduled task.

Requests per daily invocation: 8 search + C statistics, where C is the number of
nonempty topic cohorts, 0-8. Current pending audit: 8 requests. All eight cohorts:
16 requests maximum, even with cohort size ten. No pagination or automatic retries.
Repeated snapshots on the same date remain separate by run ID.

Google's current quota docs specify a default 100 search calls/day in a separate
Search Queries bucket; each statistics request costs one unit in the general bucket.
Project settings can differ. Extra pages, retries, other collectors and retrospective
runs share quota. HTTP 403/429 can still occur; errors are retained rather than
aggressively retried. Check your Cloud project's actual quota before scheduling.
See [official quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost).
API-data retention and compliance requirements also need review before production;
this pilot's append-only research archive is not a production retention policy.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Fixtures/mocks only: immutable SQL and exports, duplicate occurrences, label import
atomicity/persistence/precision, relevant-only frozen cohorts, completed daily window,
eight-topic request counts, missing video/counters, caps/failures, separate publication
and snapshot dates and independent repeated snapshots. No live API calls are made.
