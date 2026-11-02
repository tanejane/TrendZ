# Engineering Story

## One-Minute Version

TrendZ started as a hackathon beauty-trend dashboard inspired by the L'Oreal
Datathon 2025 collaboration with Monash. The original limitation was that static
examples looked more analytical than their evidence justified. I rebuilt the data
path around source provenance and made unknowns part of the product experience.

The important decision was not to combine everything into a score. Search demand,
content supply, creator expertise and campaign assumptions describe different
things. I kept them separate, used explicit evidence gates and froze methods before
evaluating them. The end-to-end demo links measured trend evidence to product
compatibility, reviewed creator candidates and deterministic campaign economics.
The grounded assistant boundary is implemented, but live LLM execution is explicitly
deferred rather than imitated with a mock answer.

## Decisions And Trade-Offs

1. **Real-data redesign:** extracted hardcoded seeds into an explicit legacy mode,
   introduced replaceable Google/YouTube/CSV adapters and SQLite. This added
   reproducibility without introducing a large orchestration framework.
2. **YouTube ceiling:** bounded weekly discovery could hit the 50-result page cap.
   More uploads discovered at a cap are not valid evidence of publication growth.
   Instead of extrapolating, I exposed cap/missingness flags, retained immutable
   runs and added manually relevant fixed cohorts for forward snapshots.
3. **Signal semantics:** current counters are retrieval-time descriptions, not
   historical views. Google interest is normalized search demand; YouTube is sampled
   content activity. I preserved per-query/request scope instead of comparing
   unrelated 0-100 series or combining popularity into a trend score.
4. **Product Fit:** deterministic evidence matching over 32 source-backed products
   enabled inspectable ingredient/benefit/format/application-area decisions.
   The 256 fixed pairs used assisted review, not independent gold. Evidence cleanup
   improved the fixed-set results while rules stayed unchanged; that is not proof
   of independent generalization. Product Fit v1 was frozen rather than repeatedly
   tuned against the same labels.
5. **Creator evidence:** 40 seed videos represented 40 different channels, so one
   match per channel could not establish specialization. Bounded expansion sampled
   747 public videos. Profile and topic affinity were reviewed separately across
   104 fixed units, with one-video safeguards and explicit abstention. H1 is an
   evidence-gated candidate policy for a product context, not a global creator ranking.
6. **Commercial calculations:** fees, reach, conversion rate, AOV and margin are
   explicit assumptions. Decimal calculations, low/base/high sensitivity and
   break-even remain deterministic. Stale context and manual-only acknowledgement
   prevent polished explanations from bypassing weak evidence.
7. **Grounded AI architecture:** nine closed tools wrap existing authorities. A
   per-turn immutable result registry and exact citation validator separate
   observed/reviewed evidence, unknowns, assumptions and calculated scenarios.
   A model cannot authorize consent or invent formulas. No provider is connected;
   the portfolio demonstrates the architecture without claiming model quality.

## Honest Closing

The strongest part is the separation of evidence and assumptions, including failures
and abstention. The weakest part is independent validation: the catalogue and
creator cohorts are small, reviews are substantially assisted and source sampling
is bounded. A larger independent holdout and better catalogue evidence are more
valuable next steps than a more impressive-looking score. The app is ready for a
local interview demo with its saved evidence, not public production deployment.
