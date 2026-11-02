# Phase 2 heterogeneous ingestion pilot

This is collection/validation only. There is no alias aggregation, lifecycle
classification, combined score, forecasting, AI, recommendations or UI redesign.

## Configuration

data/pilot_phase2.json fixes MY and the inclusive 56-day window
2026-08-19 through 2026-10-13 (eight weekly YouTube discovery windows).
The canonical topic IDs, names, categories and original query strings are unchanged.
Aliases have IDs scoped to their topic. Each observation stores query_id and query.

| Topic | Canonical query | Separate experimental aliases |
|---|---|---|
| niacinamide | niacinamide serum | niacinamide |
| retinol | retinol skincare | retinol |
| skin-barrier | skin barrier repair | skin barrier |
| hair-scalp-care | scalp care | scalp treatment |
| lip-tint | lip tint | lip stain |
| glass-skin | glass skin | glass skin routine |
| deepavali-glam | Deepavali makeup | Deepavali glam; Diwali makeup |
| hair-oil | hair oil | hair oiling |

Seventeen independent queries. Aliases are wording experiments, not asserted
equivalents: scalp treatment can include clinical content; hair oil can include
recipes/manufacturing; Deepavali/Diwali wording may return different populations.

## Repeatable offline demonstration

Run from the repository directory:

```powershell
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --fixture
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --fixture --source csv --file reports/phase2-fixture/observations.csv --output reports/phase2-csv-fixture
```

These outputs are synthetic, is_demo=true, and use separate local SQLite files.
The 28 forward fixture snapshot dates extend into a synthetic future, not measured history.
Fixture observations never appear in measured reports or the production real-mode API.
All fixture audit labels start pending; no relevance is invented.

## Google fixed-window collection

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-google-trends.txt
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --source google --topic niacinamide --query-id canonical --max-queries 1
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --source google
```

The second command is a limited access probe; the last attempts all 17 queries.
Google is optional and uses unofficial pytrends. Rate limits, response changes
or network/access failures are recorded per query and leave data unavailable.

Each request contains exactly one search term, geo=MY, cat=0, gprop="" (Web Search),
UTC and timeframe="2026-08-19 2026-10-13". No topic entity substitution or
OR-combination of aliases occurs. Full parameters and query IDs are stored
in metadata; series IDs fingerprint the parameters and retrieval version.
Daily components compare windows within a single returned request only.
Repeat retrievals remain separate versions; the report selects the latest version
per query/source/metric without splicing. Raw 0-100 levels across independently
normalized terms, windows or request versions must not be ranked or compared.
Weekly/coarser cadence blocks daily metrics. Gaps/partial rows remain missing.
Google interest is a relative demand/search signal, not absolute searches.
Related/top/rising queries are period-level metadata, not dated daily series.

## YouTube retrospective publication discovery

```powershell
$env:YOUTUBE_API_KEY = "your-key"
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --source youtube --query-id canonical
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --source youtube --resume
```

Each query has eight UTC windows, type=video, order=date, regionCode=MY,
maxResults=50, and one page per week by default. Default search budget=64 calls
per run; canonical queries go first. Seventeen queries require up to 136 searches
before extra pagination. --resume skips previously uncapped completed queries;
run later for aliases or increase the explicit budget after checking your quota.
--max-pages-per-week and --max-search-requests control pagination/cost.
This is an operational cap, not a promise about the account's available quota.

Responses are filtered locally to their exact weekly date boundaries and
deduplicated by video ID within each query. source observations describe
currently discoverable public publication counts, not a census of historical
uploads. Deleted/private/unindexed videos are absent. Publication time can
differ from original upload time. Exhausted pagination does not prove a census.
Failed windows generate no manufactured zero history. Successful searches
can record zero discovered matches without claiming zero total market uploads.
Capped/failed windows invalidate publication-series component analysis.

Present-day views/likes are retrieved separately using videos.list and stored
against retrieval dates. Publication dates NEVER backdate those statistics.
Raw current statistics, channel metadata, titles, URLs and retrieval timestamps
are retained. regionCode identifies videos viewable in Malaysia, not Malaysian
creators, audience nationality or Malaysian viewing activity.

## Forward fixed-cohort snapshots

```powershell
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --source youtube --snapshot
```

Run once daily for 28 days after discovery. This command makes no search calls
and uses up to 50 fixed discovered video IDs per query. Missing cohorts or
hidden/missing statistics remain unavailable. No scheduling happens automatically.
Cumulative counter components describe changes in stored counter levels;
they are not reconstructed historical views or a measure of consumer demand.
The first snapshot cannot support growth; 14/21 days are needed for growth/
acceleration. Do not mix new videos into an existing cohort series.

## Manual query relevance audit

reports/phase2-measured/relevance_audit.csv contains up to the first 20 unique
videos per topic/query, ordered by publication recency across the discovered
weekly results (not a relevance-ranked sample). Includes title, description,
channel, URL, publication time and present-day views/retrieval time.
Set label to relevant, irrelevant or uncertain, and add notes.
The denominator for relevance fraction is relevant+irrelevant labels;
pending and uncertain counts are reported separately. Unreviewed means
unavailable, not 0% relevant. Re-running preserves existing labels for unchanged
topic/query/video IDs. Labels do not silently filter or alter observations.
Rebuild after editing labels:

```powershell
.\.venv\Scripts\python.exe scripts/pilot_phase2.py --source none
```

## Reports and dataset

Each measured/fixture output directory contains:

- observations.csv: normalized query-level observations and full provenance.
- analysis.json: coverage, missing dates/zeros, observation/version counts,
  collection blockers, manual relevance and comparable-series validation.
- analysis.csv: component values and explicit unavailable reasons.
- report.md: readable per-query/source results and direction.
- collection.json and raw/: preserved collection status and captures.
- relevance_audit.csv: manual audit candidates, initially pending.
- pilot.sqlite3: local persistent pilot dataset (never overwrites the app database).

Google demand/search and YouTube supply/activity stay separate.
Every metric remains query/source/series-specific; no topic metric aggregates aliases.
Direction is simply positive/negative/flat according to available recent growth;
it is not a lifecycle or emerging classification.
Formulas/minimum-history rules are the Phase 1 formulas in services/metrics.py
and README.md. Report dates identify actual observed windows, not implied freshness.
Snapshot expected coverage ends at report generation date; fixture coverage
uses the explicitly synthetic snapshot span.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests are deterministic and make no network calls. Phase 2 tests cover
alias separation, fixed request parameters, eight discovery windows, present-day
counter timestamps, request budgets, capped/failed windows, manual audit
availability, and exclusion of synthetic rows from measured reports.

References:
[Google Trends normalization](https://support.google.com/trends/answer/4365533?hl=en),
[YouTube search](https://developers.google.com/youtube/v3/docs/search/list).
