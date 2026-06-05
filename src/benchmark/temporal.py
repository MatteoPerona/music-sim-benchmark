"""Temporal split utilities."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from config.settings import CUTOFF_DATE, CUTOFF_DATETIME
from src.benchmark.schema import BenchmarkItem, Split


def parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def assign_split(timestamp: datetime | str, *, cutoff: date = CUTOFF_DATE) -> Split:
    dt = parse_timestamp(timestamp) if isinstance(timestamp, str) else timestamp
    item_date = dt.astimezone(timezone.utc).date()
    return "test" if item_date >= cutoff else "training"


def tag_item(item: BenchmarkItem, *, cutoff: date = CUTOFF_DATE) -> BenchmarkItem:
    item.split = assign_split(item.timestamp, cutoff=cutoff)
    return item


def tag_items(items: Iterable[BenchmarkItem], *, cutoff: date = CUTOFF_DATE) -> list[BenchmarkItem]:
    return [tag_item(item, cutoff=cutoff) for item in items]


def assert_no_test_leakage(training_items: Iterable[BenchmarkItem]) -> None:
    for item in training_items:
        if item.split != "training":
            raise ValueError(f"Training leak: {item.id} tagged as {item.split}")


def cutoff_iso() -> str:
    return CUTOFF_DATETIME.isoformat().replace("+00:00", "Z")
