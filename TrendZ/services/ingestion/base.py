"""Source-agnostic observation contract shared by every adapter."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from math import isfinite
from typing import Protocol


@dataclass(frozen=True)
class Observation:
    topic_id: str
    source: str
    source_identifier: str
    market: str
    observation_date: str
    retrieved_at: str
    metric: str
    value: float
    series_id: str
    source_url: str = ""
    metadata: dict = field(default_factory=dict)
    is_demo: bool = False
    query_id: str = "canonical"
    query: str = ""

    def __post_init__(self):
        for name in ("topic_id", "source", "source_identifier", "market", "metric", "series_id", "query_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        date.fromisoformat(self.observation_date)
        timestamp = datetime.fromisoformat(self.retrieved_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")
        object.__setattr__(self, "retrieved_at", timestamp.astimezone(timezone.utc).isoformat())
        if not isfinite(float(self.value)) or float(self.value) < 0:
            raise ValueError("value must be finite and non-negative")
        object.__setattr__(self, "value", float(self.value))
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be an object")
        if not isinstance(self.is_demo, bool):
            raise ValueError("is_demo must be boolean")

    def to_dict(self):
        return asdict(self)


class IngestionAdapter(Protocol):
    def collect(self, topic: dict, previous: list[dict]) -> list[Observation]:
        """Return normalized observations without writing to persistence."""
        ...
