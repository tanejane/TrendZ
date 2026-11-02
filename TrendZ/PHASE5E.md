# Phase 5E: evidence-gated creator candidates

Approved H1 prototype only. Not independent validation; no universal ranking,
combined score, campaign-performance forecast or commercial/ROI integration.
The review set has 102 assisted and 2 manually resolved units, not independent gold.

## Run and review

Use the existing Flask setup and dependencies:

```powershell
.\.venv\Scripts\python.exe app_backend.py
```

Open `/trend-detail/glass-skin`. Under Creator Candidates, select a positive
Product Fit context and click View candidates. Each product can require a different
specialization. Changing any context clears previous results; failures offer retry.
The original trend, intelligence, assistant and ROI flows remain unchanged.
Non-pilot topics explicitly report that no frozen candidate context exists.

The section uses neutral styling, responsive cards and native accessible controls.
Cards show evidence state, reviewed profile/specialization/affinity, sufficiency,
reference counts, audience and engagement availability, reasons and limitations.
Expandable evidence includes titles/dates/source links, review revisions/basis,
descriptive engagement counters and Product Fit provenance. One selected video
does not establish sustained affinity. Reviewed topic evidence is not independent
per-video explicit/proxy validation.

## Read-only API

`GET /api/creator-candidates/context/<topic_id>` bootstraps the frozen positive
product choices and four pins. It does not evaluate candidates. No credentials
or live API requests are needed for these frozen views.

`GET /api/creator-candidates` requires all of:

| Parameter | Accepted value / scope |
|---|---|
| topic_id | One of the eight pilot topic IDs |
| query_id | canonical only; aliases are not silently merged |
| product_id | Any product in the frozen 32-product catalogue |
| market | MY (catalogue context, not inferred audience) |
| product_fit_version | product-fit-rules-1 |
| catalogue_version | my-curated-2026-10-16-evidence-v1 |
| review_revision_hash | 9235148176a44bc5ec32721c5d4abfd40928d1845538f979f19619cc75219666 |
| creator_policy_version | creator-candidate-h1-v1 |
| required_market_evidence | optional (default), verified |
| engagement_requirement | optional (default), available, five_valid_samples |

All evaluation requests must explicitly pin versions. Missing pins or malformed,
unknown or duplicate parameters return 400; mismatched pins 409; unknown topic or
product 404; unreviewed market/query scope 422; absent or corrupted snapshots 503.
No POST/PUT save operation is exposed. Unreviewed creator-topic pairs are not
returned as negative evidence. Unknown audience is not a default penalty; verified
MY audience is required only when explicitly requested. The optional requirements
reuse the Phase 5D H5/H6/H7 requirement gates; all other H1 rules stay unchanged.

PowerShell API example (retrieve pins rather than copying the hash):

```powershell
$base = 'http://127.0.0.1:5000'
$context = Invoke-RestMethod "$base/api/creator-candidates/context/glass-skin"
$args = @{
    topic_id = 'glass-skin'; query_id = 'canonical'; market = 'MY'
    product_id = 'mb-fresh-unspecified'
    product_fit_version = $context.pins.product_fit_version
    catalogue_version = $context.pins.catalogue_version
    review_revision_hash = $context.pins.review_revision_hash
    creator_policy_version = $context.pins.creator_policy_version
}
$query = ($args.GetEnumerator() | ForEach-Object {
    [uri]::EscapeDataString($_.Key) + '=' + [uri]::EscapeDataString($_.Value)
}) -join '&'
Invoke-RestMethod "$base/api/creator-candidates?$query"
```

Response envelope: `status`, `data_mode=real`, `policy_status`, `pins`, `context`,
`requirements`, `scope`, `presentation_order`, `counts`, `candidates`,
`independent_gold=false`, `limitations`.
Here `real` describes frozen collected/reviewed evidence, not live collection or
independent validation; candidate policy status remains explicitly prototype.

Each candidate includes identity/channel URL, `candidate_state`, reviewed domain,
specializations, topic affinity, profile support, both sufficiency states,
product-required/matched specialization, evidence IDs and video details, reasons,
warnings, market and descriptive engagement evidence, Product Fit provenance,
review basis/revisions/rationale, original readiness group, cutoff, policy version,
explicitness warning and limitations. No score or ranking field is returned.

## H1 behavior and ordering

| Internal band | User-facing state |
|---|---|
| A | strong_evidence_candidate |
| B | qualified_candidate |
| C | manual_review_only |
| abstain | unavailable |
| ineligible | ineligible |

Production gates are ported from the frozen Phase 5D H1, with parity checked against
all 264 positive and 1,784 blocked creator-topic-product contexts. A requires fully
supported profile, matching specialization, moderate/strong affinity and sufficient,
linked repeated-topic evidence. B allows supported/partial profiles and limited
reviewed affinity/evidence. Missing specialization is manual-only, not inferred
expertise. Insufficient evidence abstains; explicit no_fit is ineligible. Product
blocks precede creator gates. Original screening-explanation problems warn but do
not invalidate corrected reviewed fields. Pink Oil quarantine remains intact.

Presentation order is the five states above, then stable creator ID, **not relative
merit**. Popularity magnitudes do not enter gates. Counter availability is optional.
Counts below are product-linked contexts, not unique creator counts:

| Scope | Strong | Qualified | Manual | Unavailable | Ineligible |
|---|---:|---:|---:|---:|---:|
| Positive products (264) | 29 | 119 | 54 | 62 | 0 |
| All products (2,048) | 29 | 119 | 54 | 191 | 1,655 |

Glass Skin / FIT ME FRESH TINT: 0 strong, 2 qualified, 2 manual-only, 4 unavailable.
Sarthak is qualified for that makeup context but manual-only for HA 15ml skincare.
This demonstrates product-specific requirements, not a relative creator rank.

## Frozen evidence and integration boundaries

`services/creator_candidate_policy.py` contains only approved H1 gates and the
optional requirements. `services/creator_candidates.py` verifies sealed input
SHA-256 values plus the canonical combined review hash before serving a process-
local snapshot. Responses are detached copies. No review database is opened.
Restart Flask to reload evidence; a new snapshot needs explicit new pins and tests,
not silent replacement of the current sealed inputs.

Required files (keep these with any deployment of this prototype):

- `reports/phase5c/final-v1/creator_profile_review_export.json`
- `reports/phase5c/final-v1/creator_affinity_review_export.json`
- `reports/phase4d-lite/predictions_after.json`
- `reports/phase4d-lite/catalogue_hardened_v1.json`

No catalogue, predictions, matching rules, review labels, splits or evaluation
logic are changed. The original `/api/product-fit` deliberately still serves its
earlier catalogue; the new selector explicitly identifies the hardened context.
Product Fit provenance retains original frozen warnings, including warnings that
reflect the snapshot producer's historical evaluation status.

The data covers fixed cohort-derived channels only. Sample dates vary. Some
channels are brands/republishers; availability is not a suitability endorsement.
No Malaysian audience, sponsorship, product use, historical views or engagement
velocity is inferred. Final independent creator suitability validation is absent.

## Tests and reproducible output

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_creator_candidates -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py'
.\.venv\Scripts\python.exe scripts/creator_candidate_report.py --output reports/phase5e/new-reproduction
# With Flask running on 5018 and Playwright + Chrome installed:
node tests/creator-candidates-browser.cjs
```

Use `TEST_BASE_URL` for a different browser-test server. Browser tests cover eight
topics, product-dependent specialization, audience requirements, stale-card
clearing, source expansion, retry, safe text/URLs and desktop/mobile screenshots.
Python tests cover state/failure gates, exact frozen parity, version validation,
no popularity dependence, immutable inputs and absence of numeric ranking fields.

`reports/phase5e/implementation-v1/` holds metrics, all-eight-topic API examples
and the reproduction report. Existing output directories are never overwritten.
No Campaign Scenario or ROI integration is included.
