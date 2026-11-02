# Phase 5C Review-Assistance Preparation

This is a separate draft pack, not new predictions, final review labels or gold.
It does not update the local review database, fixed units, original groups,
Phase 5B evidence, Product Fit, any ranking or evaluation logic.

## Generate

From the repository root, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -B scripts\prepare_creator_assists.py
```

Default output: `reports/phase5c/assists/preparation-v1/`.
Use `--output reports/phase5c/assists/preparation-v2` for another export.
Existing output directories are refused rather than replaced.

- `REVIEW_DRAFTS.md`: all 104 drafts, selected YouTube links and deeper manual queue.
- `profile_suggestions.json`: 40 profile drafts.
- `affinity_suggestions.json`: 64 affinity drafts.
- `review_assists.json`: combined machine-readable draft pack.
- `decisions.json`: independently authored decisions pinned to exact unit IDs.
- `verification.json`: confidence counts, unchanged protected-file hashes, review counts.

The generator opens SQLite with `mode=ro`. It does not call review save/evaluate
or collect source data. Existing labels, history and revisions are read only.
Each suggestion records the session, source SHA, fixed-unit SHA, current review
revision and review SHA. Recheck these before any future acceptance/import;
stale suggestions must not overwrite newer human work.

## Basis and Confidence

Suggestions were authored by inspecting frozen titles, descriptions, publication
dates, screened hits and inherited human-reviewed seed provenance. This is not
video/audio playback verification, professional-credential verification, external
research, or validation of efficacy claims. Exact raw source references and full
available selected descriptions are retained in JSON. Original missing fields
remain missing, including titles/descriptions of two outside-sample seeds.

No new matching engine, numeric strength threshold or evaluation rule is introduced.
An explicit topic mention, a generic proxy, a hashtag, an ingredient list and a
substantive dedicated discussion are not interchangeable. Individually authored
reasons qualify those distinctions. Retinal/tretinoin are not retinol synonyms;
generic hydration is not explicit glass-skin or barrier coverage; festive outfits
are not Diwali makeup. Possible permanent lip coloring and duplicate/reposted
captions stay in the deeper manual queue.

- High: clear scoped draft from stored evidence, including clear one-video
  weakness/abstention. Not necessarily strong affinity or a stable profile.
- Medium: plausible but qualified; compressed windows, incidental ingredient
  mentions, catalogue captions or clinical-versus-cosmetic scope need inspection.
- Low: unresolved meaning, format, language/repost ambiguity or proxy-only support.

All rows have `review_basis=assisted_review`, `needs_human_acceptance` and
`human_approval_required=true`. Medium/low rows additionally have
`deeper_manual_review_required=true`. Every row still needs explicit acceptance;
there is no automatic batch acceptance or finalized label in this pack.

## Guardrails

Stable profile drafts select at least two supporting videos on distinct UTC
publication dates. Strong/moderate affinity drafts similarly select at least two
candidate-relevant videos on distinct dates, but are **conditional proposals**:
the human must explicitly approve those videos' relevance before accepting that
affinity. Draft selections do not create approved video records. Newly approved
count remains zero and `sustained_affinity_validated=false` for every draft.

One video can support weak affinity or a qualified profile, never sustained
affinity/stable profile. Lilac Glaze can have a clearly weak glass-skin draft
while its single-video profile remains insufficient. A skincare/haircare/makeup
profile never automatically decides any topic pair.

Selected IDs and proxy/context IDs are disjoint. Current-sample share is only
the proposed selected-current count / fixed sampled count, not validated topical
share. Outside-sample seeds retain provenance but never enter that fraction.
Counts/span/recency refer only to selected IDs and are descriptive, not scores.
Separate distinct uploads/dates are necessary but not sufficient to prove genuinely
distinct content; suspected reposts/near-duplicates are explicitly qualified.

Explanation-support drafts refer to the **original frozen proposal**, not the new
suggestion or final label. They assess stored factual screening claims and whether
their classification/relevance interpretation is substantively supported. Supported
screening does not validate substantive creator expertise, source efficacy claims,
or sustained affinity. Missing seed descriptions remain insufficient for that
part of explanation verification. These judgments remain drafts too.

## Review

Read the summary and deeper-manual queue in `REVIEW_DRAFTS.md`. Inspect the linked
videos and full JSON descriptions as needed. Use the existing local review
workspace at `http://127.0.0.1:5016/` to explicitly accept/edit a judgment, choose
supporting videos, retain `assisted_review` basis, and save as the human reviewer.
The draft pack is not automatically loaded into final form fields or submitted.
No evaluation conclusions should be generated from these drafts.

## Tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_creator_review_assists -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```

Tests use synthetic temporary sessions and the pinned local snapshot when present.
They cover complete fixed-unit membership, revisions/provenance, read-only DB
bytes/history, existing-label preservation, separate profile/affinity scope,
single-video/date guards, duplicate/unknown evidence, proxies, outside-sample
denominators, conditional sustained drafts and zero new approvals.
