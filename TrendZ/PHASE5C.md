# Phase 5C: Creator Profile + Topic Affinity Review

Local human-review workspace only. No Creator Fit ranking, combined score,
campaign recommendations, new collection, or Product Fit changes.

## Fixed Review Scope

Input: `reports/phase5b/live-initial/review_dataset.json` (40 creators, 747
sampled videos). The local session pins its SHA-256, the collection manifest,
provenance, as-of times and all provisional evidence. Later source changes
require a new session, not replacement of the fixed review units.

- **40 creator profiles**, one per channel identity.
- **64 creator-topic affinity pairs**: union of seeded topics and topics with
  at least one explicit screened match. These are candidate pairs, not confirmed
  positive labels. Supporting-only proxies do not automatically add pairs.
- Original evidence groups remain **24 review-ready / 16 insufficient creators**.
  Their affinity rows are respectively 44 / 20. Evaluation preserves these fixed
  groups even when human judgments disagree with the draft gate.
- Other possible creator-topic pairs are not negatives and are not evaluated.
- Two prior seed videos outside the latest sample remain explicitly outside the
  current denominator. Missing prior title/description fields are shown unavailable,
  not reconstructed or fabricated.

The review DB is separate: `data/creators/review_sessions/local.sqlite3`.
It does not modify the measured pilot DB, Phase 5B creator tables, relevance labels,
cohorts, Product Fit rules/catalogue/labels/reports or the main application.

## Start and Export

From the repository root:

```powershell
# Creates/reuses the source-pinned session and initial blank-label datasets:
.\.venv\Scripts\python.exe scripts\creator_review.py prepare

# Local review workspace; independent from the main website and Product Fit UI:
.\.venv\Scripts\python.exe scripts\creator_review.py serve --port 5016

# Progress, no evaluation conclusions:
.\.venv\Scripts\python.exe scripts\creator_review.py status

# Current reviews and revision history; use a new output directory per export:
.\.venv\Scripts\python.exe scripts\creator_review.py export `
  --output reports\phase5c\export-01

# Only after all 104 review labels and required evidence checks are saved:
.\.venv\Scripts\python.exe scripts\creator_review.py evaluate
```

Open `http://127.0.0.1:5016/`. If this port is occupied, choose another `--port`.
No API credential or new dependency is required. The server binds loopback only,
with debug/reloader disabled. Use the existing Flask environment.

Initial review datasets:

- `reports/phase5c/creator_profile_review.json`
- `reports/phase5c/creator_affinity_review.json`

All 104 human labels start null. Proposals never initialize final domains,
specializations, approved video selections or affinity labels. The existing
human-reviewed YouTube seed evidence stays in separate immutable provenance.

## Review Methodology

### A. Creator Profile

Inspect the creator's content examples, full available descriptions, dates,
source IDs and per-domain/specialization text-screen counts. Proposed labels are
not evidence by themselves. Repeated description boilerplate, product links,
hashtags, multilingual wording and titles without actual topical content can
mislead the screen.

Choose one label:

- `supported`: evidence supports the explicitly selected final profile at the
  sampled scope; final classifications may correct the proposal.
- `partially_supported`: some profile claims have support, but classification
  remains provisional/qualified. This is not stable profile validation.
- `unsupported`: the proposal is not established by inspected evidence; record
  corrections if established, otherwise distinguish uncertainty from rejection.
- `insufficient_evidence`: do not finalize domain/specialization fields when the
  available content cannot establish them.

Explicitly select approved domain(s), beauty specializations, supporting video
IDs, sufficiency, explanation support, review basis, reviewer and a short note.
Beauty specializations require a beauty-domain assertion. Unknown is not `other`;
general_beauty is not a fallback for missing evidence.

At least two selected videos on distinct publication dates are required for a
fully `supported` stable profile. One video can support only a qualified/partial
judgment or abstention, never a stable classification. The draft 3-video/14-day
Phase 5B gate is not automatically enforced as human truth: reviewers can disagree
with it while preserving the original evidence group in analysis.

### B. Creator x Topic Affinity

Inspect all sampled content, not only keyword hits. Select the videos that actually
support this topic; a reviewer can identify relevant content missed by the screen.
Keep ingredient/look/occasion proxies separate from explicit topic coverage.

Allowed labels:

- `strong_affinity`: sustained, compelling sampled evidence with explicit rationale.
- `moderate_affinity`: repeated meaningful evidence, but less comprehensive or qualified.
- `weak_affinity`: limited/one-off evidence; not sustained coverage.
- `no_affinity`: inspected sample does not support this topic, not a statement that
  the creator never covers it or is unsuitable for every campaign.
- `insufficient_evidence`: content or history is too limited/ambiguous to decide.

Strong/moderate labels require >=2 approved relevant videos on distinct publication
dates. This is a logical single-video safeguard, not implementation of the draft
strong/moderate numeric thresholds. Final strength remains an explicit human judgment.
Weak requires at least one relevant video. No-affinity cannot simultaneously approve
relevant videos. Topic reviews cannot edit domain/specialization classifications.

Approved sample share is the approved **current-sample** relevant-video count divided
by current sampled videos. Approved prior seeds outside that sample are retained
as evidence but excluded from numerator/denominator. Span, recency and repeated
coverage are computed only from approved relevant video IDs with publication dates;
no repeated search occurrences or counter snapshots become additional videos.

Sample windows vary under most-recent-N selection, including 110 videos older than
56 days. All judgments remain time-scoped; this is not a validated 56-day affinity
formula. A valid skincare/makeup/haircare profile can coexist with insufficient
topic affinity. Profile approval never automatically approves topic pairs.

### Explanation and Assistance

Explanation support is a separate mandatory judgment: `supported`, `unsupported`
or `insufficient_evidence`. Check the provisional explanation's factual evidence
(counts, text mentions, dates, format of the claim and source links), not whether
the eventual fit/affinity decision agrees with it. Source linkage alone does not
prove that a claim is supported.

Copy-to-draft controls copy proposed classifications or screened evidence only.
They do not select a final review label or save it. They mark the draft's review
basis as assisted. The reviewer must explicitly approve/edit and save; the actual
review basis is recorded in every revision. None of these records is automatically
declared independent human gold, even after all rows have labels.

## Revision and Safety Model

The separate review SQLite schema has:

- `metadata`: immutable source hash, manifest and session identity.
- `units`: immutable fixed profile/affinity contexts and evidence group.
- `reviews`: latest explicit human judgment and optimistic revision number.
- `events`: append-only before/after snapshots, reviewer, basis and timestamps.
- `reports`: immutable finalized report snapshots keyed by review revision hash.

Saving is atomic. Stale revisions return 409 instead of overwriting another tab.
Returning to pending creates a new event and preserves all earlier approvals.
Exports include revision history in the same read transaction as current labels.
Export/prepare will not replace different files or unsaved edits. No bulk final
acceptance or implicit gold-label conversion is provided.

The workspace rejects non-loopback hosts/clients, cross-origin writes and writes
without a per-process review token. Source text is rendered as text, not HTML.
Only fixed video/channel IDs generate outbound YouTube links/thumbnails. Cache
is disabled and source/review files stay local; the optional public thumbnail
requests do not invoke the YouTube Data API.

## Evaluation Plan and Formulas

No final evaluation is generated until **both** review units are fully labelled.
Incomplete status/exports provide progress only. Every metric below is reported
overall and separately for the original review-ready/insufficient groups where
defined. Undefined denominators return null, not zero.

| Measure | Definition / boundary |
| --- | --- |
| Creator-profile agreement | Exact proposed domain AND specialization set match against explicit human fields; only non-abstaining rows with a nonempty proposal are comparable. Missing proposals are reported separately. |
| Specialization precision | Micro TP/(TP+FP), comparing proposed and approved specialization sets on non-abstaining profile rows. Partial reviews remain identifiable by label; these are reviewed-scope judgments, not independent ground truth. |
| Specialization coverage | Micro TP/(TP+FN) against approved sets, plus fraction of answered profiles with a specialization proposal. Not population recall. |
| Topic-affinity agreement | **Unavailable:** Phase 5B assigned no categorical affinity predictions. Never manufacture predictions from draft gates to report categorical accuracy. Human label distributions are available after review. |
| Draft-gate sensitivity | Separate 2-video/7-day/2-week and 3-video/28-day/3-week contingency tables versus human sustained/strong judgments; exploratory, not enacted classifications or accuracy. |
| One-video overmatching | Number/rate of reviewed strong/moderate labels supported by fewer than two approved videos; backend validation prevents these saves. No rate for an empty high-label denominator. |
| Abstention | insufficient_evidence count / reviewed units, separately for profiles and affinity pairs. |
| Popularity bias | Descriptive outcomes stratified by creator median-view quartiles, unknown views separate. No causal bias claim, significance test or popularity weighting. Engagement never enters fit judgments automatically. |
| Multi-topic behavior | Per creator: reviewed candidate topics, positive human-affinity topics and sustained human-affinity topics. No combined score. |
| Evidence-sufficiency failures | Sufficiency counts and exact exception rows with reviewer notes, label, explanation judgment and fixed group; no fabricated failure causes. |
| Explanation traceability | Selected video references with a recorded run link / selected references, reported as structural traceability only. Human explanation-support/failure rate uses supported+unsupported judgments; insufficient checks stay separate. |

Final JSON includes per-topic outcomes, group metrics, partial/abstaining labels,
review basis, selected-evidence components and reviewer-noted exceptions. A concise
Markdown report accompanies CLI evaluation. The UI evaluation button saves an
immutable report and displays its JSON; CLI `evaluate` exports Markdown/JSON.

The 64 candidate pairs are enriched for seed/screen matches, not a fixed balanced
gold test set or all 320 possible pairs. Pairs share creators; do not treat them
as independent observations or infer generalization from this single session.
Any later rule adjustment needs a separately frozen independent holdout, not
tuning and evaluating on the same visible proposals.

## Market, Engagement and Product Fit Boundaries

Market/audience evidence is displayed separately and not edited/inferred through
affinity labels. MY seed-search viewability is not Malaysian creator residence
or audience geography. Public declared channel country remains partial evidence.
Unknown audience geography stays unknown.

Engagement is descriptive retrieval-time median views/likes, valid like/view ratios
and variability. Publication timestamps do not establish historical engagement
or growth. No velocity, endorsement, sponsorship, product use, recommendation,
campaign or ROI inference is added.

Product Fit v1 and its evidence, rules, labels, ranking and evaluation reports are
unchanged. The public frontend and Phase 5B producer tables are not connected to
these new human labels automatically. Stop before Phase 5D ranking.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_creator_review -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q

# Optional read-only real-session desktop/mobile smoke checks:
$env:NODE_PATH = 'C:/path/to/node_modules-with-playwright'
node tests/creator-review-browser.cjs
```

Tests cover blank labels, fixed-unit separation, source pinning, revision history,
immutability, stale writes, single-video/date guards, classification/affinity
independence, null denominators, group evaluation, missing categorical predictions,
popularity independence, prior-seed denominator exclusion, pending finalization,
CSRF/host guards, export history and source-text XSS handling. Synthetic approvals
exist only in temporary test databases. Browser checks make zero POST writes to
the real session.
