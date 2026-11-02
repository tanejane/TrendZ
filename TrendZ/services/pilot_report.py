"""Query-level coverage, audit and component analysis; no alias aggregation."""

import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .metrics import calculate_series, unavailable

COMPONENTS = ("recent_growth", "acceleration", "persistence", "volatility")


def day_range(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def validate_series(rows, source, expected_dates):
    reasons = []
    if not rows:
        return {"state": "unavailable", "reasons": ["No observations"]}
    if len({r["series_id"] for r in rows}) != 1:
        reasons.append("Multiple independently scaled/cohort series")
    if len({(r.get("query_id", "canonical"), r.get("query", "")) for r in rows}) != 1:
        reasons.append("Mixed query aliases")
    if len({r["observation_date"] for r in rows}) != len(rows):
        reasons.append("Duplicate daily observations")
    metadata = [r["metadata"] for r in rows]
    if source == "google_trends":
        ordered = sorted({date.fromisoformat(r["observation_date"]) for r in rows})
        intervals = [(b - a).days for a, b in zip(ordered, ordered[1:])]
        if intervals and min(intervals) >= 7:
            reasons.append("Returned cadence is weekly/coarser; daily metrics are unsupported")
        requests = {json.dumps(m.get("request", {}), sort_keys=True) for m in metadata}
        if len(requests) != 1 or not metadata[0].get("request"):
            reasons.append("Missing or inconsistent Google request parameters")
        request = metadata[0].get("request", {})
        if request.get("timeframe") != expected_dates[0] + " " + expected_dates[-1]:
            reasons.append("Google request does not match fixed experiment window")
        if request.get("timezone") != "UTC" or request.get("term_type") != "search_term":
            reasons.append("Google timezone/term type differs from experiment")
        if request.get("query") != rows[0].get("query") or request.get("geo") != rows[0]["market"]:
            reasons.append("Request/query/market provenance mismatch")
    if source == "youtube" and rows[0]["metric"] == "discovered_publications":
        if any(not m.get("window_complete") for m in metadata):
            reasons.append("Capped or failed discovery windows; publication counts are lower bounds")
    return {"state": "valid" if not reasons else "invalid", "reasons": reasons}


def export_csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_audit(path):
    if not Path(path).exists():
        return {}
    grouped = defaultdict(list)
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["label"] not in ("", "pending", "relevant", "partially relevant", "irrelevant", "uncertain"):
                raise ValueError("Invalid manual audit label")
            grouped[(row["topic_id"], row["query_id"])].append(row)
    return grouped


def build_report(config, queries, observations, collection, output, include_demo=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    dates = day_range(config["start_date"], config["end_date"])
    rows = [r for r in observations if bool(r.get("is_demo")) == include_demo]
    audit = read_audit(output / "relevance_audit.csv")
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["topic_id"], row.get("query_id", "canonical"), row["source"], row["metric"], row["series_id"])].append(row)
    results = []
    for query in queries:
        for source, metric, signal in (
            ("google_trends", "interest_score", "demand_search"),
            ("youtube", "discovered_publications", "content_supply"),
            ("youtube", "sampled_views", "content_activity"),
            ("youtube", "sampled_likes", "content_activity"),
        ):
            candidates = [group for key, group in grouped.items()
                          if key[:4] == (query["id"], query["query_id"], source, metric)]
            selected = max(candidates, key=lambda group: max(row["retrieved_at"] for row in group)) if candidates else []
            # Snapshots belong to dates after collection starts, not the retrospective window.
            expected = dates if metric in ("interest_score", "discovered_publications") else day_range(
                config.get("snapshot_start", config["end_date"]),
                config.get("snapshot_end", config.get("snapshot_start", config["end_date"])))
            present = {row["observation_date"] for row in selected}
            missing = sorted(set(expected) - present)
            validation = validate_series(selected, source, dates)
            collected = collection.get((query["id"], query["query_id"], source), {})
            values = calculate_series(selected) if selected and validation["state"] == "valid" else {
                key: unavailable("; ".join(validation["reasons"]) or "No observations") for key in COMPONENTS}
            growth = values["recent_growth"]
            direction = "unavailable" if growth["state"] != "available" else (
                "positive" if growth["value"] > 0 else "negative" if growth["value"] < 0 else "flat")
            reviewed = audit.get((query["id"], query["query_id"]), [])
            decided = [r for r in reviewed if r["label"] in ("relevant", "partially relevant", "irrelevant")]
            relevance = sum(r["label"] == "relevant" for r in decided) / len(decided) if decided else None
            results.append({
                "topic_id": query["id"], "query_id": query["query_id"], "query": query["query"],
                "source": source, "metric": metric, "signal": signal,
                "data_mode": "demo" if include_demo else "real" if selected else "unavailable",
                "collection_status": collected.get("state", "not_collected"),
                "collection_reason": collected.get("reason"),
                "observation_count": len(selected), "stored_version_count": len(candidates),
                "expected_days": len(expected), "covered_days": len(set(expected) & present),
                "missing_dates": missing, "missingness_fraction": len(missing) / len(expected),
                "zero_values": sum(r["value"] == 0 for r in selected),
                "query_relevance": {"audit_size": len(reviewed), "decided": len(decided),
                                    "pending": sum(r["label"] in ("", "pending") for r in reviewed),
                                    "uncertain": sum(r["label"] == "uncertain" for r in reviewed),
                                    "relevant_fraction_of_decided": relevance,
                                    "state": "reviewed" if decided else "unavailable"},
                "comparable_series": validation, "series_id": selected[0]["series_id"] if selected else None,
                "window_end": max(present) if present else None,
                "retrieved_at": max((r["retrieved_at"] for r in selected), default=None),
                "source_level_direction": direction, "components": {k: values[k] for k in COMPONENTS},
            })
            results[-1]["query_relevance"]["audit_source"] = "youtube"
            if source == "google_trends":
                results[-1]["query_relevance"] = {
                    "state": "unavailable",
                    "reason": "YouTube sample relevance does not validate Google search intent",
                }
    report = {"experiment": config, "data_mode": "demo" if include_demo else "real" if rows else "unavailable",
              "alias_aggregation": False, "rows": results}
    (output / "analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fields = ["topic_id", "query_id", "query", "source", "metric", "signal", "data_mode",
              "observation_count", "covered_days", "expected_days", "missingness_fraction",
              "source_level_direction", *COMPONENTS, "unavailable_reasons"]
    flattened = []
    for row in results:
        flattened.append({**row, **{k: row["components"][k]["value"] for k in COMPONENTS},
                          "unavailable_reasons": "; ".join(
                              sorted({row["components"][k].get("reason", "") for k in COMPONENTS} - {""}))})
    export_csv(output / "analysis.csv", flattened, fields)
    exports = [{**row, "metadata": json.dumps(row["metadata"], sort_keys=True)} for row in rows]
    fields_obs = ["topic_id", "query_id", "query", "source", "source_identifier", "source_url", "market",
                  "observation_date", "retrieved_at", "metric", "value", "series_id", "is_demo", "metadata"]
    export_csv(output / "observations.csv", exports, fields_obs)
    lines = ["# Phase 2 pilot report", "", "Data mode: " + report["data_mode"],
             "Aliases remain separate. No topic-level aggregated metrics or emerging labels.", "",
             "Google = demand/search interest; YouTube = content supply/activity, not consumer demand.",
             "YouTube counters are measured at retrieval; publication dates do not backdate views.",
             "Audit labels are manual; pending candidates do not establish query relevance.", "",
             "| Topic / query | Source / metric | Observations | Coverage | Growth % | Acceleration pp | Persistence | Volatility | Direction |",
             "|---|---|---:|---|---:|---:|---:|---:|---|"]
    for row in results:
        vals = [str(row["components"][key]["value"]) if row["components"][key]["state"] == "available" else "Unavailable"
                for key in COMPONENTS]
        lines.append("| " + " | ".join([row["topic_id"] + " / " + row["query_id"],
            row["source"] + " / " + row["metric"], str(row["observation_count"]),
            f"{row['covered_days']}/{row['expected_days']}", *vals, row["source_level_direction"]]) + " |")
    lines.extend(["", "## Coverage and quality", "",
                  "| Topic / query | Source / metric | Missing days | Zero values | Series validation | Audit decided / pending | Collection issue |",
                  "|---|---|---:|---:|---|---|---|"])
    for row in results:
        relevance = row["query_relevance"]
        lines.append("| " + " | ".join([
            row["topic_id"] + " / " + row["query_id"], row["source"] + " / " + row["metric"],
            str(len(row["missing_dates"])), str(row["zero_values"]),
            row["comparable_series"]["state"] + ": " + "; ".join(row["comparable_series"]["reasons"]),
            f"{relevance.get('decided', 'Unavailable')} / {relevance.get('pending', 'Unavailable')}",
            (row["collection_reason"] or row["collection_status"]).replace("|", "/"),
        ]) + " |")
    lines.extend(["", "## Unavailable component reasons", ""])
    for row in results:
        reasons = sorted({row["components"][k].get("reason", "") for k in COMPONENTS} - {""})
        if reasons:
            lines.append("- " + row["topic_id"] + " / " + row["query_id"] + " / " +
                         row["source"] + " / " + row["metric"] + ": " + "; ".join(reasons))
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
