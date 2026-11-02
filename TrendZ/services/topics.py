"""Canonical topics and separately identified query aliases."""

def query_variants(topic):
    queries = [{"id": "canonical", "query": topic["query"]}, *topic.get("aliases", [])]
    ids = [item["id"] for item in queries]
    if len(ids) != len(set(ids)) or any(not item["query"].strip() for item in queries):
        raise ValueError("Query aliases require unique IDs and nonempty wording")
    return [{**topic, "query_id": item["id"], "query": item["query"]} for item in queries]
