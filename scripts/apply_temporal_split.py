#!/usr/bin/env python3
"""Apply temporal split tags to raw JSON item files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmark.schema import BenchmarkItem  # noqa: E402
from src.benchmark.temporal import tag_item  # noqa: E402


def process_file(path: Path, *, dry_run: bool) -> BenchmarkItem:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        raise ValueError(f"{path} is a bundle file; point at individual item JSON files.")

    item = BenchmarkItem.from_dict(payload)
    tagged = tag_item(item)

    if not dry_run:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(tagged.to_dict(), handle, indent=2, ensure_ascii=False)

    return tagged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="JSON files or directories (defaults to data/raw)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    search_roots = args.paths or [ROOT / "data" / "raw"]
    files: list[Path] = []
    for root in search_roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(root.rglob("*.json")))

    files = [path for path in files if path.name != "all_press.json" and not path.name.endswith(".bundle.json")]

    if not files:
        print("No JSON files found.")
        return 1

    counts: Counter[str | None] = Counter()
    for path in files:
        item = process_file(path, dry_run=args.dry_run)
        counts[item.split or "untagged"] += 1

    mode = "Would tag" if args.dry_run else "Tagged"
    print(f"{mode} {len(files)} files. Split counts: {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
