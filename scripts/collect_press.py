#!/usr/bin/env python3
"""Fetch press articles listed in config/press_articles.json."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.press import collect_press  # noqa: E402


def main() -> int:
    items = collect_press()
    split_counts = Counter(item.split for item in items)
    print(f"Collected {len(items)} press articles -> data/raw/press/")
    print(f"Split counts: {dict(split_counts)}")
    for item in items:
        title = item.metadata.get("title", item.id)
        print(f"  [{item.split}] {title} ({item.metadata.get('word_count')} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
