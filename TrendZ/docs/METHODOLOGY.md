# Methods, evidence and evaluation boundaries

TrendZ intentionally avoids a combined popularity/viral-trend score. For definitions, denominators, gating logic and frozen method versions consult the retained original research documentation:

- [Trend dimension formulas and abstentions](../PHASE3A.md)
- [Product Fit evidence cleanup, holdout limits and reproducibility](../PHASE4D_LITE.md)
- [Creator policies and review boundaries](../PHASE5E.md)
- [Campaign assumptions and economics](../PHASE6B.md)
- [Nine-tool grounding interface](../PHASE7B.md)
- [Live provider deferral](../PHASE7C_DEFERRED.md)
- [Architecture](../portfolio/ARCHITECTURE.md)

## Reproducibility status

The original project archive contains a frozen measured SQLite pilot, curated product/review exports, source hashes, research scripts and a saved Phase 8A audit. Those reports and evidence files are deliberately omitted from this public source-only release. The publication includes `portfolio/demo/verified_facts.json` with historical evidence counts and SHA-256 provenance, but it cannot independently reproduce those facts without the original research artifacts. Treat these as **historically recorded bounded results**, not as CI or independently verified benchmark claims for the GitHub zip.

## Key cautions

- Google Trends returns relative search-interest indices; independently normalized requests cannot be ranked as absolute search demand.
- YouTube discovery is bounded and may be capped. Retrieval-time view counts are not publication-time engagement; geography filtering is not audience verification.
- A product attribute claim is not efficacy evidence. The compatibility rules are deterministic.
- Fixed product/creator review labels were substantially assisted and are not a fresh independent gold-standard holdout.
- The campaign scenario is deterministic arithmetic based on user inputs. Sensitivity rates are user assumptions, not statistical confidence intervals.
- Assistant grounding validates canonical claims and citation fields; it does not establish source truth, arbitrary-language entailment or live model quality. No LLM provider is configured.

This separation is a deliberate design choice: unavailable or weak evidence remains visible instead of becoming an invented number.
