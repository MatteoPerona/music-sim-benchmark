#!/usr/bin/env python3
"""Collect AOTY user and critic reviews for albums in config/aoty_albums.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.aoty import collect_aoty, summarize_collection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--album",
        action="append",
        dest="albums",
        help="Album slug to collect (e.g. what-the-feng). Repeatable. Default: all.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.75,
        help="Seconds between HTTP requests (default: 0.75).",
    )
    args = parser.parse_args()

    payload = collect_aoty(album_ids=args.albums, delay_seconds=args.delay)
    summary = summarize_collection(payload)

    print(f"Wrote combined bundle -> {payload['combined_path']}")
    for album_id, stats in summary.items():
        meta = stats["album_meta"]
        print(f"\n{album_id}")
        print(f"  user reviews: {stats['user_review_count']}")
        print(f"  critic reviews: {stats['critic_review_count']}")
        print(f"  split: {stats['split_counts']}")
        print(f"  mean user score (collected): {stats['mean_user_score']}")
        if meta.get("user_score") is not None:
            print(f"  AOTY displayed user score: {meta.get('user_score')}")
        if meta.get("critic_score") is not None:
            print(f"  AOTY displayed critic score: {meta.get('critic_score')}")

    summary_path = payload["combined_path"].parent / "collection_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    print(f"\nSummary -> {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
