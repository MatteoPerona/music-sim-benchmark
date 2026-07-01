"""Build and filter the AOTY user×album score matrix for v0."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import AOTY_RAW_DIR, PROCESSED_DIR


@dataclass
class MatrixBuildResult:
    reviews: list[dict[str, Any]]
    user_index: dict[str, int]
    album_index: dict[str, int]
    stats: dict[str, Any]
    quality: dict[str, Any]


def _parse_timestamp(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned)


def load_raw_user_reviews(raw_dir: Path = AOTY_RAW_DIR) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for album_dir in sorted(raw_dir.iterdir()):
        if not album_dir.is_dir():
            continue
        user_path = album_dir / "user_reviews.json"
        if not user_path.exists():
            continue
        payload = json.loads(user_path.read_text(encoding="utf-8"))
        for item in payload:
            meta = item.get("metadata") or {}
            rows.append(
                {
                    "review_id": item.get("id"),
                    "album_id": meta.get("album_id"),
                    "album_slug": meta.get("album_slug") or album_dir.name,
                    "album_title": meta.get("album_title"),
                    "artist": meta.get("artist"),
                    "username": item.get("author_id"),
                    "score": item.get("score"),
                    "date": item.get("timestamp"),
                    "review_text": item.get("text"),
                    "likes": meta.get("likes"),
                    "url": item.get("url"),
                    "relative_date": meta.get("relative_date"),
                    "date_source": meta.get("date_source"),
                    "aoty_review_id": meta.get("review_id"),
                    "metadata": meta,
                }
            )
    return rows


def dedupe_reviews(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep the latest review per user+album; audit duplicates and date issues."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        user = row.get("username")
        album = row.get("album_slug")
        if not user or not album:
            continue
        grouped[(user.lower(), album)].append(row)

    kept: list[dict[str, Any]] = []
    duplicate_groups = 0
    edited_date_flags = 0
    relative_date_only = 0
    imprecise_dates = 0
    listing_relative_dates = 0

    for key, entries in grouped.items():
        if len(entries) > 1:
            duplicate_groups += 1
        entries.sort(key=lambda r: _parse_timestamp(r["date"]), reverse=True)
        winner = entries[0]
        kept.append(winner)

        for entry in entries:
            if entry.get("date_source") == "listing_relative" or entry.get("relative_date"):
                listing_relative_dates += 1
            if entry.get("relative_date") and entry.get("date_source") != "review_page":
                relative_date_only += 1
            if entry.get("date", "").endswith("T00:00:00Z"):
                imprecise_dates += 1

        for entry in entries[1:]:
            old_date = entry.get("date", "")
            new_date = winner.get("date", "")
            if old_date and new_date and old_date != new_date:
                edited_date_flags += 1

    audit = {
        "duplicate_user_album_groups": duplicate_groups,
        "reviews_before_dedup": len(rows),
        "reviews_after_dedup": len(kept),
        "edited_or_redated_reviews_dropped": edited_date_flags,
        "entries_with_relative_date_metadata": relative_date_only,
        "entries_with_listing_relative_dates": listing_relative_dates,
        "entries_with_midnight_utc_dates": imprecise_dates,
    }
    return kept, audit


def apply_matrix_filters(
    rows: list[dict[str, Any]],
    *,
    min_user_reviews: int = 3,
    min_album_reviews: int = 20,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scored = [row for row in rows if row.get("score") is not None]
    dropped_no_score = len(rows) - len(scored)

    def filter_pass(rows_in: list[dict[str, Any]]) -> list[dict[str, Any]]:
        user_counts = Counter(row["username"].lower() for row in rows_in)
        album_counts = Counter(row["album_slug"] for row in rows_in)
        users_ok = {u for u, c in user_counts.items() if c >= min_user_reviews}
        albums_ok = {a for a, c in album_counts.items() if c >= min_album_reviews}
        return [
            row
            for row in rows_in
            if row["username"].lower() in users_ok and row["album_slug"] in albums_ok
        ]

    filtered = filter_pass(scored)
    # Re-apply iteratively because user/album filters interact.
    while True:
        next_filtered = filter_pass(filtered)
        if len(next_filtered) == len(filtered):
            break
        filtered = next_filtered

    users = sorted({row["username"] for row in filtered})
    albums = sorted({row["album_slug"] for row in filtered})
    user_index = {name: idx for idx, name in enumerate(users)}
    album_index = {slug: idx for idx, slug in enumerate(albums)}

    user_review_counts = Counter(row["username"].lower() for row in filtered)
    album_review_counts = Counter(row["album_slug"] for row in filtered)
    n_users = len(users)
    n_albums = len(albums)
    n_cells = len(filtered)
    density = (100.0 * n_cells / (n_users * n_albums)) if n_users and n_albums else 0.0

    per_user_hist = Counter(user_review_counts.values())
    stats = {
        "n_users": n_users,
        "n_albums": n_albums,
        "n_reviews": n_cells,
        "density_pct": round(density, 3),
        "dropped_no_score": dropped_no_score,
        "users_with_ge_3_reviews": sum(1 for c in user_review_counts.values() if c >= 3),
        "albums_with_ge_20_reviews": sum(1 for c in album_review_counts.values() if c >= 20),
        "reviews_per_user_distribution": {str(k): v for k, v in sorted(per_user_hist.items())},
        "reviews_per_album": dict(sorted(album_review_counts.items(), key=lambda kv: -kv[1])),
        "min_user_reviews": min_user_reviews,
        "min_album_reviews": min_album_reviews,
    }
    return filtered, stats, user_index, album_index


def build_matrix(
    raw_dir: Path = AOTY_RAW_DIR,
    *,
    min_user_reviews: int = 3,
    min_album_reviews: int = 20,
) -> MatrixBuildResult:
    raw_rows = load_raw_user_reviews(raw_dir)
    deduped, quality = dedupe_reviews(raw_rows)
    filtered, stats, user_index, album_index = apply_matrix_filters(
        deduped,
        min_user_reviews=min_user_reviews,
        min_album_reviews=min_album_reviews,
    )
    return MatrixBuildResult(
        reviews=filtered,
        user_index=user_index,
        album_index=album_index,
        stats=stats,
        quality=quality,
    )


def save_matrix(
    result: MatrixBuildResult,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    out = output_dir or (PROCESSED_DIR / "aoty")
    out.mkdir(parents=True, exist_ok=True)

    triplets = []
    for row in result.reviews:
        triplets.append(
            [
                result.user_index[row["username"]],
                result.album_index[row["album_slug"]],
                float(row["score"]),
            ]
        )

    matrix_payload = {
        "format": "user_album_score_triplets",
        "n_users": result.stats["n_users"],
        "n_albums": result.stats["n_albums"],
        "density_pct": result.stats["density_pct"],
        "triplets": triplets,
    }

    paths = {
        "matrix": out / "user_album_matrix.json",
        "user_index": out / "user_index.json",
        "album_index": out / "album_index.json",
        "filtered_reviews": out / "filtered_reviews.json",
        "stats": out / "matrix_stats.json",
        "quality": out / "data_quality.json",
    }

    paths["matrix"].write_text(json.dumps(matrix_payload, indent=2), encoding="utf-8")
    paths["user_index"].write_text(json.dumps(result.user_index, indent=2), encoding="utf-8")
    paths["album_index"].write_text(json.dumps(result.album_index, indent=2), encoding="utf-8")
    paths["filtered_reviews"].write_text(
        json.dumps(result.reviews, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["stats"].write_text(json.dumps(result.stats, indent=2), encoding="utf-8")
    paths["quality"].write_text(json.dumps(result.quality, indent=2), encoding="utf-8")
    return paths


def audit_raw_overlap(raw_dir: Path = AOTY_RAW_DIR) -> dict[str, Any]:
    rows = load_raw_user_reviews(raw_dir)
    deduped, quality = dedupe_reviews(rows)
    scored = [row for row in deduped if row.get("score") is not None]

    albums = sorted({row["album_slug"] for row in scored})
    artists = sorted({row.get("artist") for row in scored if row.get("artist")})
    users = {row["username"].lower() for row in scored if row.get("username")}
    user_albums: dict[str, set[str]] = defaultdict(set)
    for row in scored:
        if row.get("username"):
            user_albums[row["username"].lower()].add(row["album_slug"])

    users_ge2 = sum(1 for albums_seen in user_albums.values() if len(albums_seen) >= 2)
    users_ge3 = sum(1 for albums_seen in user_albums.values() if len(albums_seen) >= 3)
    density = (
        100.0 * len(scored) / (len(users) * len(albums))
        if users and albums
        else 0.0
    )

    return {
        "n_albums": len(albums),
        "albums": albums,
        "n_artists": len(artists),
        "artists": artists,
        "n_reviews": len(scored),
        "n_unique_users": len(users),
        "users_with_ge_2_albums": users_ge2,
        "users_with_ge_3_albums": users_ge3,
        "matrix_density_pct": round(density, 3),
        "data_quality": quality,
    }
