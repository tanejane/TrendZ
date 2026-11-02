# Experimental Gemini explainer (local-only)

This adds a narrow **read-only explanation endpoint** (`POST /api/assistant/explain`) for **one canonical measured topic**. The existing nine-tool deterministic assistant remains separate and unmodified. This is not autonomous tool use, validated reasoning, public deployment, or a measured model-quality benchmark.

## Setup

1. Install with `python -m pip install -r requirements.txt` in the project virtual environment.
2. Copy `.env.example` to `.env`; put the real `GEMINI_API_KEY` there, and set `GEMINI_MODEL=gemini-3.5-flash-lite`.
3. Set `TRENDZ_ASSISTANT_ENABLED=true` **only locally**.
4. Use a separately approved *measured* SQLite database and `TRENDZ_DATA_MODE=real`. The GitHub source ZIP does not include the research database.
5. Launch the locally bound Flask app, e.g. `python scripts/run_demo.py --port 5000` if the required research artifacts are available. The measured dashboard contains “Ask TrendZ about stored evidence.”

The API accepts `{ "topic_id": "<configured topic>", "question": "What does the evidence show?" }` and returns a generated explanation, a link to the underlying intelligence endpoint, and an explicit disclaimer. It intentionally does not allow freeform retrieval, cross-topic winner declarations, or campaign predictions. No arbitrary tool calls are permitted.

## Important boundaries

- The route refuses non-loopback clients and is disabled by default; for real public deployment, implement proper user authentication, CSRF protections, quotas, caching, usage monitoring, and provider budgets first. **Do not put the key in frontend files or GitHub.**
- The Gemini provider can hallucinate. Answers are **not** independently verified against the evidence; always inspect the underlying source components.
- The service sends a compact excerpt of measured evidence and your question to Google Gemini; avoid submitting sensitive or unpublished data without permission.
- The explainer fails closed if measured data is missing or the evidence excerpt is too large.
- The existing demo/legacy chatbot remains retired (HTTP 410). Public source releases do not include the measured research database.
- Run `python -m unittest tests.test_gemini_explainer -v` for mocked tests (no real API call).
