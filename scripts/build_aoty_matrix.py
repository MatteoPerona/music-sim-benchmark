#!/usr/bin/env python3
"""Apply v0 filters and save the user×album score matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.processing.aoty_matrix import build_matrix, save_matrix  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data" / "raw" / "aoty",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "aoty",
    )
    parser.add_argument("--min-user-reviews", type=int, default=3)
    parser.add_argument("--min-album-reviews", type=int, default=20)
    args = parser.parse_args()

    result = build_matrix(
        args.raw_dir,
        min_user_reviews=args.min_user_reviews,
        min_album_reviews=args.min_album_reviews,
    )
    paths = save_matrix(result, args.output_dir)

    stats = result.stats
    print("=== FILTERED MATRIX ===")
    print(f"Users: {stats['n_users']}")
    print(f"Albums: {stats['n_albums']}")
    print(f"Observed cells: {stats['n_reviews']}")
    print(f"Density: {stats['density_pct']:.3f}%")
    print(f"Users with >=3 reviews: {stats['users_with_ge_3_reviews']}")
    print(f"Albums with >=20 reviews: {stats['albums_with_ge_20_reviews']}")
    print(f"Reviews/user distribution: {stats['reviews_per_user_distribution']}")
    print("\nOutputs:")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
