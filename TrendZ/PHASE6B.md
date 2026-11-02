# Phase 6B: Campaign Scenario + Deterministic ROI

This implements the approved Phase 6A scenario architecture, not campaign-performance
prediction. Product Fit v1, Creator Candidate H1, reviews, intelligence formulas and
source evidence remain unchanged. No new dependencies or credentials are required.

## Run and flow

```powershell
.\.venv\Scripts\python.exe app_backend.py
```

Open `/roi-insights`, select a topic, positive product and usable creator, then
Build Campaign Scenario. The same action is present on trend-detail creator cards.
The entry point supports all eight frozen pilot topics even in demo dashboard mode.
The scenario page separates evidence, user assumptions and calculated outcomes.

Objective and format are blank until explicitly chosen. All commercial quantities
start blank, not with seeded flattering values. Enter costs explicitly, including
zero costs. Currency is MYR and channel must be selected as YouTube. Dates use an
exclusive end date. Formats are tutorial, product review, routine integration,
educational explainer, short-form demonstration and creator-led promotional post.
Format is planned, not a proven creator capability. Awareness and consideration
are cost-only. Conversion is the only objective with monetary outcomes in v1.

Positive Product Fit is required; supporting_fit remains indirect. Strong/qualified
creators can proceed. Manual-only requires a checkbox and written reason and keeps
its state. Unavailable/ineligible cannot be overridden. No sponsorship, willingness
to collaborate, creator product use, endorsement or MY audience is inferred.

## API

- `GET /api/campaign-scenarios/context`: identity/version-pinned evidence bootstrap.
- `POST /api/campaign-scenarios/evaluate`: stateless conditional calculation.

Context GET requires topic_id, query_id, product_id, creator_id, market, the four
Phase 5E pins (product_fit_version, catalogue_version, creator_policy_version,
review_revision_hash), and `calculation_version=campaign-economics-v1`. Optional
`required_market_evidence` and `engagement_requirement` retain Phase 5E semantics.
Only frozen canonical/MY scope is supported; no alias merging or scope fallback.

Bootstrap returns `context_ref` with those pins plus exact trend method/snapshot,
topic configuration, product assessment, selected candidate and context hashes.
The read-only trend provider backs up SQLite into a disposable temporary snapshot
and reads both dimension results and source manifests from that same consistent
copy. No source migrations/metric cache writes occur. No scenario is stored there.
The 30MB pilot database makes copying a modest per-request overhead; this simple
MVP intentionally favors reproducibility over a new cache/registry architecture.

POST body:

```json
{
  "schema_version": "campaign-scenario-v1",
  "calculation_version": "campaign-economics-v1",
  "context_ref": "<use the complete object returned by context GET>",
  "assumptions": {
    "objective": "conversion", "format": "short_form_demonstration",
    "channel": "youtube", "currency": "MYR",
    "campaign_window": {"start_date": "2026-11-01", "end_date_exclusive": "2026-12-01"},
    "costs": {"creator_fee": "600", "media_spend": "200", "production_cost": "150", "other_cost": "50"},
    "budget_ceiling": "1200", "conversion_basis": "assumed_reach",
    "population": {"value": 1000, "unit": "unique_reached_people", "basis": "user_entered", "source_ref": null},
    "conversion_rates": {"low": "0.02", "base": "0.05", "high": "0.08"},
    "aov": "50", "gross_margin_rate": "0.4",
    "manual_candidate_acknowledgement": {"accepted": false, "reason": null}
  }
}
```

The quoted context placeholder above must be replaced with the actual JSON object.
Full ready-to-use requests and responses are in `reports/phase6b/implementation-v2/api_examples.json`.
The example commercial values are synthetic, not recommended benchmarks.

Example PowerShell bootstrap from a selected candidate (four pins come from the
existing Product Fit context endpoint):

```powershell
$base = 'http://127.0.0.1:5000'
$p = Invoke-RestMethod "$base/api/creator-candidates/context/glass-skin"
$args = @{
  topic_id='glass-skin'; query_id='canonical'; market='MY'
  product_id='mb-fresh-unspecified'; creator_id='<selected creator_id>'
  product_fit_version=$p.pins.product_fit_version
  catalogue_version=$p.pins.catalogue_version
  creator_policy_version=$p.pins.creator_policy_version
  review_revision_hash=$p.pins.review_revision_hash
  calculation_version='campaign-economics-v1'
}
$query = ($args.GetEnumerator() | ForEach-Object {
  [uri]::EscapeDataString($_.Key)+'='+[uri]::EscapeDataString($_.Value)
}) -join '&'
$context = Invoke-RestMethod "$base/api/campaign-scenarios/context?$query"
# Include $context.context_ref as an object in the POST body with explicit assumptions.
```

POST re-resolves upstream evidence instead of trusting submitted states or metrics.
Wrong/stale versions, hashes or required manual acknowledgement return 409;
missing pins/malformed/unknown fields 400; unknown creator 404; invalid values or
blocked candidacy 422; missing/corrupt sources 503. Known oversized bodies return
413. Duplicate context query parameters are rejected. An updated context requires
explicit refresh; manual acknowledgement is reset in the UI on refresh.

Valid incomplete commercial inputs return `scenario_state=partial`, with null and
unavailable reasons per affected output, not fake zeros. Blocked requests never
contain calculated outcomes. Changing assumptions immediately clears old results.

Response objects: `evidence`, `assumptions`, `calculated_outcomes`, `sensitivity`,
`break_even`, `warnings`, `provenance`, `limitations`. `field_classification`
distinguishes observed/reviewed/upstream-calculated evidence from user assumptions
and derived outputs, including assumed-rate columns in sensitivity. Whole-response
`data_mode=assumption_based` and `output_kind=assumption_based`; evidence retains
its own real/unavailable context. No output is presented as measured performance.

## Calculation definition

```text
C = creator_fee + media_spend + production_cost + other_cost
orders = supplied_people * assumed_conversion_rate
revenue = orders * net_AOV
gross_profit = revenue * gross_margin_rate
net_profit = gross_profit - C
ROI_ratio = net_profit / C
ROI_percent = 100 * ROI_ratio
break_even_revenue = C / gross_margin_rate
break_even_orders = C / (net_AOV * gross_margin_rate)
minimum_whole_orders = ceil(break_even_orders)
break_even_conversion_rate = C / (supplied_people * net_AOV * gross_margin_rate)
```

Use finite nonnegative decimal strings (integers also accepted), at most 12 decimal
places, monetary bounds 10^12, integer people up to 10^12, rates/margins in [0,1].
Decimal arithmetic uses 50-digit precision. Only displays round money/percent to
two places using ROUND_HALF_UP. Full computed values remain in exports; no early
rounding or whole-order substitution into continuous break-even rate.

Exactly one population basis: `assumed_reach` / `unique_reached_people` or
`target_population` / `target_people`. External planning values require a source
reference. No creator views, subscribers, trend metrics or Google interest are
used as reach or conversion input. CTR/post-click CVR and ambiguous recovery-rate
inputs are unsupported and rejected, not silently multiplied.

Zero cost means ROI undefined, not infinity. Zero population permits zero sales
when other inputs exist but no break-even rate. Zero margin/AOV prevents finite
break-even where its denominator is zero. Missing inputs stay unavailable, never
default zero. Rate >100% needed for break-even is flagged infeasible, not clamped.
Budget ceiling is not a cost and does not silently cap costs; overrun warns.

Gross margin includes COGS, not campaign spend. AOV and margin must share the same
net-revenue/tax/discount/returns basis. Avoid double-counting shipping/fees already
in margin as other_cost. Net profit means modeled campaign contribution, not
audited company income. No causal incrementality, break-even time or success
probability is estimated. Duration does not boost returns.

Low/base/high rates must be explicitly supplied and ordered. Missing low/high stay
unavailable; no automatic optimism/pessimism factors or confidence intervals.

## Worked example

Costs MYR1,000; assumed unique reach1,000; net AOV MYR50; gross margin40%:

| Assumed rate | Orders | Revenue | Gross profit | Net profit | ROI |
|---|---:|---:|---:|---:|---:|
| 2% | 20 | RM1,000 | RM400 | -RM600 | -60% |
| 5% | 50 | RM2,500 | RM1,000 | RM0 | 0% |
| 8% | 80 | RM4,000 | RM1,600 | RM600 | 60% |

Break-even: RM2,500 revenue, 50 orders, 5% conversion. Not a prediction.

## Legacy cleanup and boundaries

`/roi-insights` now uses one evidence-gated scenario entry point; the random chart,
random ROI table, multiplier simulator and preset commercial recommendations are
removed. Demo trend-detail commercial predictions/revenue and dashboard/watchlist
ROI numbers are replaced with scenario entry links. Noncommercial demo features
remain separate. `/api/roi-prediction` and `/api/business-value` return 410 with
replacement references; no clients should use their former mock outputs.
Legacy numeric fields remain in untouched demo source records for compatibility,
but are not a second visible commercial calculator or inputs to the new service.

No upstream rule/catalogue/review/source files are modified. Context hashing
does not guarantee all old evidence revisions can be replayed after source changes;
export JSON retains the exact resolved evidence/assumptions/results. No database
stores user scenarios. No new assistant, AI, training, recommendations or forecast.
Currently local prototype only; no authentication/shared persistence deployment.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_campaign_scenarios -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py'
.\.venv\Scripts\python.exe scripts/campaign_scenario_report.py --output reports/phase6b/new-run
# With the local Flask server running (default browser-test port 5020):
node tests/campaign-scenario-browser.cjs
```

Set `TEST_BASE_URL` for another port. Reports under `reports/phase6b/` include
worked API examples, blocked examples, protected hashes and desktop/mobile
screenshots. Output report directories are immutable; use a new directory to rerun.
