[README.md](https://github.com/user-attachments/files/34304149/README.md)
# TrendZ · Beauty Trend Intelligence

**From scattered public signals to explainable product and creator decisions.**

TrendZ is a research prototype that helps beauty teams inspect emerging interests, explore product compatibility, review creator evidence and model *hypothetical* campaign economics — without treating online popularity as proven market demand or predicted sales.

Built independently as an evolution of a beauty-industry datathon concept inspired by the **L’Oréal Datathon 2025 × Monash** collaboration. **Not affiliated with or endorsed by L’Oréal or Monash.**

![TrendZ dashboard showing observed topics and evidence coverage](showcase/product-ui/01-dashboard.png)

**[Explore the interface](showcase/product-ui/README.md)** · **[Architecture](showcase/ARCHITECTURE.md)** · **[Research methods](docs/METHODOLOGY.md)** · **[Demo and setup](docs/GETTING_STARTED.md)** · **[Contribute](CONTRIBUTING.md)**

## Why this exists

A viral video, an increase in search interest and a creator’s expertise are **not interchangeable**. Yet they are easy to collapse into a single “trend score.” TrendZ instead keeps the evidence, provenance, uncertainty and business assumptions separate so a decision-maker can see **what is known, what is missing and what is assumed**.

## Follow the decision journey

| Step | What you can inspect | Important boundary |
| --- | --- | --- |
| **01 · Discover** | Observed beauty topics and source coverage | Stored snapshots; not a real-time market feed |
| **02 · Understand** | Six evidence-aware trend intelligence dimensions | No single predictive trend score |
| **03 · Match** | Product Fit with ingredient, benefit, format and use-case rules | Compatibility is not efficacy |
| **04 · Shortlist** | Creator candidates with review provenance and abstention states | Not endorsement, audience verification or global ranking |
| **05 · Plan** | Version-pinned campaign context, ROI, sensitivity and break-even | User-entered assumptions, not actual or forecast returns |

<details><summary><strong>See product journey screenshots</strong></summary>

![Evidence-aware trend details](showcase/product-ui/03-trend-detail.png)

![Product compatibility interface](showcase/product-ui/04-product-fit.png)

![Creator candidate evidence](showcase/product-ui/05-creator-candidates.png)

![Campaign assumption builder](showcase/product-ui/10-planner-assumptions.png)

</details>

## What is implemented

- **Evidence-aware trend intelligence:** demand momentum, signal persistence, content saturation, creator diversity, engagement velocity and evidence quality, each with independently reported availability and limitations.
- **Inspectable product matching:** deterministic `product-fit-rules-1` over a curated Malaysian beauty catalogue, with explicit insufficient-evidence outcomes.
- **Product-specific creator candidates:** fixed cohort, profile/affinity review trails, one-video safeguards and eligibility gates.
- **Scenario economics:** Decimal-based ROI, break-even and low/base/high sensitivity from explicit planning inputs, with version/staleness checks.
- **Grounded-assistant infrastructure:** nine internal tool contracts, scoped context, canonical citations and validation. **An opt-in, localhost-only Gemini explanation endpoint is available for approved measured evidence.** The nine-tool deterministic assistant is not model-driven; no public chatbot is deployed.

### Technical design

```text
Public search/content sources + normalized CSV
                  │
         ingestion + provenance
                  │
        SQLite observations / snapshots
                  │
      six independent intelligence signals
                  │
        curated Product Fit rules
                  │
    reviewed creator candidates + gates
                  │
    pinned scenario assumptions + economics
                  │
      inspectable planning outputs

     [separate internal grounded AI boundary]
            provider connection is separately opt-in
```

**Stack:** Python · Flask 3 · SQLite · Jinja · JavaScript (vanilla) · CSS · unittest · Node test runner. Optional Google Trends adapter and YouTube API ingestion. No trained machine-learning model, SPA framework or autonomous agent is claimed. Optional Gemini provider uses server-side credentials; see [Gemini integration](docs/GEMINI_ASSISTANT.md).

![TrendZ system architecture showing evidence and calculation boundaries](showcase/demo/architecture.png)

## Evidence and evaluation

The retained *local research archive* includes eight pilot topics (from 18 configured), 32 catalogue products, 256 fixed Product Fit pairs, 40 creator profiles, 747 sampled public creator-video IDs and 104 creator review units. These are **sample counts, not market-size estimates**. Most review labels were assisted; they are not independent human ground truth.

| Saved result | Scope |
| --- | --- |
| Product Fit macro P@5 **0.625**, nDCG@5 **0.9441** | Eight fixed topics, after evidence cleanup; not independent validation |
| Creator profile agreement **13/24** | Comparable review proposals only |
| One-video safeguard **0 violations** | Seven reviewed moderate/strong affinity decisions |
| **339** discovered Python test cases | Historical archive count; not a fresh CI result on this public package |

See [methodology and limitations](docs/METHODOLOGY.md) for denominators, caveats and provenance. No overall prediction accuracy or measured campaign return is claimed.

## Run it or explore the code

**This is a source-and-portfolio publication, not a turnkey copy of the measured demo.** For rights/privacy reasons, the frozen measurement database and raw review exports are **not included**. Thus the full measured journey shown in screenshots will not run from an ordinary GitHub clone; it fails explicitly when its evidence is absent. This is intentional, not a silent sample-data substitution.

For installation and the exact list of missing assets, see **[Getting Started](docs/GETTING_STARTED.md)**. You can still browse the Flask routes, services, UI, fixtures, unit tests and architecture. The archived *legacy simulated mode* is explicitly marked as such and must never be presented as a measured demo.

```bash
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -r requirements.txt
# macOS/Linux:
.venv/bin/python -m pip install -r requirements.txt
```

With separately obtained/approved frozen evidence assets, run `python scripts/run_demo.py --port 5000` inside the environment. It launches a local snapshot on `127.0.0.1`, not a public production service.

## Repository map

| Path | Purpose |
| --- | --- |
| `app_backend.py` | Flask web app and API routes |
| `services/ingestion/` | Source adapters and ingestion |
| `services/intelligence_*` | Six dimensions and evidence semantics |
| `services/product_*` | Catalogue, matching, reviews and evaluation |
| `services/creator_*` | Creator evidence, policy, review and selection |
| `services/campaign_*` | Context versioning, validation and economics |
| `services/assistant_*` | Internal grounded-tool infrastructure (no model provider) |
| `templates/`, `static/` | Jinja interface and browser behavior |
| `tests/`, `scripts/` | Unit tests, historical workflows and audit tools |
| `showcase/`, `docs/` | Screenshots, architecture, explanation and contribution guides |

## Known limitations and next steps

Snapshot evidence is dated and bounded; Google Trends is normalized per request; YouTube searches are sampled; some dimensions must abstain. Product and creator sets are limited, and assisted reviews are **not independent benchmarks**. There is no audience verification, causal validation, live AI, continuous monitoring, authentication or production-ready deployment.

The most useful collaboration areas are **source reproducibility/packaging**, **independent evaluation**, **evidence quality**, **accessibility**, and **privacy-conscious deployment**, rather than adding an unvalidated “AI score.” See [contribution ideas](CONTRIBUTING.md).

### Credits and usage

Independent educational/research work inspired by a datathon theme. Third-party source data and service marks belong to their respective owners. Screenshots depict retained research evidence; illustrative category images are not product endorsements. **No open-source license has been granted in this package**; licensing should be decided explicitly before inviting code reuse or redistribution.
