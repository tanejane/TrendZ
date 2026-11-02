# Phase 5B: Creator Evidence Expansion

Backend evidence collection and audit preparation only. No Creator Fit ranking,
combined score, UI, campaign recommendations, sponsorship inference or Product Fit changes.

## Scope and Sampling

The seed set is derived from the eight existing canonical size-5 cohorts in
`reports/phase2-measured/pilot.sqlite3`. Current relevant audit labels, label-event
IDs, immutable video/channel identity and source query are verified. The pilot
refuses to expand unless it resolves exactly those 40 unique channels. There is
no arbitrary channel-ID argument or unrestricted influencer search.

For each seed, the collector requests:

1. `channels.list(part=snippet,contentDetails,id=<seed>)` to find its uploads playlist.
2. One `playlistItems.list(part=snippet,contentDetails,maxResults=50)` page.
3. One `videos.list(part=snippet,statistics,status,id=<up to 50 IDs>)` request.

It selects up to 20 videos, ordered by publication time, among public videos with
matching channel identity and valid publication dates in that bounded page.
This means the most recent public videos **within the first 50 playlist entries**,
not a guaranteed complete channel history. Missing, private, mismatched and future
items are excluded and recorded. Fewer than 20 valid videos are not backfilled.
The optional numeric flags only narrow this fixed rule (maximum 50 scanned IDs).

There is no `search.list` call, no new channel discovery, and no MY-region filter
on uploads retrieval. The maximum is three calls per creator / 120 requests per
40-channel pass, before explicit retries. Each endpoint currently has a 1-unit
quota cost; actual project quotas/authorization still apply. No automatic retry
loop is used. Authorization/quota/rate-limit failures halt further requests in
that invocation; three consecutive channel failures also halt the pass. Skipped
channels are explicitly unavailable. API/network failures are not empty success.

Official references:
[channels.list](https://developers.google.com/youtube/data/reference/rest/v3/channels/list),
[playlistItems.list](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/list),
[videos.list](https://developers.google.com/youtube/data/reference/rest/v3/videos/list).

## PowerShell Commands

Run from the project root. Use the existing Python environment; no dependencies
are added. The API key is read only from the process environment and is never
written into raw request parameters, reports or console output.

```powershell
# If stored in your Windows user environment:
$env:YOUTUBE_API_KEY = [Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY', 'User')

# Read-only seed/budget inspection; no API requests or migrations:
.\.venv\Scripts\python.exe scripts\creator_phase5b.py plan

# Collect / resume the same fixed batch:
.\.venv\Scripts\python.exe scripts\creator_phase5b.py collect `
  --batch-id phase5b-initial `
  --output reports\phase5b\live-initial

# If a previous output directory exists, use a NEW output directory for resume.
# Successful per-channel captures in the same batch are reused, consuming no
# extra requests. Failed captures can be attempted again; all attempts stay raw.
.\.venv\Scripts\python.exe scripts\creator_phase5b.py collect `
  --batch-id phase5b-initial `
  --output reports\phase5b\live-resume

# Explicit refresh, which consumes API quota again and creates new immutable runs:
.\.venv\Scripts\python.exe scripts\creator_phase5b.py collect `
  --batch-id phase5b-initial --retry `
  --output reports\phase5b\live-refresh

# Offline reuse of evidence ALREADY stored for these channels:
.\.venv\Scripts\python.exe scripts\creator_phase5b.py reuse-existing `
  --output reports\phase5b\existing-only

# Deterministic tests, no API credentials needed:
.\.venv\Scripts\python.exe -m unittest tests.test_creator_phase5b -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The default `--db` is the measured pilot database, not `data/trendz.sqlite3`.
`--max-videos 20 --scan-limit 50` are defaults. `--as-of` accepts a timezone-aware
timestamp; observations/review events later than that cutoff are excluded, never
turned into historical measurements. Without it, live results use actual response
timestamps, recorded separately for each creator.

`reuse-existing` is explicitly **not completed live expansion**. It never claims
fresh uploads or a representative creator-content denominator. It supports
development/review while credentials or access are unavailable.

## Persistence and Reproducibility

Raw API responses and safe request parameters are stored exactly once per
channel capture in the existing immutable `youtube_runs` table, with
`kind=creator_expansion`. The existing archive format is reused. Each request
has its own start/retrieval timestamp; full raw responses remain in the run.
The report contains exact run/request/item references. Collection keys bind the
batch ID, frozen seed fingerprint and sampling policy. Successful/partial
captures resume without refetching; explicit retries create new run IDs.

Six new creator tables plus an existing migration-table entry (no existing schema semantics are changed):

| Table | Purpose |
| --- | --- |
| creators | Source identity, observed display name, first/last evidence observation, fixed cohort provenance |
| creator_contents | Lightweight creator/run/video links and exact raw reference; no duplicate raw snippets/counters |
| creator_profiles | Immutable provisional profile proposal revisions and supporting video IDs |
| creator_specializations | Proposed specialization evidence linked to profile revision; not final classification |
| creator_topic_affinity_runs | Immutable per-creator/topic component bundles and cutoff/version |
| creator_topic_evidence | Raw-reference links, matched terms/fields and inherited human seed provenance |
| migrations | Existing table receives `creator_evidence_v1`; this is not a new replacement table |

There are **six new creator tables**, plus an entry in the existing migrations
table. The table above explicitly distinguishes the migration entry from a new
table. No separate creator-engagement raw table is necessary; video counters
remain in existing raw runs and later cohort snapshots remain reusable.

Run, content, profile, specialization and affinity/evidence histories are immutable.
The creator identity index may extend first/last observed timestamps as new raw
evidence arrives. Raw references are checked against video/channel identity before
linking. Replaying the same derived analysis is idempotent.

Frozen Product Fit files/reports/review database are hash-checked before and after
the command. Existing raw-run digest records must remain unchanged. No existing
watchlist, trend metrics, relevance labels, cohort membership or daily snapshots
are rewritten by this phase.

## Provisional Profiles and Topic Evidence

`data/creator_evidence_v1.json` is a separate, versioned screening vocabulary;
the frozen tracked-topic configuration is not changed. It covers the eight
pilot topics, explicit aliases, supporting-only proxies, domain cues and beauty
specializations. Hits record the exact term and title/description field.

Examples of safeguards:

- Nicotinamide can support a niacinamide mention; vitamin B3 alone is only a proxy.
- Retinal, tretinoin and broad retinoids do not become retinol synonyms.
- Lip stain/tint and hair-oiling variants are recognized with word boundaries.
- Deepavali/Diwali requires makeup/look context; festival-only mentions do not count.
- Dewy/radiant skin is not silently equated to explicit glass-skin coverage.
- Hydration/ceramides alone do not become an explicit barrier-topic match.

Keyword absence is not a verified negative. Descriptions, boilerplate, language,
negation and visual/audio meaning can all cause screening errors. Domain and
specialization proposals require repeated video evidence and retain provisional
status. `other` and `general_beauty` are not missing-data defaults.

The Phase 5A profile-review gate remains draft: >=3 sampled videos, >=14 elapsed
publication days and >=2 publication weeks, with >=2 matching videos supporting a
specialization/domain proposal. Passing this gate means **ready for human review**,
not validated stable specialization. Human profile and specialization fields stay blank.

No strong/moderate/weak labels are enacted. Every topic result has provisional or
unavailable state and `strength_state=null`. Sensitivity compares the two Phase 5A
draft gates: 2 videos/7 days/2 weeks versus 3 videos/28 days/3 weeks. Both confirmed-only
and screen-assisted gate outcomes are exposed, not interpreted as calibrated affinity.

Inherited relevant seed labels and new suggestions are separate. Seed video IDs
outside the selected recent sample are listed separately, never included in its
numerator or denominator. Topic shares are only exposed for the bounded upload
sample. For query-selected legacy reuse, shares are null with an explicit reason.
Even upload-sample shares describe the selected sample, not total channel output.

## Descriptive Engagement and Market Evidence

- Median views/likes/comments: median of available per-video retrieval-time counters.
- Variability: population standard deviation for >=2 observed counters, otherwise null.
- Like/view ratio: median of individual `likes/views` values with views>0 and both
  counters present. This is not a ratio of medians. Missing values are not zero.
- Engagement velocity is unavailable in this expansion. No historical engagement
  is reconstructed from publication dates; no popularity-weighted fit is calculated.
- Public channel country, if returned, is partial self-declared location evidence
  with raw source reference, not verified residence or audience geography.
- No field automatically becomes verified market evidence. Malaysian audience and
  Malaysian-market content remain unknown without direct reviewed evidence.
- MY search provenance applies only to the seed retrieval. Uploads have no regionCode.

## Review Artifacts

Each invocation writes a new, protected-from-overwrite output directory:

- `report.md`: per-channel scanned/detail/selected counts, profile review readiness,
  confirmed versus proposed topic history, overlap, sensitivity, engagement availability
  and source limitations.
- `metrics.json`: machine-readable summary and collection manifest.
- `review_dataset.json`: creator identity, sampled videos, full available descriptions,
  publication/retrieval timestamps, counters, proposed profiles/topic evidence, exact
  provenance, and blank final human fields. These are not gold labels.
- `raw/<run_id>.json`: existing immutable YouTube export format, live collection only.

The dataset is ready for manual inspection in an editor. This phase prepares but
does not finalize/import new creator gold labels; profile validation precedes Phase 5C.
No frontend/API route is added, and no final Creator Fit method is implemented.
