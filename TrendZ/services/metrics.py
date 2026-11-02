"""Daily component metrics, never a combined score or lifecycle classifier.

For nonnegative daily x, use contiguous 7-day windows A (oldest), B, C (latest).
Growth = 100*(mean(C)/mean(B)-1); needs 14 days and positive B.
Acceleration = growth(B,C)-growth(A,B), percentage points; needs 21 days.
Persistence = fraction of C strictly above mean(B); needs 14 days.
Volatility = population std(C)/mean(C); needs 7 days and positive C.
Missing days are not zero-filled. Units/sources/scales are never pooled.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, pstdev


def unavailable(reason):
    return {"state": "unavailable", "value": None, "reason": reason}


def measured(value, unit):
    return {"state": "available", "value": round(value, 6), "unit": unit}


def calculate_series(rows):
    values = {row["observation_date"]: row["value"] for row in rows}
    end = date.fromisoformat(max(values))

    def window(offset):
        dates = [(end - timedelta(days=offset + i)).isoformat() for i in range(7)]
        return [values[d] for d in dates] if all(d in values for d in dates) else None

    a, b, c = window(14), window(7), window(0)
    growth = unavailable("Requires 14 contiguous daily observations")
    persistence = unavailable("Requires 14 contiguous daily observations")
    acceleration = unavailable("Requires 21 contiguous daily observations")
    volatility = unavailable("Requires 7 contiguous daily observations")
    if c is not None:
        volatility = measured(pstdev(c) / mean(c), "coefficient_of_variation") if mean(c) > 0 else unavailable("Latest window mean is zero")
    if b is not None and c is not None:
        persistence = measured(sum(v > mean(b) for v in c) / 7, "fraction")
        growth = measured(100 * (mean(c) / mean(b) - 1), "percent") if mean(b) > 0 else unavailable("Previous window mean is zero")
        if a is not None and growth["state"] == "available":
            acceleration = measured(growth["value"] - 100 * (mean(b) / mean(a) - 1), "percentage_points") if mean(a) > 0 else unavailable("Oldest window mean is zero")
    return {"recent_growth": growth, "acceleration": acceleration,
            "persistence": persistence, "volatility": volatility, "as_of": end.isoformat(),
            "history_days": len(values)}


def calculate_topic(observations):
    groups = defaultdict(list)
    for row in observations:
        if not row.get("is_demo"):
            groups[(row["source"], row["metric"], row["series_id"], row["market"],
                    row["source_identifier"], row.get("query_id", "canonical"))].append(row)
    # Choose latest series for each source/metric; never combine independently scaled requests.
    candidates = {}
    for key, rows in groups.items():
        stamp = max(row["retrieved_at"] for row in rows)
        source_metric = (key[0], key[1], key[5])
        if source_metric not in candidates or stamp > candidates[source_metric][0]:
            candidates[source_metric] = (stamp, key, rows)
    series = []
    for _, key, rows in candidates.values():
        if any(row["metadata"].get("window_complete") is False for row in rows):
            calculated = {name: unavailable("Discovery has capped or failed windows") for name in
                          ("recent_growth", "acceleration", "persistence", "volatility")}
            calculated.update(as_of=max(r["observation_date"] for r in rows),
                              history_days=len({r["observation_date"] for r in rows}))
        else:
            calculated = calculate_series(rows)
        series.append({"source": key[0], "metric": key[1], "series_id": key[2],
                       "market": key[3], "source_identifier": key[4], "query_id": key[5], **calculated})
    # One designated signal per independent source, same market and latest date.
    signals = [s for s in series if
               (s["source"] == "youtube" and s["metric"] == "sampled_views")
               or (s["source"] != "youtube" and s["metric"] == "interest_score")]
    # Alias variants are never pooled into topic-level confirmation.
    usable = [s for s in signals if s["query_id"] == "canonical" and s["recent_growth"]["state"] == "available"]
    comparable = len({s["source"] for s in usable}) >= 2 and len({(s["market"], s["as_of"]) for s in usable}) == 1
    confirmation = unavailable("Requires two independent sources with available growth and aligned dates/market")
    if comparable:
        confirmation = measured(sum(s["recent_growth"]["value"] > 0 for s in usable) / len(usable), "fraction_of_sources_growing")
    return {"series": series, "cross_source_confirmation": confirmation,
            "formula_version": "daily-windows-v1", "trend_score": None, "lifecycle": None}
