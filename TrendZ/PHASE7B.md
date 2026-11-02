# Phase 7B: deterministic assistant infrastructure

No model, provider, SDK or AI assistant is connected. This phase adds an internal
Python gateway and executable fixtures, not a conversational agent or public API.
The existing quantitative services remain authoritative and unchanged.

## Files and boundaries

- `services/assistant_contracts.py`: nine closed argument schemas and validation.
- `services/assistant_sources.py`: read-only adapters, allowlists and comparisons.
- `services/assistant_runtime.py`: trusted context, registry and confirmation.
- `services/assistant_grounding.py`: exact field-based response validation.
- `scripts/assistant_harness.py`: 32 scripted synthetic infrastructure cases.
- `scripts/assistant_review.py`: trusted local operator confirmation demonstration.
- `tests/test_assistant_gateway.py`: fixture, security and metamorphic tests.

There is no new HTTP assistant endpoint, drawer, provider or automatic planner.
The nine tools cannot access SQL, shell, filesystem, arbitrary URLs, ingestion or
editing. Source adapters alone resolve known local frozen artifacts. They project
only bounded evidence and approved HTTPS source URLs, excluding credential URLs
and private reviewer rationale. Titles and descriptions are data, never commands.

## Internal tool contracts

All arguments are closed objects (`additionalProperties: false`) with required
fields, enums and bounds. The executable schemas are exported as
`reports/phase7b/harness-final/tool_contracts.json`. Validation implements the schema
subset actually used, not every feature of general JSON Schema.

| Tool | Scope / behavior |
| --- | --- |
| `get_trend_intelligence` | Exact topic, query and market; six separate dimensions |
| `compare_trends` | Two to four authorized distinct topic scopes; side-by-side evidence |
| `get_product_fit` | Exact topic/query/market/product; frozen Product Fit evidence |
| `list_positive_product_fits` | Authorized topic/query/market; explicit pagination |
| `get_creator_candidates` | Selected product context; stable presentation, not merit ranking |
| `get_creator_candidate_evidence` | Exact selected creator; reviewed evidence and limits |
| `get_campaign_context` | Exact product and creator; existing eligibility and version pins |
| `evaluate_campaign_scenario` | Complete context pins, explicit assumptions and trusted confirmation |
| `trace_decision` | Trend -> product -> creator -> optional same-context scenario |

Every call requires the opaque `context_ref`. Unknown IDs, aliases, mismatched
markets, products or creators fail closed; there is no fallback to a demo topic.
List tools return totals, returned counts, truncation and next offset. Undelivered
rows are not citeable. No combined score, winner, global rank or new analytics exist.

## Context and registry

`AssistantSources(root, database_path)` uses existing frozen services and a temporary
SQLite backup for a consistent turn snapshot. `AssistantTurn` lasts at most 300
seconds by default, permits 10 attempted tool calls, bounds requests to 64 KiB and
delivered payloads to 512 KiB. Pagination limits are 1-20 rows, offset at most 1000.

The trusted host calls `turn.controller().bind(scopes)` after revalidation. Client
values are hints, never authority. Each context captures topic/query/market,
optional product/creator, source/method hashes, review hash, policy, Product Fit,
catalogue, scenario and calculation versions. Caller-invented or stale pins fail.
Rebinding invalidates earlier context and consent handles; cross-turn handles fail.

Each result is canonical immutable JSON bytes with detached reads: call ID,
validated arguments, scope, source pins, delivered payload/hash, evidence IDs,
basis map, warnings, unavailable reasons, limitations and capture timestamp.
Trusted normalized assumption inputs are separate `user_input` ledger events.
Only this ledger can be cited. There is no automatic conversation persistence.
Expiry is checked on access; explicit close clears private turn state and deletes
the temporary snapshot. This is not physical memory zeroization or a background
expiry daemon. Harness exports deliberately persist synthetic fixture audits only.

## Grounding contract

Responses contain all four sections:

1. `what_trendz_knows`
2. `what_trendz_does_not_know`
3. `user_assumptions`
4. `scenario_calculation_shows`

Claims include basis, exact scope, value, unit, state and a reference containing
call ID, delivered `/payload/...` JSON pointer and payload hash. Basis values are
`observed`, `reviewed`, `upstream_calculated`, `diagnostic`, `user_assumption`,
`derived_scenario` and `workflow_request`. Required warnings/limitations must be
preserved exactly. Invalid pointers, hidden fields, stale hashes, altered numbers,
units, enum states, bases, scope, canonical text and section confusion are rejected.

The renderer intentionally produces constrained field-based text. Arbitrary prose
or paraphrase is not accepted as validated output. Structural grounding is not
semantic entailment, independent source verification or model-quality evaluation.
Availability/provisional/unavailable evidence states remain in source payloads.

## Explicit authorization

Only a trusted local Python host holds the controller capability. It is not a tool
and cannot be obtained through tool arguments. `prepare_assumptions` delegates to
the unchanged Phase 6B normalizer, displays explicit values/units and creates a
hash. `confirm_assumptions` requires approval of that exact draft/hash. Manual-only
creator acknowledgement is a separate explicit action with a matching reason.
Confirmation refs are short-lived, context/hash-bound and consumed on success.
Forged, expired, replayed or cross-turn consent cannot authorize a calculation.

Scenario evaluation delegates to the unchanged live Phase 6B context resolver;
source changes after binding cause stale-context rejection. Trend momentum and
creator popularity cannot supply missing assumptions or alter economics.

An interactive demonstration (operator supplies explicit assumption JSON in the
existing Phase 6B format, with no inferred defaults):

```powershell
.\.venv\Scripts\python.exe scripts\assistant_review.py --topic-id glass-skin --product-id mb-fresh-unspecified --creator-id <creator-id> --assumptions <assumptions.json>
```

It prints the normalized preview and units, then requires typing the displayed
`CONFIRM` token. Manual-only contexts require a second explicit acknowledgement.
`--export <new-file.json>` is optional and exclusive-create; confirmation handles
are redacted/hashed in audit exports. Normal operation saves no conversation.
This local capability boundary is not network authentication. A future web host
needs authenticated sessions, CSRF protection and a genuinely trusted confirmation
UI; exposing these Python operations directly to a model or client is unsafe.

## Comparison and trace restrictions

Google Trends absolute-interest comparisons require matching request-level
provenance: shared request/artifact hashes, query terms, market, observation window,
timeframe, category, property and request type. Independently normalized 0-100
series are not absolute demand measures. The current production adapter does not
establish a shared request artifact, so it returns side-by-side evidence with
`not_comparable` and a reason. E03 tests a synthetic shared artifact only; it does
not certify current live-source comparability.

Trace preserves direct/indirect Product Fit, reviewed creator basis, unknown market
evidence, source pins, assumptions and scenario limits. Candidacy is explicitly not
endorsement, product use, causal effectiveness or predicted campaign success.
The 102 assisted / 2 manual Phase 5C basis remains visible, not independent gold.

## Legacy isolation

`POST /api/malaysia/chatbot` now returns HTTP 410 with
`legacy_assistant_retired`. The old fixed-template/demo fallback is not connected
to this gateway. Dashboard and trend detail chat entry points and unsafe chat
`innerHTML` interpolation have been removed. Structured evidence links remain;
the visible note says no AI/model is connected. Existing product, creator and
campaign flows remain separate and retain their original services.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_assistant_gateway -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe scripts\assistant_harness.py
# Use a NEW directory for a deliberate synthetic audit export:
.\.venv\Scripts\python.exe scripts\assistant_harness.py --output reports\phase7b\harness-v1
```

E01-E24 remain development fixtures; E25-E32 retain their predeclared withheld
split. All are now executable deterministic regressions, not an untouched future
model holdout or independent validation set. Checks include tool sequences,
canonical citations/facts, required warnings, prohibited state changes, scope/pins,
confirmation, source-text injection, fake URLs, budgets and malformed payloads.
Metamorphic tests change momentum/popularity without changing economics, compare
product-specific specialization behavior and reject changed pins.

`reports/phase7b/baseline.json` records 24 protected upstream files, including the
measured source database, review store/exports, Product Fit evidence/predictions,
Creator H1 and Phase 6B context/schema/economics/eligibility. Harness verifies these
before and after and exports exact hashes. See `reports/phase7b/VERIFICATION.md`
for the executed results and limitations. No provider cost/latency, reasoning
quality, campaign quality or AI accuracy is measured. Phase 7C requires separate
provider selection and approval.
