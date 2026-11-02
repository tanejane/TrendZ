# Phase 3B: trend detail intelligence UI

The existing `/trend-detail/<topic_id>` page now includes a shared measured-intelligence
section in both measured and demo layouts. Existing sections and actions remain intact.
No analytical formulas, endpoints, schema, commercial/ROI logic or audit labels change.
No new scores, lifecycle labels, AI interpretation or recommendations are added.

## Display

The section requests `/api/intelligence/<topic_id>?query_id=canonical`. A labelled select
permits explicit alias selection; sources/query variants are never pooled by the UI.
The six dimensions are displayed independently. Backend `data_confidence` is labelled
**Evidence Quality**, without renaming the API field.

Available uses a solid dark neutral badge. Provisional uses a dashed neutral badge,
with provisional reasons visible. Unavailable uses a muted badge, explicit unavailable
values and blocking reasons. Missing values are not displayed as zero. Sources,
observation dates, market and quality warnings remain visible. Supporting components
may still appear when their parent dimension is unavailable, matching the API's scope.
Repeated identical component reasons are shown once within each dimension.

Each dimension has expandable method/provenance details. The compact methodology note
reads: "Available means supported at the current evidence scope, not validated market truth."
API values are inserted with textContent, not HTML. No analytical values are calculated
in JavaScript; numeric formatting preserves zero, negative and missing values.

Loading is announced through a live status region. Network or malformed-response
failures show a separate retry action, not fabricated unavailable measurements. Query
changes abort superseded requests and prevent stale responses from replacing the
selected alias. Desktop uses two columns; mobile uses one. Styling is confined to the
new section and uses the existing neutral theme variables.

## Files

- `templates/intelligence_dimensions.html`: shared section and loading/error states.
- `templates/trend-detail.html`, `templates/measured_detail.html`: inclusion points.
- `static/js/intelligence.js`: fetch, query selection and safe component rendering.
- `static/css/intelligence.css`: scoped responsive neutral presentation.
- `tests/intelligence-ui.test.cjs`: seven dependency-free Node unit tests.
- `tests/test_phase3b.py`: three Flask template-preservation tests.
- `tests/intelligence-browser.cjs`: optional Playwright checks against a running app.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/intelligence-ui.test.cjs
```

Optional browser verification requires a development installation of Playwright and
Chrome, not a new runtime application dependency. Point it at an already-running real
mode preview with the measured pilot database:

```powershell
$env:TEST_BASE_URL = "http://127.0.0.1:5013"
node tests/intelligence-browser.cjs
```

`PLAYWRIGHT_MODULE` may specify an existing absolute Playwright module path, and
`SCREENSHOT_DIR` may select another screenshot directory. Checks cover all eight topics,
states/warnings, Evidence Quality wording, provenance disclosure, query switching,
mobile overflow, retry, safe text rendering and preserved ROI navigation. The screenshots
in `reports/phase3b` were produced from a real-mode preview using an isolated copy of the
measured database. No live ingestion or manual relevance import was performed.
