# Phase 4D-lite: Evidence-only Product Fit v1 Rerun

The frozen method is `product-fit-rules-1`. No semantic rules, format allowlists,
thresholds, ordering, intent definitions or evaluation formulas change in this phase.

The original `data/products/catalogue.json`, completed review session and Phase 4C
reports remain untouched. The source-reviewed field manifest is
`data/products/evidence_hardening_v1.json`. It creates a **separate versioned catalogue**
under `reports/phase4d-lite/catalogue_hardened_v1.json`, explicitly injected through
the existing `ProductFit(Catalogue(path))` interface. This is an isolated rerun, not a
silent change to the website's default evidence or an automatic production rollout.

```powershell
.\.venv\Scripts\python.exe scripts\product_evidence_rerun.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_phase4d.py
```

Source decisions are fixed before metrics are read: MY application directions or
explicit product headings only; linked-size corroboration is marked partial;
regional guidance is not promoted to a verified Malaysian field. No ingredients,
benefits or labels are backfilled to improve agreement. B5 formula conflicts are
represented as conflicted ingredient fields with original observations preserved,
not a fabricated replacement INCI. Pink Oil quarantine is retained unchanged.

The same 256 review decisions, pair identities, product families and dev/evaluation
assignments are reused explicitly across evidence versions. These labels remain
mixed human/assisted judgments, not a new independent holdout. New or changed
explanations do not inherit old explanation-support decisions; support metrics are
unavailable where re-audit is pending. Frozen Phase 4C support judgments are not edited.

Reports include before/after metrics, split and topic results, all prediction-state
transitions, source provenance, evidence-only field changes and a SHA-256 freeze
manifest. Changed historical artifacts are not overwritten on a repeat run.

## Freeze Policy

Freeze v1 semantics and the hardened evidence snapshot after this rerun. Do not
tune on the reviewed evaluation labels. A future semantic change requires a new,
independently adjudicated holdout demonstrating a genuine rule problem. Formula or
application uncertainty must remain explicit until authoritative evidence resolves it.
