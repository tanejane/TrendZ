# Phase 4B: Deterministic Product Fit

Product Fit is **catalogue compatibility**, not a market opportunity score, product efficacy
test, personalized routine, purchase recommendation, forecast or commercial ranking.
Trend intelligence, ROI scenarios, AI assistant and fixed YouTube cohorts are unchanged.

## Catalogue and provenance

`data/products/catalogue.json` contains 32 records across 23 families/source pages:
12 skincare, 10 makeup and 10 haircare. 29 records have a verified size or shade;
three are explicitly unspecified product-level records, not verified purchasable SKUs.
The catalogue is narrow and L'Oreal-group biased, not representative of Malaysian retail.

Sources are official Malaysian L'Oreal Paris, Maybelline and La Roche-Posay PDPs,
plus one clearly marked Watsons Malaysia Retinol B3 listing. Exact URLs are in the
catalogue source registry and every match's field references. Public browser/indexed
extracts were checked on 2026-10-15; day precision is retained rather than inventing
a retrieval time-of-day. Some indexed extracts are older than that verification date.
No crawler, external requests during serving, live stock or current price assumptions.

Product schema:

```text
product_id, family_id, brand, product_name, market
category, subcategory, product_format, application_area[], finish
manufacturer_claims[{concept, text, claim_type, independently_verified:false}]
raw_ingredients, normalized_ingredients[], ingredient_completeness
variant, shade, size, occasions
source_id -> sources[{url, source_type, verified_on, timestamp_precision, access_method, scope}]
catalogue_version, verified_on, requires_review, quality_warnings[]
field_quality[field] = {state, reason, evidence:[{source_id, basis}]}
```

Field states are verified (source-backed transcription/taxonomy, **not scientific
validation**), partial, unknown, or conflict. Unknown values are null. Claims remain
source declarations in a separate field, including retailer-reported brand claims.
INCI is retained on 16 records: nine have a complete listed formula, seven partial
or shared-formula evidence. Other records retain explicit named ingredients only
where verified, or null; absence from partial lists never proves ingredient absence.
INCI bullet delimiters are transcribed as commas; source misspellings/concatenations
are not silently repaired. Package formula/current shade composition is not verified.
No ingredient concentration or benefits are inferred from ingredient presence.

Notable evidence handling:

- Pink hair oil's product identity/ingredient-block consistency needs review. Both
  sizes are quarantined, not returned as hair-oil fits.
- Hyalu B5's source claims alcohol-free while listing ALCOHOL DENAT. The conflicting
  alcohol claim is excluded and a warning retained; unrelated supported fields remain usable.
- Missing explicit application areas on HA/Oil Control/Mela source extracts remain null.
- Generic ingredient tiles, consumer reviews and unrelated page recommendations are ignored.
- Unspecified shades/sizes and lack of shade-specific INCI are explicit warnings.

`scripts/build_product_catalogue.py` materializes curated facts without networking.
Update facts only after source review and bump catalogue version. Stable IDs must not
be reassigned. Keep the previous catalogue/report when releasing a new version.

## Structure

```text
data/product_intents.json             Explicit intent and alias overrides
data/products/catalogue.json          Versioned catalogue and source registry
data/products/human_review.json       Fixed, unlabelled human review set
services/product_catalogue.py        Read-only loading and provenance checks
services/product_fit.py              Independent component matching and legacy adapter
services/product_evaluation.py       Human metrics and mechanical trace checks
scripts/build_product_catalogue.py   Curated facts, deterministic materialization
scripts/product_fit_report.py        Read-only examples/evaluation export
reports/phase4b/examples.json         Full responses for all eight topics, all pairs
reports/phase4b/evaluation.json       Counts, abstention, traceability, pending human metrics
tests/test_phase4b.py                 Synthetic rule oracles/API/daily-summary checks
tests/product-text.test.cjs           External text and source-URL safety
tests/product-fit-browser.cjs        Optional eight-topic/mobile/security browser checks
```

## Matching method

`product-fit-rules-1`, intent version `intent-1`. No ML, embedding, numerical combined
score, demand/lifecycle/popularity/ROI join or inferred ingredient requirement.
Each configured query is evaluated separately; query aliases are never aggregated.

Hard constraints are category, optional subcategory, format, market and application
area. Known incompatibility is no_fit; unknown required compatibility is
insufficient_evidence. Shared category alone cannot match.

| Intent | Rule |
| --- | --- |
| Niacinamide | Exact ingredient + face skincare serum; broad alias removes serum/subcategory constraint |
| Retinol | Exact retinol + face skincare; retinyl palmitate is not retinol |
| Skin barrier | Explicit barrier-repair claim = direct; configured hydration/soothing claims or exact panthenol/ceramide concepts = supporting only |
| Scalp care | Scalp application plus explicit scalp-care/cleansing declaration |
| Lip tint | Lip application and lip_tint format; stain alias requires lip_stain, not silently equated |
| Glass skin | Face application plus declared hydration/radiance or radiant/dewy finish = supporting only |
| Deepavali glam | Compatible face/lip makeup plus long-wear/intense-colour declaration = supporting only without explicit occasion evidence |
| Hair oil | Hair-length application plus hair_oil format; oil-named shampoo/conditioner is not equivalent |

Only exact curated ingredient aliases are normalized. No substring match of retinol
against retinyl palmitate, no category-to-efficacy inference. Conflicted fields cannot
support a match. Unknown INCI yields abstention for ingredient requirements. Verified
format can support a format-led match without INCI: missing INCI is not a universal veto.
Look/occasion concepts are provisional editorial configurations, not validated preferences.

Matched products sort direct_fit then supporting_fit, with stable product ID ties.
This is transparent deterministic ordering, **not a learned ranking**. Sizes and shades
count separately; several matches may be one family. Family deduplication is not implemented.

## Read-only API

```text
GET /api/product-fit/<topic_id>?query_id=canonical
GET /api/product-fit/niacinamide?query_id=broad
```

All eight pilot IDs are supported, including `hair-scalp-care`. Unknown topic/query
returns 404; invalid/unavailable catalogue returns 503. POST is not supported. Serving
does not initialize/migrate a trend database, ingest sources, create cohorts or write files.

Root response: status, topic_id, canonical_topic, query_id, query, market, intent,
data_mode=real (curated source-backed records), output_kind=rule_based_catalogue_fit,
state=provisional (human methodology review pending), method_version, intent_version,
catalogue_version, matched_products, assessments (including excluded/abstained pairs),
counts, warnings, ranking_method.

Each pair: product_id/name/brand, fit_state, method_version, dimensions (ingredient,
declared-benefit, format, application, subcategory, look, occasion), supporting_evidence,
missing_evidence, contradictions, warnings, provenance. Evidence contains literal field
value, product ID, field state, source ID/URL/type/verification date, basis and catalogue
version. Explanations do not assert clinical effects. This is not measured trend data.

The legacy product mapping/hashtag endpoints consume this service. No unknown-category
skincare default, no unmatched hashtag fallback, no opportunity score, fake price,
humidity suitability or availability. Missing frontend fields are present with nulls,
both cost keys agree, and unverified values display explicitly. Old unsupported hashtags
now honestly return 404; canonical topic names/queries and configured aliases resolve.
The existing page layout remains; text is escaped and source links allow HTTPS only.
A scoped contrast fix keeps legacy white text readable under the shared neutral theme.

## Current canonical outputs

Counts are product records, **not evaluation precision**. Full pair evidence is in examples.json.

| Topic | Direct | Supporting | Insufficient | No fit | Example |
| --- | ---: | ---: | ---: | ---: | --- |
| Niacinamide | 1 | 0 | 4 | 27 | Retinol B3 serum has explicitly listed niacinamide |
| Retinol | 1 | 0 | 6 | 25 | Retinol B3 serum; retailer source/malformed-INCI warning retained |
| Skin barrier | 2 | 3 | 4 | 23 | Hyalu B5, 30/50ml, declared barrier repair |
| Scalp care | 2 | 0 | 0 | 30 | Full Resist scalp essence / scalp-cleansing shampoo |
| Lip tint | 1 | 0 | 0 | 31 | Teddy Tint; shade/size unspecified |
| Glass skin | 0 | 8 | 4 | 20 | Fresh Tint has declared radiance; no literal glass-skin efficacy claim |
| Deepavali glam | 0 | 8 | 0 | 24 | Vinyl Ink long-wear/colour attributes; no cultural/occasion validation |
| Hair oil | 4 | 0 | 2 | 26 | Gold 30/100ml, Brown and Rose 100ml; Pink withheld |

## Human evaluation

The fixed JSON review set contains all 256 canonical topic/product pairs. It covers
machine-stratified direct/supporting/same-category-negative/incomplete cases; the
sampling stratum is **not a human label**. Human labels, reviewer/date, explanation
support judgment and notes start null. No automated labels or invented precision.
Families are deterministically split dev/evaluation (SHA-256 family ID modulo 3);
size/shade siblings never cross splits. No parameters have been trained on these labels.

Manually fill `human_label` (one of the four fit states), reviewer, reviewed_on,
unsupported_explanation (true/false), and notes after inspecting the source/intent.
Do not change row IDs, splits or versions. Keep a copy of your reviewed artifact.
Run the report with `--review PATH` to validate and compute results; it never auto-labels.

Per topic/split, ranking metrics become available only after every candidate has a
human label. Fixed eval candidate pools are separate from dev and the full production
catalogue. Aliases are outside this initial human evaluation and require separate review.

- Precision@5 = human-relevant returned top-five / 5. Direct/supporting are relevant;
  fewer than five returned products leaves empty positions, not a smaller denominator.
- nDCG@5 uses grades direct=2, supporting=1, no_fit/insufficient=0; gain=2^grade-1,
  log2(rank+1) discount, divided by ideal DCG in that fixed candidate pool.
- Catalogue-bounded recall = relevant returned candidates / all human-relevant candidates
  in that labelled split. Not market-wide recall; null when no relevant gold exists.
- Unsupported-match rate needs separate human explanation-support judgments for every
  returned match in the split. Reference existence alone does not establish factual support.
- Mechanical abstention = insufficient_evidence pairs / all 32 products for that topic.
- Mechanical explanation traceability = valid field/source/version references / all
  references emitted for matched products. This checks schema integrity, not relevance.

**Current human results: unavailable/pending, zero human labels.** Mechanical reference
traceability is 100% for all eight queries. Abstention: Niacinamide 12.5%, Retinol 18.75%,
Skin barrier 12.5%, Scalp care 0%, Lip tint 0%, Glass skin 12.5%, Deepavali 0%, Hair oil 6.25%.
Synthetic rule/ranking unit oracles are expressly not real-world human evaluation results.

## Commands

From the repository directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\product_fit_report.py
# After human review, validate/evaluate without overwriting labels:
.\.venv\Scripts\python.exe scripts\product_fit_report.py --review path\to\reviewed.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests\product-text.test.cjs tests\intelligence-ui.test.cjs
```

Verified: 95 Python tests (21 new), 10 JavaScript tests (three new), and 11 optional
browser workflow/security checks pass. The browser checks cover all eight queries,
desktop/mobile rendering, explicit unknown-query errors and injected external text/URLs.
Desktop/mobile screenshots are saved in reports/phase4b.

The committed catalogue and review file are sufficient; no regeneration, API key or
additional dependency is required for Product Fit. `--initialize-review` is only for
a new review file and refuses to overwrite existing human edits.

Daily collection remains explicit and unscheduled. Set YOUTUBE_API_KEY in your shell,
then use the existing canonical-cohort process:

```powershell
.\.venv\Scripts\python.exe scripts\youtube_phase25.py daily --output reports\phase2-measured
```

It now prints concise completed-search/completed-stats-request/video/failure/date counts
to stderr, and adds post_run_summary to the normal JSON output. Actual retrieval date(s)
are separate from the completed UTC publication day. Hidden likes mark partial video
records, not failed requests. Absent videos are not counted as successfully snapshotted.
Capped discovery and unavailable records are separate summary fields. A same-day skip
does not claim new collection. No live collection or automatic scheduling was run for Phase 4B.

## Remaining provisional work

Complete human Product Fit evaluation, verify missing application/variant/INCI fields,
review quarantined source inconsistencies, broaden brands, and assess family-aware
retrieval ordering. No recommendation validity, independent claim verification, current
stock, prices, consumer suitability, sales impact or cultural fit is established.
