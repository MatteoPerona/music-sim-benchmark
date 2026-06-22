#!/usr/bin/env python3
"""Collect Reddit posts and comments via old.reddit.com HTML scraping."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collectors.reddit import collect_reddit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between HTTP requests (default: 1.0).",
    )
    parser.add_argument(
        "--skip-subreddit",
        action="append",
        dest="skip_subreddits",
        help="Skip a subreddit (repeatable), e.g. fengeveryday",
    )
    parser.add_argument(
        "--only-subreddit",
        action="append",
        dest="only_subreddits",
        help="Collect only these subreddits (repeatable)",
    )
    parser.add_argument(
        "--no-global-search",
        action="store_true",
        help="Skip global Reddit searches",
    )
    args = parser.parse_args()

    payload = collect_reddit(
        delay_seconds=args.delay,
        only_subreddits=args.only_subreddits,
        skip_subreddits=args.skip_subreddits,
        include_global_search=not args.no_global_search,
    )
    summary = payload["summary"]
    print(f"Collected {summary['total_items']} Reddit items -> data/raw/reddit/")
    print(f"  scraper: {summary.get('scraper')}")
    print(f"  submissions scanned: {summary['submissions_seen']}")
    print(f"  types: {summary['type_counts']}")
    print(f"  split: {summary['split_counts']}")

    print("\nTop subreddits:")
    for subreddit, count in Counter(summary["subreddit_counts"]).most_common(10):
        print(f"  r/{subreddit}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
