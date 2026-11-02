from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from services.gemini_provider import compact_evidence, explain, GeminiUnavailable
from services.trend_service import TrendService
from services.intelligence_service import IntelligenceService
from services.product_fit import ProductFit
from services.creator_candidates import CreatorCandidates, CandidateRequestError
from services.campaign_context import CampaignContext
from services.campaign_schema import ScenarioError, OBJECTIVES, FORMATS
from services.campaign_scenarios import evaluate as evaluate_campaign


load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
app.config["DATA_MODE"] = os.environ.get("TRENDZ_DATA_MODE", "demo")
app.config["DATABASE_PATH"] = os.environ.get("TRENDZ_DB_PATH", str(DATA_DIR / "trendz.sqlite3"))


def trend_service():
    key = (app.config["DATABASE_PATH"], app.config["DATA_MODE"])
    cached = app.extensions.get("trend_service")
    if not cached or cached[0] != key:
        app.extensions["trend_service"] = (key, TrendService(BASE_DIR, *key))
    return app.extensions["trend_service"][1]


@app.context_processor
def mode_context():
    return {"data_mode": app.config["DATA_MODE"]}


@app.before_request
def measured_boundaries():
    if app.config["DATA_MODE"] == "real" and request.path in {
        "/api/ai-trend-forecasting", "/api/advanced-forecasting", "/api/early-detection",
        "/api/trend-radar", "/api/ingredient-popularity", "/api/visual-trend-recognition",
        "/api/multimodal-detection", "/api/focus-groups", "/api/malaysia/community-analysis",
    }:
        return api_success(data_mode="unavailable", reason="Not measured or implemented in Phase 1",
                           forecasts=[], predictions={}, items=[])


@app.after_request
def response_metadata(response):
    if request.path.startswith("/api/") and response.is_json:
        payload = response.get_json()
        # Legacy scenario APIs keep their array shapes. Each item is explicitly demo.
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    item.setdefault("data_mode", "demo")
                    item.setdefault("output_kind", "assumption_based")
        elif isinstance(payload, dict):
            payload.setdefault("data_mode", "demo")
            if request.path in {"/api/business-value", "/api/roi-prediction"}:
                payload["output_kind"] = "assumption_based"
        response.set_data(app.json.dumps(payload))
        response.headers["X-TrendZ-Data-Mode"] = payload.get("data_mode", "demo") if isinstance(payload, dict) else "demo"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.errorhandler(sqlite3.Error)
def database_error(error):
    app.logger.error("Database operation failed: %s", error)
    return api_error("Database operation failed", 500, data_mode="unavailable")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def api_success(**payload: Any):
    return jsonify({"status": "success", **payload})


def api_error(message: str, status_code: int = 400, **payload: Any):
    payload.setdefault("data_mode", "unavailable")
    return jsonify({"status": "error", "message": message, **payload}), status_code


TRENDS = json.loads((DATA_DIR / "demo_trends.json").read_text(encoding="utf-8"))


INFLUENCERS = [
    {
        "id": 1,
        "name": "Aina Sofia",
        "platform": "Instagram",
        "username": "ainasofia.beauty",
        "followers": 185000,
        "engagement_rate": 5.8,
        "category": "skincare",
        "specialization": "Sensitive-skin routines and sunscreen education",
        "location": "Kuala Lumpur",
        "language": "Malay, English",
        "contact_email": "aina@example.com",
        "instagram_url": "https://instagram.com/",
        "tiktok_url": "https://tiktok.com/",
        "youtube_url": "https://youtube.com/",
        "price_range": "RM 5K-10K",
        "availability": "Available",
        "rating": 4.8,
        "bio": "Beauty creator focused on practical routines for Malaysian humidity.",
        "profile_image": "https://ui-avatars.com/api/?name=Aina+Sofia&background=EC4899&color=fff",
    },
    {
        "id": 2,
        "name": "Priya Raman",
        "platform": "TikTok",
        "username": "priyaglam.my",
        "followers": 240000,
        "engagement_rate": 6.6,
        "category": "makeup",
        "specialization": "Festive makeup, inclusive shades, and quick tutorials",
        "location": "Selangor",
        "language": "English, Tamil, Malay",
        "contact_email": "priya@example.com",
        "instagram_url": "https://instagram.com/",
        "tiktok_url": "https://tiktok.com/",
        "youtube_url": "https://youtube.com/",
        "price_range": "RM 10K-20K",
        "availability": "Available",
        "rating": 4.9,
        "bio": "Makeup creator with strong festival and shade-match content.",
        "profile_image": "https://ui-avatars.com/api/?name=Priya+Raman&background=8B5CF6&color=fff",
    },
    {
        "id": 3,
        "name": "Mei Lin Tan",
        "platform": "YouTube",
        "username": "meilinbeautylab",
        "followers": 98000,
        "engagement_rate": 4.9,
        "category": "haircare",
        "specialization": "Haircare explainers and long-form product reviews",
        "location": "Penang",
        "language": "English, Mandarin",
        "contact_email": "meilin@example.com",
        "instagram_url": "https://instagram.com/",
        "tiktok_url": "https://tiktok.com/",
        "youtube_url": "https://youtube.com/",
        "price_range": "RM 3K-5K",
        "availability": "Busy",
        "rating": 4.7,
        "bio": "Detailed reviewer known for ingredient and routine breakdowns.",
        "profile_image": "https://ui-avatars.com/api/?name=Mei+Lin&background=10B981&color=fff",
    },
]


def get_trends() -> list[dict[str, Any]]:
    return trend_service().trends()


def find_trend(trend_id: str) -> dict[str, Any] | None:
    return next((trend for trend in get_trends() if trend["id"] == trend_id), None)


def get_watchlist() -> list[dict[str, Any]]:
    return trend_service().watchlist()


def product_mapping_for_trend(trend: dict[str, Any]) -> dict[str, Any]:
    service = ProductFit()
    try:
        topic_id, query_id = service.resolve(trend['id'])
        return service.legacy(topic_id, query_id)
    except KeyError:
        return {"trend_id":trend['id'], "trend_name":trend['name'],
                "recommended_products":[], "opportunity_score":None,
                "data_mode":"unavailable", "reason":"No configured Product Fit intent"}


def hashtag_recommendations(hashtag: str) -> dict[str, Any]:
    service = ProductFit()
    topic_id, query_id = service.resolve(hashtag)
    return service.legacy(topic_id, query_id, hashtag)


@app.get('/api/product-fit/<topic_id>')
def api_product_fit(topic_id):
    try:
        return api_success(**ProductFit().topic(topic_id, request.args.get('query_id','canonical')))
    except KeyError as error:
        return api_error(str(error.args[0]), 404)
    except (OSError, ValueError) as error:
        app.logger.error('Product catalogue unavailable: %s', error)
        return api_error('Product catalogue unavailable or invalid', 503)


def creator_candidate_service():
    if 'creator_candidates' not in app.extensions:
        app.extensions['creator_candidates'] = CreatorCandidates(BASE_DIR)
    return app.extensions['creator_candidates']


@app.get('/api/creator-candidates/context/<topic_id>')
def api_creator_candidate_context(topic_id):
    """Bootstrap frozen Product Fit choices and pins; no candidate evaluation."""
    try:
        return api_success(**creator_candidate_service().context(topic_id))
    except CandidateRequestError as error:
        return api_error(str(error), error.status)
    except (OSError, ValueError, KeyError) as error:
        app.logger.error('Creator candidate evidence unavailable: %s', error)
        return api_error('Frozen creator candidate evidence unavailable or invalid', 503)


@app.get('/api/creator-candidates')
def api_creator_candidates():
    try:
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            return api_error('Duplicate request parameters are not allowed')
        return api_success(**creator_candidate_service().query(request.args.to_dict()))
    except CandidateRequestError as error:
        return api_error(str(error), error.status)
    except (OSError, ValueError, KeyError) as error:
        app.logger.error('Creator candidate evidence unavailable: %s', error)
        return api_error('Frozen creator candidate evidence unavailable or invalid', 503)


@app.route("/")
def dashboard():
    return render_template("measured_dashboard.html" if app.config['DATA_MODE'] == 'real' else "dashboard.html", saved_only=False)


@app.route("/hashtag-products")
def hashtag_products():
    return render_template("hashtag-products.html")


@app.route("/influencer-collaboration")
def influencer_collaboration():
    return render_template("influencer-collaboration.html")


@app.route("/watchlist")
def watchlist_page():
    return render_template("measured_dashboard.html" if app.config['DATA_MODE'] == 'real' else "watchlist.html", saved_only=True)


@app.route("/trend-detail/<trend_id>")
def trend_detail(trend_id: str):
    trend = find_trend(trend_id)
    if not trend:
        return render_template("not_found.html"), 404
    return render_template("trend-detail.html", trend=trend)


@app.route("/roi-insights")
def roi_insights():
    try:
        service = creator_candidate_service()
    except (OSError, ValueError, KeyError):
        return render_template('roi-insights.html', topics=[], trend=None, context_unavailable=True), 503
    topics = [(key, value['canonical_topic']) for key, value in service.products.items()]
    topic_id = request.args.get('topic_id')
    if topic_id and topic_id not in service.products:
        return api_error('Unknown campaign topic', 404)
    trend = {'id': topic_id, 'name': service.products[topic_id]['canonical_topic']} if topic_id else None
    return render_template("roi-insights.html", topics=topics, trend=trend)


@app.get('/campaign-scenario')
def campaign_scenario():
    return render_template('campaign-scenario.html', objectives=OBJECTIVES, formats=FORMATS)


def campaign_context_service():
    return CampaignContext(creator_candidate_service(), app.config['DATABASE_PATH'], BASE_DIR)


def scenario_failure(error):
    return api_error(str(error), getattr(error, 'status', 400), code=getattr(error, 'code', 'invalid_upstream_context'))


@app.get('/api/campaign-scenarios/context')
def api_campaign_context():
    try:
        if any(len(request.args.getlist(key)) != 1 for key in request.args):
            raise ScenarioError('duplicate_parameter', 'Duplicate context parameters are not allowed', 400)
        return api_success(**campaign_context_service().resolve(request.args.to_dict()))
    except (ScenarioError, CandidateRequestError) as error:
        return scenario_failure(error)
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        app.logger.error('Campaign source context unavailable: %s', error)
        return api_error('Campaign evidence unavailable or invalid', 503, code='source_unavailable')


@app.post('/api/campaign-scenarios/evaluate')
def api_evaluate_campaign():
    if request.content_length is not None and request.content_length > 65536:
        return api_error('Scenario request is too large', 413, code='request_too_large')
    try:
        return api_success(**evaluate_campaign(request.get_json(silent=True), campaign_context_service()))
    except (ScenarioError, CandidateRequestError) as error:
        return scenario_failure(error)
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        app.logger.error('Campaign source context unavailable: %s', error)
        return api_error('Campaign evidence unavailable or invalid', 503, code='source_unavailable')


@app.route("/api/")
def api_index():
    return api_success(
        routes=[
            "GET /api/summary",
            "GET /api/trends",
            "GET /api/chart-data",
            "GET /api/watchlist",
            "POST /api/watchlist/add",
            "POST /api/watchlist/remove",
            "GET /api/malaysia/product-mapping",
            "GET /api/product-fit/<topic_id>?query_id=canonical",
            "GET /api/campaign-scenarios/context (all identity/version pins required)",
            "POST /api/campaign-scenarios/evaluate",
            "GET /api/creator-candidates/context/<topic_id>",
            "GET /api/creator-candidates (explicit context and four version pins required)",
            "GET /api/malaysia/hashtag-products/<hashtag>",
            "POST /api/malaysia/chatbot (retired; HTTP 410)",
            "GET /api/malaysia/influencers",
        ]
    )


@app.route("/api/summary")
def api_summary():
    trends = get_trends()
    if app.config["DATA_MODE"] == "real":
        available = sum(trend["data_mode"] == "real" for trend in trends)
        return api_success(
            data_mode="real" if available else "unavailable",
            reason=None if available else "No measured observations collected",
            tracked_topics=len(trends), observed_topics=available,
            emerging_trends=None, decay_trends=None, high_roi_trends=None,
            total_reach=None, avg_engagement=None, top_platform=None,
        )
    return jsonify(
        {
            "emerging_trends": len([trend for trend in trends if trend["lifecycle"] == "Emerging"]),
            "decay_trends": len([trend for trend in trends if trend["lifecycle"] == "Decay"]),
            "high_roi_trends": None,
            "total_reach": sum(trend["reach"] for trend in trends),
            "avg_engagement": round(sum(trend["engagement_rate"] for trend in trends) / len(trends), 1),
            "top_platform": "TikTok",
            "data_mode": "demo",
        }
    )


@app.route("/api/trends")
def api_trends():
    platform = request.args.get("platform", "").lower()
    audience = request.args.get("audience", "").lower()
    category = request.args.get("category", "").lower()

    scenario = request.args.get("scope") == "scenario"
    trends = [{**row, "data_mode": "demo", "scenario_kind": "assumption_based"} for row in TRENDS] if scenario else get_trends()
    if platform:
        trends = [trend for trend in trends if trend["platform"].lower() == platform]
    if audience:
        trends = [trend for trend in trends if audience.replace(" ", "") in trend["audience"].lower().replace(" ", "")]
    if category:
        trends = [trend for trend in trends if trend["category"].lower() == category]

    mode = "demo" if scenario or app.config["DATA_MODE"] == "demo" else "real" if any(t["data_mode"] == "real" for t in trends) else "unavailable"
    return api_success(data_mode=mode, trends=trends,
                       output_kind="assumption_based" if scenario else "trend_intelligence",
                       reason="No measured observations match these filters" if mode == "unavailable" else None)


@app.route("/api/trends/<trend_id>")
def api_trend(trend_id):
    trend = find_trend(trend_id)
    if not trend:
        return api_error("Topic not found", 404, data_mode="unavailable")
    return api_success(data_mode=trend["data_mode"], trend=trend)


@app.route("/api/trends/<trend_id>/observations")
def api_observations(trend_id):
    if not any(t["id"] == trend_id for t in trend_service().db.topics()):
        return api_error("Topic not found", 404, data_mode="unavailable")
    rows = trend_service().db.observations(trend_id)
    return api_success(data_mode="real" if rows else "unavailable", observations=rows,
                       reason=None if rows else "No measured observations collected")


@app.get('/api/intelligence/<topic_id>')
def api_intelligence(topic_id):
    topics = json.loads((DATA_DIR / 'tracked_topics.json').read_text(encoding='utf-8'))
    try:
        result = IntelligenceService(app.config['DATABASE_PATH'], topics).topic(
            topic_id, request.args.get('query_id', 'canonical'))
    except KeyError:
        return api_error('Topic not found', 404, data_mode='unavailable')
    except ValueError as error:
        return api_error(str(error), 400, data_mode='unavailable')
    return api_success(**result)


@app.route("/api/chart-data")
def api_chart_data():
    if app.config["DATA_MODE"] == "real":
        datasets = []
        provenance = []
        for topic in trend_service().db.topics():
            rows = trend_service().db.observations(topic["id"])
            metric_groups = (trend_service().db.metrics(topic["id"]) or trend_service().recalculate(topic["id"])).get("series", [])
            for series in metric_groups:
                selected = [row for row in rows if row["source"] == series["source"]
                            and row["metric"] == series["metric"] and row["series_id"] == series["series_id"]
                            and row["source_identifier"] == series["source_identifier"]]
                dates = sorted({row["observation_date"] for row in selected})
                values = {row["observation_date"]: row["value"] for row in selected}
                datasets.append({"label": f"{topic['name']} / {series['source']} / {series['metric']}",
                                 "observations": [{"date": day, "value": values[day]} for day in dates],
                                 "series_id": series["series_id"], "unit": series["metric"]})
                provenance.extend(selected)
        return api_success(data_mode="real" if datasets else "unavailable", labels=[], datasets=datasets,
                           reason=None if datasets else "No measured chart history",
                           provenance=provenance)
    return jsonify(
        {
            "labels": ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5", "Week 6"],
            "datasets": [
                {
                    "label": trend["name"],
                    "data": [max(5, trend["trend_score"] - 25 + index * 5) for index in range(6)],
                    "borderColor": color,
                    "backgroundColor": color.replace("1)", "0.12)"),
                    "tension": 0.35,
                }
                for trend, color in zip(
                    TRENDS[:3],
                    ["rgba(37, 99, 235, 1)", "rgba(16, 185, 129, 1)", "rgba(236, 72, 153, 1)"],
                )
            ],
        }
    )


@app.route("/api/malaysia/product-mapping")
def api_malaysia_product_mapping():
    service = ProductFit()
    mappings = [service.legacy(topic_id) for topic_id in service.intents['topics']]
    return api_success(
        total_mappings=len(mappings),
        product_mappings=mappings,
        seasonal_opportunities={}, malaysia_insights={"climate_considerations":[]},
        data_mode='real', output_kind='rule_based_catalogue_fit',
        catalogue_version=service.catalogue.version,
    )


@app.route("/api/malaysia/hashtag-products/<hashtag>")
def api_malaysia_hashtag_products(hashtag: str):
    clean = hashtag.strip().replace("#", "")
    if not clean:
        return api_error("Hashtag is required", 400, hashtag=hashtag)
    try:
        recommendations = hashtag_recommendations(clean)
    except KeyError:
        return api_error('No configured Product Fit intent for this hashtag', 404, hashtag='#'+clean)
    return api_success(
        hashtag=f"#{clean}",
        recommendations=recommendations,
        timestamp=now_iso(),
        data_mode='real', output_kind='rule_based_catalogue_fit',
        malaysia_context={
            "climate_suitable": None,
            "local_availability": None,
            "cultural_relevance": recommendations["malaysia_relevance"],
        },
    )


@app.post("/api/assistant/explain")
def api_assistant_explain():
    """Local-only, opt-in Gemini explanation of one measured topic.

    Separate from the nine-tool deterministic harness. Never publicly expose
    this key-backed endpoint without authentication and server-side rate limiting.
    """
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return api_error("Local access only", 403, code="local_only")
    if os.getenv("TRENDZ_ASSISTANT_ENABLED", "false").lower() != "true":
        return api_error("Assistant disabled", 503, code="assistant_disabled")
    if app.config["DATA_MODE"] != "real":
        return api_error("Assistant requires measured data mode", 422, code="not_measured")
    if request.content_length is not None and request.content_length > 2048:
        return api_error("Request too large", 413, code="request_too_large")
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"topic_id", "question"}:
        return api_error("Expected topic_id and question", 400, code="invalid_request")
    topic_id, question = data["topic_id"], data["question"]
    if not isinstance(topic_id, str) or len(topic_id) > 100 or not isinstance(question, str) or not question.strip() or len(question) > 500:
        return api_error("Invalid topic or question", 400, code="invalid_request")
    try:
        topics = json.loads((DATA_DIR / "tracked_topics.json").read_text(encoding="utf-8"))
        if not any(t["id"] == topic_id for t in topics):
            return api_error("Unknown topic", 404, code="unknown_topic")
        intelligence = IntelligenceService(app.config["DATABASE_PATH"], topics).topic(topic_id)
        if intelligence.get("data_mode") != "real":
            return api_error("Measured evidence unavailable", 422, code="no_evidence")
        evidence = compact_evidence(intelligence)
        answer = explain(question, evidence)
    except GeminiUnavailable as error:
        # The provider chains the original exception. Log only its type and
        # numeric HTTP code: never log the raw provider error, prompt, or key.
        cause = error.__cause__
        cause_type = type(cause).__name__ if cause is not None else "None"
        raw_status = getattr(cause, "code", None) if cause is not None else None
        if not isinstance(raw_status, int):
            raw_status = getattr(cause, "status_code", None) if cause is not None else None
        status = raw_status if isinstance(raw_status, int) and 100 <= raw_status <= 599 else None
        app.logger.warning(
            "Gemini diagnostic: cause_type=%s, provider_status=%s",
            cause_type, status if status is not None else "unknown",
        )
        if status == 429:
            message, code = "Gemini rate limit or quota reached. Check Google AI Studio usage.", "provider_quota"
        elif status in (400, 404):
            message, code = "Gemini rejected the request or model. Check your configured model and request limits.", "provider_request_rejected"
        elif status in (401, 403):
            message, code = "Gemini API access denied. Check the API key and project permissions.", "provider_access_denied"
        else:
            message, code = "Gemini unavailable. Check the local server diagnostic and provider configuration.", "provider_unavailable"
        return api_error(message, 503, code=code)
    except (KeyError, ValueError, sqlite3.Error, OSError) as error:
        app.logger.warning("Trend intelligence evidence unavailable: %s", type(error).__name__)
        return api_error("Measured evidence unavailable", 503, code="evidence_unavailable")
    return api_success(
        answer=answer, topic_id=topic_id, query_id=evidence["query_id"],
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        data_mode="real", output_kind="generative_explanation_unverified",
        disclaimer="AI-generated interpretation of stored evidence; verify against source components. Not live data or a forecast.",
        evidence_url=f"/api/intelligence/{topic_id}",
    )


@app.route("/api/malaysia/chatbot", methods=["POST"])
def api_malaysia_chatbot():
    return api_error('Legacy demo chatbot retired. Deterministic assistant infrastructure is test-only; no model is connected.',
                     410, code='legacy_assistant_retired')


@app.route("/api/malaysia/trend-opportunities")
def api_malaysia_trend_opportunities():
    return api_success(
        monthly_opportunities={
            "May": [{"event": "Mid-year sale", "idea": "Hydration bundle push", "priority": "High"}],
            "August": [{"event": "Merdeka", "idea": "Local pride color story", "priority": "Medium"}],
            "October": [{"event": "Deepavali", "idea": "Festive long-wear glam", "priority": "High"}],
        },
        proactive_trends=[
            {"name": "Humidity-proof glow", "category": "skincare", "score": 88},
            {"name": "Festive lip wardrobe", "category": "makeup", "score": 81},
            {"name": "Scalp reset Sunday", "category": "haircare", "score": 74},
        ],
        gap_opportunities=["More SPF content for men", "Inclusive shade-matching explainers"],
    )


@app.route("/api/malaysia/community-analysis")
def api_malaysia_community_analysis():
    return api_success(
        community_analysis={
            "malay": {"top_category": "skincare", "growth": 16, "recommendation": "Halal-friendly messaging and SPF education"},
            "chinese": {"top_category": "skincare", "growth": 12, "recommendation": "Ingredient-led serum content"},
            "indian": {"top_category": "makeup", "growth": 18, "recommendation": "Festival looks and inclusive foundation shades"},
            "mixed": {"top_category": "haircare", "growth": 9, "recommendation": "Humidity and frizz-control routines"},
        },
        total_communities=4,
        insights={"most_active": "indian", "fastest_growing": "malay", "highest_engagement": "mixed"},
    )


@app.route("/api/malaysia/smart-questions/<trend_id>")
def api_malaysia_smart_questions(trend_id: str):
    trend = find_trend(trend_id)
    if not trend:
        return api_error("Trend not found", 404)
    return api_success(
        smart_questions=[
            f"Which product bundle should support {trend['name']}?",
            "What creator format should we test first?",
            "What budget range is sensible for MVP launch?",
        ],
        trend_summary={"name": trend["name"], "score": trend["trend_score"], "action": trend["action"]},
    )


@app.route("/api/malaysia/influencers")
def api_malaysia_influencers():
    return api_success(influencers=INFLUENCERS, total_count=len(INFLUENCERS), message="Influencers loaded")


@app.route("/api/ai-trend-forecasting")
def api_ai_trend_forecasting():
    top_trend = max(TRENDS, key=lambda trend: trend["growth"])
    return api_success(
        trend_summary={"total_trends": len(TRENDS), "top_growth_trend": top_trend["name"]},
        market_dynamics={"momentum_direction": "Growing", "confidence": 0.82},
        predictions={"next_big_trend": top_trend["name"], "platform_shifts": "Short-form education"},
        recommendations={"investment_priorities": ["Creator testing", "SPF education", "Festive makeup bundles"]},
    )


@app.route("/api/early-detection")
def api_early_detection():
    return jsonify(
        [
            {
                "trend_id": trend["id"],
                "trend_name": trend["name"],
                "early_trend_score": trend["early_trend_score"],
                "action_urgency": trend["action_urgency"],
            }
            for trend in sorted(TRENDS, key=lambda item: item["early_trend_score"], reverse=True)[:3]
        ]
    )


@app.route("/api/business-value")
def api_business_value():
    return api_error('Legacy mock economics retired. Use a pinned campaign scenario.', 410,
                     code='legacy_roi_retired', replacement='/roi-insights')


@app.route("/api/focus-groups")
def api_focus_groups():
    return jsonify(
        [
            {"trend_id": "glass-skin", "platform": "TikTok", "demographics": {"age_range": "18-24", "gender": "All genders"}},
            {"trend_id": "sunscreen-reapply", "platform": "Instagram", "demographics": {"age_range": "25-34", "gender": "All genders"}},
            {"trend_id": "deepavali-glam", "platform": "Instagram", "demographics": {"age_range": "18-30", "gender": "Mostly women"}},
        ]
    )


@app.route("/api/content-creation")
def api_content_creation():
    return jsonify(
        [
            {
                "trend_id": trend["id"],
                "trend_name": trend["name"],
                "platform": trend["platform"],
                "content_ideas": trend["content_ideas"],
            }
            for trend in TRENDS[:4]
        ]
    )


@app.route("/api/watchlist")
def api_watchlist():
    watchlist = get_watchlist()
    return api_success(data_mode=app.config["DATA_MODE"], watchlist=watchlist, alerts=watchlist, total_count=len(watchlist))


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return api_error("JSON body must be an object", 400)
    trend_id = str(data.get("trend_id", "")).strip()
    if not trend_id:
        return api_error("trend_id is required", 400)

    trend = find_trend(trend_id)
    if not trend:
        return api_error("Trend not found", 404)

    watchlist = get_watchlist()
    if any(item.get("trend_id") == trend_id for item in watchlist):
        return api_error("Trend is already in your watchlist", 409)

    try:
        trend_service().db.add_watch(trend_id, now_iso())
    except sqlite3.IntegrityError:
        return api_error("Trend is already in your watchlist", 409)
    watchlist = get_watchlist()
    item = next(item for item in watchlist if item["trend_id"] == trend_id)
    return api_success(data_mode=app.config["DATA_MODE"], message="Trend added to watchlist", item=item, watchlist=watchlist)


@app.route("/api/watchlist/remove", methods=["POST"])
def api_watchlist_remove():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return api_error("JSON body must be an object", 400)
    trend_id = str(data.get("trend_id", "")).strip()
    if not trend_id:
        return api_error("trend_id is required", 400)

    if not trend_service().db.remove_watch(trend_id):
        return api_error("Trend not found in watchlist", 404)
    return api_success(data_mode=app.config["DATA_MODE"], message="Trend removed from watchlist", watchlist=get_watchlist())


@app.route("/api/ingredient-popularity")
def api_ingredient_popularity():
    return api_success(
        ingredients=[
            {"name": "Hyaluronic Acid", "score": 92, "growth": 14},
            {"name": "Niacinamide", "score": 81, "growth": 9},
            {"name": "Ceramides", "score": 74, "growth": 7},
        ]
    )


@app.route("/api/visual-trend-recognition")
def api_visual_trend_recognition():
    return api_success(
        visual_trends=[
            {"name": "Dewy base", "score": 88},
            {"name": "Glossy lips", "score": 76},
            {"name": "Sleek hair", "score": 69},
        ]
    )


@app.route("/api/trigger-full-setup")
def api_trigger_full_setup():
    service = trend_service()
    return api_success(data_mode=service.mode, message="SQLite is initialized. Run scripts/ingest.py to collect observations.")


@app.route("/api/roi-prediction")
def api_roi_prediction():
    return api_error('Legacy mock ROI retired. No campaign performance prediction is available.', 410,
                     code='legacy_roi_retired', replacement='/api/campaign-scenarios/evaluate')


@app.route("/api/multimodal-detection")
def api_multimodal_detection():
    return api_success(
        hashtags_data=[
            {"hashtag": f"#{trend['hashtag']}", "text_score": trend["trend_score"], "influencer_score": trend["fomo_score"]}
            for trend in TRENDS[:4]
        ],
        summary="MVP combines hashtag, engagement, and creator fit signals.",
    )


@app.route("/api/advanced-forecasting")
def api_advanced_forecasting():
    return api_success(
        forecasts=[
            {
                "trend_id": trend["id"],
                "trend_name": trend["name"],
                "forecast": [max(0, round(trend["trend_score"] + trend["growth"] * step / 6, 1)) for step in range(1, 7)],
            }
            for trend in TRENDS[:4]
        ],
        forecast_period="6 weeks",
        malaysia_adjusted=True,
    )


@app.route("/api/trend-radar")
def api_trend_radar():
    radar_data = {"emerging": [], "growing": [], "peak": [], "declining": []}
    for trend in TRENDS:
        bucket = "emerging" if trend["lifecycle"] == "Emerging" else "growing" if trend["lifecycle"] == "Growing" else "peak" if trend["trend_score"] >= 80 else "declining"
        radar_data[bucket].append({"name": trend["name"], "score": trend["trend_score"], "platform": trend["platform"], "category": trend["category"]})
    return api_success(
        radar_data=radar_data,
        total_trends=len(TRENDS),
        heatmap_intensity={key: len(value) for key, value in radar_data.items()},
    )


if __name__ == "__main__":
    trend_service()
    print("Starting TrendZ at http://localhost:5000")
    app.run(debug=False, host="127.0.0.1", port=5000)
