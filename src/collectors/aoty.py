"""Album of the Year review collector."""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import HTTPError, RequestException
from dateutil import parser as date_parser
from dateutil.parser import ParserError

from config.settings import AOTY_BASE_URL, AOTY_MANIFEST, AOTY_RAW_DIR
from src.benchmark.schema import BenchmarkItem, make_aoty_item
from src.benchmark.temporal import tag_item

REQUEST_DELAY_SECONDS = 1.25
REVIEWS_PER_PAGE = 25
IMPERSONATE = "chrome131"
MAX_RETRIES = 6


@dataclass
class ListingReview:
    review_id: str | None
    username: str
    score: int | None
    text: str
    review_url: str | None
    likes: int | None
    relative_date: str | None


def load_manifest(path: Path = AOTY_MANIFEST) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _session() -> curl_requests.Session:
    session = curl_requests.Session(impersonate=IMPERSONATE)
    return session


def fetch_html(session: curl_requests.Session, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, timeout=45)
            if response.status_code == 429:
                wait = min(60, 5 * (2**attempt))
                time.sleep(wait)
                continue
            response.raise_for_status()
            if "Just a moment" in response.text:
                wait = min(60, 5 * (2**attempt))
                time.sleep(wait)
                continue
            return response.text
        except HTTPError as exc:
            last_error = exc
            if exc.response is not None and exc.response.status_code in {429, 503, 502}:
                wait = min(60, 5 * (2**attempt))
                time.sleep(wait)
                continue
            raise
        except RequestException as exc:
            last_error = exc
            wait = min(30, 2 * (2**attempt))
            time.sleep(wait)

    raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts") from last_error


def _parse_review_total(soup: BeautifulSoup) -> int | None:
    counter = soup.select_one(".userReviewCounter")
    text = counter.get_text(" ", strip=True) if counter else ""
    if not text:
        for line in soup.get_text("\n").split("\n"):
            if "user reviews" in line.lower():
                text = line.strip()
                break
    match = re.search(r"of\s+([\d,]+)\s+user reviews", text, re.I)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _parse_listing_reviews(soup: BeautifulSoup) -> list[ListingReview]:
    reviews: list[ListingReview] = []
    for row in soup.select(".albumReviewRow"):
        name_el = row.select_one(".userReviewName a")
        if not name_el:
            continue

        href = name_el.get("href", "")
        username_match = re.search(r"/user/([^/]+)/?", href)
        username = username_match.group(1) if username_match else name_el.get_text(strip=True)

        review_id = None
        row_id = row.get("id", "")
        if row_id.startswith("review_"):
            review_id = row_id.removeprefix("review_")

        rating_el = row.select_one(".ratingBlock .rating, .rating")
        score = None
        if rating_el:
            score_match = re.search(r"\d+", rating_el.get_text(strip=True))
            score = int(score_match.group()) if score_match else None

        text_el = row.select_one(".albumReviewText")
        text = text_el.get_text(" ", strip=True) if text_el else ""

        comment_link = row.select_one(".review_comments a[href*='/album/']")
        review_url = None
        if comment_link and comment_link.get("href"):
            review_url = urljoin(AOTY_BASE_URL, comment_link["href"])

        likes_el = row.select_one(".review_likes")
        likes = None
        if likes_el:
            likes_text = likes_el.get_text(strip=True).replace(",", "")
            likes = int(likes_text) if likes_text.isdigit() else None

        relative_date_el = row.select_one(".review_date")
        relative_date = relative_date_el.get_text(strip=True) if relative_date_el else None

        reviews.append(
            ListingReview(
                review_id=review_id,
                username=username,
                score=score,
                text=text,
                review_url=review_url,
                likes=likes,
                relative_date=relative_date,
            )
        )
    return reviews


def _listing_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}p={page}"


RELATIVE_DATE_RE = re.compile(
    r"(?P<value>\d+)\s*(?P<unit>y|yr|year|years|mo|mon|month|months|w|wk|week|weeks|d|day|days|h|hr|hour|hours|m|min|minute|minutes)\b",
    re.I,
)


def _parse_relative_date_text(raw: str, reference: datetime | None = None) -> datetime:
    from datetime import timedelta

    ref = reference or datetime.now(timezone.utc)
    match = RELATIVE_DATE_RE.search(raw.strip())
    if not match:
        raise ValueError(f"Unrecognized relative date: {raw!r}")

    value = int(match.group("value"))
    unit = match.group("unit").lower()
    if unit in {"y", "yr", "year", "years"}:
        delta = timedelta(days=value * 365)
    elif unit in {"mo", "mon", "month", "months"}:
        delta = timedelta(days=value * 30)
    elif unit in {"w", "wk", "week", "weeks"}:
        delta = timedelta(weeks=value)
    elif unit in {"d", "day", "days"}:
        delta = timedelta(days=value)
    elif unit in {"h", "hr", "hour", "hours"}:
        delta = timedelta(hours=value)
    else:
        delta = timedelta(minutes=value)

    return ref - delta


def _parse_review_date_text(raw: str, reference: datetime | None = None) -> datetime:
    cleaned = raw.strip()
    if not cleaned:
        raise ValueError("Empty review date")

    if "(updated" in cleaned.lower():
        cleaned = cleaned.split("(updated")[0].strip()

    try:
        parsed = date_parser.parse(cleaned)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError, ParserError):
        return _parse_relative_date_text(cleaned, reference=reference)


def _fetch_exact_review_date(
    session: curl_requests.Session,
    review_url: str,
    *,
    fallback_relative_date: str | None = None,
) -> datetime:
    html = fetch_html(session, review_url)
    soup = BeautifulSoup(html, "lxml")
    date_el = soup.select_one(".reviewDate")
    if date_el:
        return _parse_review_date_text(date_el.get_text(strip=True))
    if fallback_relative_date:
        return _parse_relative_date_text(fallback_relative_date)
    raise ValueError(f"No .reviewDate found on {review_url}")


def _guess_review_url(album_id: int, album_slug: str, username: str) -> str:
    return f"{AOTY_BASE_URL}/user/{username}/album/{album_id}-{album_slug}/"


def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return {entry["review_url"]: entry for entry in payload}


def _save_checkpoint(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(list(entries.values()), handle, indent=2, ensure_ascii=False)


def collect_user_reviews(
    session: curl_requests.Session,
    album: dict[str, Any],
    *,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    output_dir: Path | None = None,
    fetch_exact_dates: bool = True,
) -> list[BenchmarkItem]:
    base_url = album["user_reviews_url"]
    album_id = album["album_id"]
    album_slug = album["id"]
    checkpoint_path = (output_dir or AOTY_RAW_DIR / album_slug) / "user_reviews.checkpoint.json"
    checkpoint = _load_checkpoint(checkpoint_path)

    first_html = fetch_html(session, base_url)
    first_soup = BeautifulSoup(first_html, "lxml")
    total_reviews = _parse_review_total(first_soup)
    first_page_reviews = _parse_listing_reviews(first_soup)

    total_pages = 1
    if total_reviews:
        total_pages = max(1, math.ceil(total_reviews / REVIEWS_PER_PAGE))

    listing_reviews: list[ListingReview] = list(first_page_reviews)
    for page in range(2, total_pages + 1):
        time.sleep(delay_seconds)
        html = fetch_html(session, _listing_url(base_url, page))
        listing_reviews.extend(_parse_listing_reviews(BeautifulSoup(html, "lxml")))

    seen: set[tuple[str, str | None]] = set()
    unique_listing: list[ListingReview] = []
    for review in listing_reviews:
        key = (review.username.lower(), review.review_id)
        if key in seen:
            continue
        seen.add(key)
        unique_listing.append(review)

    items: list[BenchmarkItem] = []
    for index, listing in enumerate(unique_listing):
        review_url = listing.review_url or _guess_review_url(album_id, album_slug, listing.username)

        if review_url in checkpoint:
            item = BenchmarkItem.from_dict(checkpoint[review_url]["item"])
            items.append(item)
            continue

        if fetch_exact_dates:
            time.sleep(delay_seconds)
            reviewed_at = _fetch_exact_review_date(
                session,
                review_url,
                fallback_relative_date=listing.relative_date,
            )
            date_source = "review_page"
        elif listing.relative_date:
            reviewed_at = _parse_relative_date_text(listing.relative_date)
            date_source = "listing_relative"
        else:
            time.sleep(delay_seconds)
            reviewed_at = _fetch_exact_review_date(
                session,
                review_url,
                fallback_relative_date=listing.relative_date,
            )
            date_source = "review_page"

        review_key = listing.review_id or listing.username
        item = make_aoty_item(
            item_id=f"aoty:user:{album_slug}:{review_key}",
            text=listing.text,
            timestamp=reviewed_at,
            url=review_url,
            author_id=listing.username,
            score=float(listing.score) if listing.score is not None else None,
            metadata={
                "review_type": "user",
                "album_id": album_id,
                "album_slug": album_slug,
                "album_title": album["title"],
                "artist": album["artist"],
                "review_id": listing.review_id,
                "likes": listing.likes,
                "relative_date": listing.relative_date,
                "date_source": date_source,
            },
        )
        item = tag_item(item)
        items.append(item)

        checkpoint[review_url] = {"review_url": review_url, "item": item.to_dict()}
        if index % 10 == 0:
            _save_checkpoint(checkpoint_path, checkpoint)

    _save_checkpoint(checkpoint_path, checkpoint)
    return items


def _parse_album_scores(soup: BeautifulSoup) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    user_el = soup.select_one(".albumUserScore")
    critic_el = soup.select_one(".albumCriticScore")
    if user_el:
        match = re.search(r"\d+", user_el.get_text(strip=True))
        scores["user_score"] = int(match.group()) if match else None
        count_match = re.search(r"\(([\d,]+)\)", user_el.get_text(strip=True))
        if count_match:
            scores["user_review_count_displayed"] = int(count_match.group(1).replace(",", ""))
    if critic_el:
        match = re.search(r"\d+", critic_el.get_text(strip=True))
        scores["critic_score"] = int(match.group()) if match else None

    genre_els = soup.select(".albumGenres a, .genre a, a.genre")
    genres = [el.get_text(strip=True) for el in genre_els if el.get_text(strip=True)]
    if genres:
        scores["genres"] = genres

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if payload.get("@type") == "MusicAlbum":
            scores["release_date"] = payload.get("datePublished")
            genre = payload.get("genre")
            if genre:
                scores["genres"] = genre if isinstance(genre, list) else [genre]
            rating = payload.get("aggregateRating") or {}
            if rating.get("name") == "Critic Score":
                scores["critic_score"] = int(float(rating.get("ratingValue")))
                scores["critic_review_count"] = int(rating.get("ratingCount", 0))
    return scores


def _parse_critic_date(row: BeautifulSoup) -> datetime | None:
    dated = row.select_one(".albumReviewLinks .actionContainer[title]")
    if dated and dated.get("title"):
        parsed = date_parser.parse(dated["title"])
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def collect_critic_reviews(
    session: curl_requests.Session,
    album: dict[str, Any],
) -> list[BenchmarkItem]:
    html = fetch_html(session, album["album_page_url"])
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("#criticReviewContainer")
    if not container:
        return []

    album_slug = album["id"]
    album_id = album["album_id"]
    items: list[BenchmarkItem] = []

    for row in container.select(".albumReviewRow"):
        publication_el = row.select_one(".publication a, a[href*='/publication/']")
        publication = publication_el.get_text(strip=True) if publication_el else None

        author_el = row.select_one(".author a")
        author = author_el.get_text(strip=True) if author_el else None

        rating_el = row.select_one(".albumReviewRating")
        score = None
        if rating_el:
            match = re.search(r"\d+", rating_el.get_text(strip=True))
            score = int(match.group()) if match else None

        text_el = row.select_one(".albumReviewText")
        text = text_el.get_text(" ", strip=True) if text_el else ""

        external_el = row.select_one(".extLink a[href], .extLinkIcon a[href]")
        external_url = external_el["href"] if external_el and external_el.get("href") else album["album_page_url"]

        review_id = None
        menu_btn = row.select_one("button.criticReviewMenuToggle")
        if menu_btn and menu_btn.get("data-review-id"):
            review_id = menu_btn["data-review-id"]

        reviewed_at = _parse_critic_date(row)
        if reviewed_at is None:
            reviewed_at = date_parser.parse(album["release_date"]).replace(tzinfo=timezone.utc)

        critic_key = review_id or re.sub(r"[^a-z0-9]+", "-", (publication or "unknown").lower())
        item = make_aoty_item(
            item_id=f"aoty:critic:{album_slug}:{critic_key}",
            text=text,
            timestamp=reviewed_at,
            url=external_url,
            author_id=author,
            score=float(score) if score is not None else None,
            metadata={
                "review_type": "critic",
                "album_id": album_id,
                "album_slug": album_slug,
                "album_title": album["title"],
                "artist": album["artist"],
                "publication": publication,
                "review_id": review_id,
            },
        )
        items.append(tag_item(item))

    return items


def parse_user_rated_albums(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Extract album ratings from an AOTY user profile page."""
    albums: list[dict[str, Any]] = []
    seen: set[int] = set()

    for row in soup.select(".ratingRow, .userRatingRow, tr[data-album-id]"):
        link = row.select_one("a[href*='/album/']")
        if not link:
            continue
        href = link.get("href", "")
        match = re.search(r"/album/(\d+)-([^/.]+)", href)
        if not match:
            continue
        album_id = int(match.group(1))
        if album_id in seen:
            continue
        seen.add(album_id)

        title_el = row.select_one(".albumTitle, .title, a[href*='/album/']")
        rating_el = row.select_one(".rating, .ratingBlock .rating, .userRating")
        score = None
        if rating_el:
            score_match = re.search(r"\d+", rating_el.get_text(strip=True))
            score = int(score_match.group()) if score_match else None

        albums.append(
            {
                "album_id": album_id,
                "slug": match.group(2),
                "title": title_el.get_text(strip=True) if title_el else match.group(2),
                "score": score,
                "url": urljoin(AOTY_BASE_URL, href),
            }
        )

    if albums:
        return albums

    for link in soup.select("a[href*='/album/'][href$='.php']"):
        href = link.get("href", "")
        if "/user/" in href:
            continue
        match = re.search(r"/album/(\d+)-([^/.]+)\.php", href)
        if not match:
            continue
        album_id = int(match.group(1))
        if album_id in seen:
            continue
        seen.add(album_id)
        albums.append(
            {
                "album_id": album_id,
                "slug": match.group(2),
                "title": link.get_text(strip=True) or match.group(2),
                "score": None,
                "url": urljoin(AOTY_BASE_URL, href),
            }
        )
    return albums


def fetch_user_rated_albums(
    session: curl_requests.Session,
    username: str,
    *,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
) -> list[dict[str, Any]]:
    url = f"{AOTY_BASE_URL}/user/{username}/"
    time.sleep(delay_seconds)
    html = fetch_html(session, url)
    return parse_user_rated_albums(BeautifulSoup(html, "lxml"))


def snowball_albums_from_users(
    usernames: list[str],
    *,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    exclude_album_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Count how often seed-scene reviewers rated each album elsewhere on AOTY."""
    exclude = exclude_album_ids or set()
    session = _session()
    counts: Counter[int] = Counter()
    album_meta: dict[int, dict[str, Any]] = {}

    for index, username in enumerate(usernames):
        if index:
            time.sleep(delay_seconds)
        try:
            rated = fetch_user_rated_albums(session, username, delay_seconds=0)
        except Exception:
            continue
        for entry in rated:
            album_id = entry["album_id"]
            if album_id in exclude:
                continue
            counts[album_id] += 1
            album_meta.setdefault(album_id, entry)

    ranked = []
    for album_id, user_count in counts.most_common():
        ranked.append({**album_meta[album_id], "overlap_users": user_count})
    return ranked


def collect_album(
    session: curl_requests.Session,
    album: dict[str, Any],
    *,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    fetch_exact_dates: bool = True,
) -> dict[str, Any]:
    output_dir = AOTY_RAW_DIR / album["id"]
    output_dir.mkdir(parents=True, exist_ok=True)

    user_reviews = collect_user_reviews(
        session,
        album,
        delay_seconds=delay_seconds,
        output_dir=output_dir,
        fetch_exact_dates=fetch_exact_dates,
    )
    time.sleep(delay_seconds)

    critic_reviews = collect_critic_reviews(session, album)
    album_html = fetch_html(session, album["album_page_url"])
    album_meta = _parse_album_scores(BeautifulSoup(album_html, "lxml"))
    album_meta.update(
        {
            "album_id": album["album_id"],
            "album_slug": album["id"],
            "album_title": album["title"],
            "artist": album["artist"],
            "user_review_count_collected": len(user_reviews),
            "critic_review_count_collected": len(critic_reviews),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    user_path = output_dir / "user_reviews.json"
    critic_path = output_dir / "critic_reviews.json"
    meta_path = output_dir / "album_meta.json"

    with user_path.open("w", encoding="utf-8") as handle:
        json.dump([item.to_dict() for item in user_reviews], handle, indent=2, ensure_ascii=False)

    with critic_path.open("w", encoding="utf-8") as handle:
        json.dump([item.to_dict() for item in critic_reviews], handle, indent=2, ensure_ascii=False)

    with meta_path.open("w", encoding="utf-8") as handle:
        json.dump(album_meta, handle, indent=2, ensure_ascii=False)

    return {
        "album": album["id"],
        "user_reviews": user_reviews,
        "critic_reviews": critic_reviews,
        "album_meta": album_meta,
        "output_dir": output_dir,
    }


def collect_aoty(
    *,
    manifest_path: Path = AOTY_MANIFEST,
    album_ids: list[str] | None = None,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    fetch_exact_dates: bool = True,
    skip_album_ids: list[str] | None = None,
) -> dict[str, Any]:
    AOTY_RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(manifest_path)
    if album_ids:
        manifest = [album for album in manifest if album["id"] in album_ids]
    if skip_album_ids:
        skip = set(skip_album_ids)
        manifest = [album for album in manifest if album["id"] not in skip]

    session = _session()
    results: dict[str, Any] = {}
    all_reviews: list[BenchmarkItem] = []

    for index, album in enumerate(manifest):
        if index:
            time.sleep(delay_seconds)
        result = collect_album(
            session,
            album,
            delay_seconds=delay_seconds,
            fetch_exact_dates=fetch_exact_dates,
        )
        results[album["id"]] = result
        all_reviews.extend(result["user_reviews"])
        all_reviews.extend(result["critic_reviews"])

    combined_path = AOTY_RAW_DIR / "all_aoty_reviews.json"
    with combined_path.open("w", encoding="utf-8") as handle:
        json.dump([item.to_dict() for item in all_reviews], handle, indent=2, ensure_ascii=False)

    return {
        "results": results,
        "all_reviews": all_reviews,
        "combined_path": combined_path,
    }


def summarize_collection(results: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for album_id, result in results["results"].items():
        user_reviews: list[BenchmarkItem] = result["user_reviews"]
        split_counts = {"training": 0, "test": 0}
        scores: list[float] = []
        for review in user_reviews:
            split_counts[review.split or "untagged"] += 1
            if review.score is not None:
                scores.append(review.score)

        mean_score = round(sum(scores) / len(scores), 1) if scores else None
        summary[album_id] = {
            "user_review_count": len(user_reviews),
            "critic_review_count": len(result["critic_reviews"]),
            "split_counts": split_counts,
            "mean_user_score": mean_score,
            "album_meta": result["album_meta"],
        }
    return summary
