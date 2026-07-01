#!/usr/bin/env python3
"""Snowball album discovery from overlap users' AOTY profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import AOTY_MANIFEST  # noqa: E402
from src.collectors.aoty import load_manifest, snowball_albums_from_users  # noqa: E402
from src.processing.aoty_matrix import load_raw_user_reviews  # noqa: E402


def overlap_users(raw_dir: Path, min_albums: int = 2) -> list[str]:
    user_albums: dict[str, set[str]] = {}
    for row in load_raw_user_reviews(raw_dir):
        user = row.get("username")
        album = row.get("album_slug")
        if not user or not album:
            continue
        user_albums.setdefault(user.lower(), set()).add(album)
    return sorted(user for user, albums in user_albums.items() if len(albums) >= min_albums)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data" / "raw" / "aoty",
    )
    parser.add_argument(
        "--min-overlap-albums",
        type=int,
        default=2,
        help="Only sample users who reviewed at least this many seed albums.",
    )
    parser.add_argument(
        "--max-users",
        type=int,
        default=80,
        help="Cap profile fetches (polite scraping).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="How many snowball candidates to print/save.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.25,
        help="Seconds between HTTP requests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "aoty" / "snowball_candidates.json",
    )
    args = parser.parse_args()

    manifest = load_manifest(AOTY_MANIFEST)
    exclude_ids = {album["album_id"] for album in manifest}
    users = overlap_users(args.raw_dir, min_albums=args.min_overlap_albums)[: args.max_users]

    print(f"Sampling {len(users)} overlap users (>= {args.min_overlap_albums} seed albums)...")
    ranked = snowball_albums_from_users(
        users,
        delay_seconds=args.delay,
        exclude_album_ids=exclude_ids,
    )

    top = ranked[: args.top]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(top, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n=== TOP {len(top)} SNOWBALL CANDIDATES ===")
    for entry in top:
        print(
            f"  {entry['overlap_users']:>3} users | {entry['album_id']:>8} | "
            f"{entry.get('title', entry['slug'])[:50]}"
        )
    print(f"\nSaved -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
