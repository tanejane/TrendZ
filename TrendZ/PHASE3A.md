# Phase 3A: independent backend dimensions

## API and data selection

`GET /api/intelligence/<topic_id>` selects the canonical query. An alias is explicit:
`GET /api/intelligence/glass-skin?query_id=routine`. Unknown topics return 404; unknown
query IDs return 400; non-GET methods return 405. Aliases are never pooled.

The endpoint reads **measured evidence only**, even when the existing app is in demo
mode. It never migrates a database, initializes missing SQLite files, recalculates
legacy caches, ingests sources, saves labels, or calls an external API. A missing
database returns all dimensions unavailable for a configured topic. Demo observations
and demo captures are excluded. No existing endpoint, UI or commercial logic changes.

It uses the existing `TRENDZ_DB_PATH`/`DATABASE_PATH`, not an implicit second database.
To expose the completed pilot when starting the server in PowerShell:

```powershell
$env:TRENDZ_DB_PATH = (Resolve-Path reports/phase2-measured/pilot.sqlite3).Path
.\.venv\Scripts\python.exe app_backend.py
```

Response envelope:

```json
{
  "status": "success",
  "data_mode": "real",
  "topic_id": "hair-oil",
  "query_id": "canonical",
  "query": "hair oil",
  "market": "MY",
  "available_queries": [{"query_id": "canonical", "query": "hair oil"}],
  "method_version": "intelligence-dimensions-v1",
  "dimensions": {
    "demand_momentum": {},
    "signal_persistence": {},
    "content_saturation": {},
    "creator_diversity": {},
    "engagement_velocity": {},
    "data_confidence": {}
  }
}
```

The above illustrates field structure only; `available_queries` includes all configured
aliases in actual responses. Each populated dimension has:

| Field | Meaning |
| --- | --- |
| state | available, provisional or unavailable |
| components | Independent measured values, component-level availability/units/reasons and supporting counts |
| source | Array of source names; never a merged measurement unit |
| query_id, query, market | Exact selected configuration |
| observation_window | Inclusive start/end dates; null when no relevant observations |
| retrieval_window | Earliest/latest retrieval timestamps for cited evidence |
| method_version | Versioned dimension method |
| evidence_identifiers | Relevant observation, series, immutable run/hash, cohort, audit-candidate and video IDs |
| scope | What the measurement describes and does not describe |
| unavailable_reasons | Blocking reasons when unavailable |
| provisional_reasons | Qualifications when provisional |
| quality_warnings | Persistent caveats, including unvalidated semantics and sampling limits |

`available` means supported **at the stated scope**. It does not mean that a beauty
topic has been validated, a population estimated, or future behavior established.
`provisional` means a descriptive proxy or qualified measurement. `unavailable` means
requirements are not met. An unavailable dimension may retain supporting sample
counts or separately available components; it never converts them into the missing
dimension value. JSON null is retained for unavailable components.

## Methods and evidence gates

Demand momentum reuses `daily-windows-v1`: growth is
`100 * (mean(C)/mean(B) - 1)`, for consecutive seven-day windows B and C. It needs 14
contiguous days and positive B. Acceleration subtracts growth(A,B) from growth(B,C),
needs 21 contiguous days and positive A/B, and is expressed in percentage points.
Google request/query/market/timeframe consistency, daily cadence, duplicate dates and
0-100 values are validated. Only the latest intact request-relative series is selected;
independently normalized requests are never stitched.

Search sparsity policy v1: if more than half the **stored days of the selected series**
are zero-valued, otherwise calculable momentum/persistence is provisional. This is a
transparent engineering warning threshold, not a calibrated confidence model. It does
not delete, replace or reinterpret zeros. Search meaning remains unvalidated and
query-relative even when a numerical component is available.

Signal persistence keeps sources separate. Persistence is the fraction of C strictly
above mean(B), requiring 14 contiguous days. Volatility is population std(C)/mean(C),
requiring seven days and a positive C mean. This is short-window elevation, not long-term
longevity. Search-only availability is permitted with publication components explicitly
unavailable; publication-only results remain provisional query-supply proxies.

Content saturation has **no saturation-level formula or benchmark**. The level stays
unavailable. A comparable uncapped publication-growth proxy makes the dimension
provisional, never available as market saturation. Any capped, failed, overlapping or
request-mismatched window blocks supply growth. Publication counts deduplicate video
IDs, filter UTC half-open publication boundaries, and include measured zero discoveries
only within successful windows. Missing windows/days are not imputed. Only one immutable
run is selected: the latest matching query/market capture. Daily runs are not implicitly
stitched into retrospective runs, so a single daily run cannot satisfy growth history.

Creator diversity exposes sampled video/channel counts, largest-channel publication
share and `HHI = sum(channel_share^2)`, with shares based only on videos with channel
IDs. At least two identified channels are required. Missing channel IDs are counted.
Unreviewed query samples are provisional, including capped samples; they are never
population estimates. A fully labelled audit for the selected run permits an available
**audited relevant sample** statistic; irrelevant/partially relevant candidates are
excluded. A partial audit yields only a provisional explicitly reviewed subset.
Wrong request provenance blocks creator attribution. Duplicate video appearances do
not inflate publication shares. The real audit remains deferred, not completed.

Engagement velocity requires an explicitly human-relevant frozen cohort, with matching
member IDs and original discovery run/query/market provenance. Select the latest cohort
and its latest two distinct snapshot dates; repeated same-day runs are not separate
daily observations. For each matched video, use actual elapsed retrieval hours and
calculate `delta_views/hours` and `delta_likes/hours` separately. Sum valid per-video
rates as **matched-sample** rates; expose matched counts and fixed cohort size.
Incomplete pairs or missing likes make supported view velocity provisional. No valid
view pairs makes velocity unavailable. Nonpositive intervals, date/timestamp conflicts,
snapshots predating cohort selection, changed publication timestamps, unavailable
videos and negative/corrected counters are rejected, not clamped to zero. Different
cohorts and legacy sampled-view totals cannot form pairs. No current pilot topic has
the required fixed cohort/snapshots.

Data confidence is an available **diagnostic profile**, not a number, probability,
weighted grade or confirmation score. It reports Google coverage/missing/zero days,
request validation reasons, YouTube cap/failure/completeness counts, selected-run audit
coverage/status, fixed cohorts and snapshot counts. Reproducibility explicitly identifies
legacy-surviving captures. With no evidence the dimension is unavailable. A complete
date range never means uncapped supply or reviewed relevance.

## Architecture and examples

- `services/intelligence_evidence.py`: read-only SQLite snapshot, strict source/query/market filtering.
- `services/intelligence_components.py`: independent descriptive calculations and validation gates.
- `services/intelligence_service.py`: six dimension envelopes, scope, states and evidence identifiers.
- `app_backend.py`: one read-only route; no cache or commercial changes.
- `tests/test_phase3a.py`: fixture/mock-only tests; no external calls.

No schema changes are needed. Existing immutable Phase 2.5 records are never updated.
The normalized Google observations remain identified by observation/series IDs, not
misrepresented as immutable YouTube runs. Older overwritten captures remain lost.

Generate complete **actual API responses for all eight topics**, plus a state table:

```powershell
.\.venv\Scripts\python.exe scripts/report_phase3a.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Outputs are `reports/phase3a/responses.json`, `states.json` and `README.md`. The report
checks that the source database hash is unchanged and does not invent missing data.
No live ingestion or audit import occurs. No UI, score, lifecycle, forecasting, AI,
recommendations or ROI changes are included.
