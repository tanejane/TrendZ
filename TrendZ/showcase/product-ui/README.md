# TrendZ Product UI

Frontend-only redesign over the measured backend. No analytical method, review,
policy, data, source evidence or calculation was changed. Live AI remains disabled.

| Screen | Capture |
| --- | --- |
| Dashboard | [Eight observed trend cards](01-dashboard.png) |
| Explore Trends | [Search and category filters](02-explore-trends.png) |
| Trend Detail | [Evidence dimensions and product journey](03-trend-detail.png) |
| Product Fit | [Frozen compatible-product context](04-product-fit.png) |
| Creator Candidates | [Reviewed product-specific candidates](05-creator-candidates.png) |
| Watchlist populated | [Saved trend cards](06-watchlist-populated.png) |
| Watchlist empty | [Empty state with Explore CTA](07-watchlist-empty.png) |
| Campaign Planner | [Five-step entry and trend selection](08-campaign-planner.png) |
| Planner creator step | [Contextual candidate selection](09-planner-creators.png) |
| Planner assumptions | [Explicit inputs, no inferred defaults](10-planner-assumptions.png) |
| Scenario review | [Unchanged deterministic results](11-scenario-review.png) |
| Dashboard mobile | [390px responsive layout](12-dashboard-mobile.png) |
| Planner mobile | [390px guided planning](13-planner-mobile.png) |

The campaign example uses the same synthetic planning inputs as the earlier demo:
MYR 1,000 cost, 1,000 assumed people, MYR 50 AOV, 40% margin, and assumed conversion
rates 2/5/8%. Its -60/0/60% ROI sensitivity is conditional arithmetic, not measured
or predicted campaign performance. No assumptions are pre-filled in the application.

The empty Watchlist capture uses an empty watchlist response fixture only; topic
evidence and metrics are not mocked. Other product views use the retained measured
snapshot and frozen catalogue/reviews. Category imagery is illustrative, not a
photo of any named catalogue product. [Asset provenance](ASSET_PROVENANCE.md).

Current preview: `http://127.0.0.1:5022/`. Explore is `/?view=explore`, a frontend
view of the same data, not a new backend route. Historical Phase 8A table screenshots
remain archived in `../demo/`.
