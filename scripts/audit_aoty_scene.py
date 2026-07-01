#!/usr/bin/env python3
"""Audit raw AOTY scene data: overlap, density, and quality flags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.processing.aoty_matrix import audit_raw_overlap  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data" / "raw" / "aoty",
        help="Directory containing per-album AOTY raw folders.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "aoty" / "audit_report.json",
        help="Where to write the audit JSON report.",
    )
    args = parser.parse_args()

    report = audit_raw_overlap(args.raw_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== AOTY SCENE AUDIT ===")
    print(f"Albums: {report['n_albums']}")
    print(f"Artists: {report['n_artists']} ({', '.join(report['artists'])})")
    print(f"Total scored reviews: {report['n_reviews']}")
    print(f"Unique users: {report['n_unique_users']}")
    print(f"Users with >=2 albums: {report['users_with_ge_2_albums']}")
    print(f"Users with >=3 albums: {report['users_with_ge_3_albums']}")
    print(f"Matrix density: {report['matrix_density_pct']:.2f}%")
    print(f"\nReport -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
