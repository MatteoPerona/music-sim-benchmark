"""Shared data schema for benchmark items."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

Source = Literal[
    "aoty",
    "reddit",
    "youtube",
    "tiktok",
    "press",
    "twitter",
]

Split = Literal["training", "test"] | None


@dataclass
class BenchmarkItem:
    """One piece of text the sim may see (training) or we score against (test)."""

    id: str
    source: Source
    text: str
    timestamp: str  # ISO 8601 UTC
    url: str
    author_id: str | None = None
    score: float | None = None
    split: Split = None
    segment_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkItem":
        return cls(**data)


def make_reddit_item(
    *,
    item_id: str,
    text: str,
    timestamp: datetime,
    url: str,
    author_id: str | None,
    score: float | None,
    metadata: dict[str, Any],
) -> BenchmarkItem:
    return BenchmarkItem(
        id=item_id,
        source="reddit",
        text=text,
        timestamp=timestamp.replace(tzinfo=None).isoformat() + "Z",
        url=url,
        author_id=author_id,
        score=score,
        metadata=metadata,
    )


def make_aoty_item(
    *,
    item_id: str,
    text: str,
    timestamp: datetime,
    url: str,
    author_id: str | None,
    score: float | None,
    metadata: dict[str, Any],
) -> BenchmarkItem:
    return BenchmarkItem(
        id=item_id,
        source="aoty",
        text=text,
        timestamp=timestamp.replace(tzinfo=None).isoformat() + "Z",
        url=url,
        author_id=author_id,
        score=score,
        metadata=metadata,
    )


def make_press_item(
    *,
    item_id: str,
    text: str,
    timestamp: datetime,
    url: str,
    author_id: str | None,
    score: float | None,
    metadata: dict[str, Any],
) -> BenchmarkItem:
    return BenchmarkItem(
        id=item_id,
        source="press",
        text=text,
        timestamp=timestamp.replace(tzinfo=None).isoformat() + "Z",
        url=url,
        author_id=author_id,
        score=score,
        metadata=metadata,
    )
