"""Reddit collector via old.reddit.com HTML scraping (no official API)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from config.settings import REDDIT_MANIFEST, REDDIT_RAW_DIR
from src.benchmark.schema import BenchmarkItem, make_reddit_item
from src.benchmark.temporal import tag_item

OLD_REDDIT_BASE = "https://old.reddit.com"
REQUEST_DELAY_SECONDS = 1.0
MAX_PAGES_PER_SOURCE = 40
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class ScrapedPost:
    post_id: str
    fullname: str
    title: str
    selftext: str
    author: str | None
    score: int | None
    created_utc: float
    permalink: str
    subreddit: str
    num_comments: int
    url: str


@dataclass
class ScrapedComment:
    comment_id: str
    fullname: str
    body: str
    author: str | None
    score: int | None
    created_utc: float
    permalink: str
    parent_fullname: str | None


def load_manifest(path: Path = REDDIT_MANIFEST) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


MAX_RETRIES = 4


class ScrapeError(RuntimeError):
    def __init__(self, url: str, status_code: int | None = None) -> None:
        self.url = url
        self.status_code = status_code
        super().__init__(f"Failed to fetch {url}" + (f" ({status_code})" if status_code else ""))


class OldRedditScraper:
    def __init__(self, *, delay_seconds: float = REQUEST_DELAY_SECONDS) -> None:
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": BROWSER_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def fetch_html(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            if attempt:
                time.sleep(min(30, self.delay_seconds * (2**attempt)))

            time.sleep(self.delay_seconds)
            try:
                response = self.session.get(url, timeout=45)
                if response.status_code in {403, 429, 503}:
                    fallback = curl_requests.get(
                        url,
                        impersonate="chrome120",
                        headers=dict(self.session.headers),
                        timeout=45,
                    )
                    if fallback.status_code == 200:
                        return fallback.text
                    last_error = ScrapeError(url, fallback.status_code)
                    continue
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                continue

        raise ScrapeError(url, getattr(last_error, "status_code", None)) from last_error

    def listing_urls_for_subreddit(self, config: dict[str, Any]) -> list[tuple[str, str]]:
        name = config["name"]
        urls: list[tuple[str, str]] = []

        if config.get("collect_mode") == "all":
            for sort_name in config.get("listing_sorts", ["new"]):
                if sort_name == "top":
                    urls.append(
                        (
                            f"{OLD_REDDIT_BASE}/r/{name}/top/?t={config.get('top_time_filter', 'all')}",
                            f"subreddit:{name}:listing:top",
                        )
                    )
                else:
                    urls.append(
                        (
                            f"{OLD_REDDIT_BASE}/r/{name}/{sort_name}/",
                            f"subreddit:{name}:listing:{sort_name}",
                        )
                    )
        else:
            for query in config.get("queries", []):
                encoded = requests.utils.quote(query)
                urls.append(
                    (
                        f"{OLD_REDDIT_BASE}/r/{name}/search/?q={encoded}&restrict_sr=on&sort=new&t=all",
                        f"subreddit:{name}:search:{query}",
                    )
                )
            for sort_name in config.get("listing_sorts", ["new"]):
                if sort_name == "top":
                    urls.append(
                        (
                            f"{OLD_REDDIT_BASE}/r/{name}/top/?t={config.get('top_time_filter', 'all')}",
                            f"subreddit:{name}:listing:top:filtered",
                        )
                    )
                else:
                    urls.append(
                        (
                            f"{OLD_REDDIT_BASE}/r/{name}/{sort_name}/",
                            f"subreddit:{name}:listing:{sort_name}:filtered",
                        )
                    )
        return urls

    def global_search_urls(self, manifest: dict[str, Any]) -> list[tuple[str, str]]:
        urls: list[tuple[str, str]] = []
        for search in manifest.get("global_searches", []):
            query = search["query"]
            encoded = requests.utils.quote(query)
            urls.append(
                (
                    f"{OLD_REDDIT_BASE}/search?q={encoded}&sort={search.get('sort', 'new')}&t={search.get('time_filter', 'all')}",
                    f"global:search:{query}",
                )
            )
        return urls


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", value.strip())
    return int(match.group()) if match else None


def _reddit_url(path: str) -> str:
    if path.startswith("http"):
        return path
    return urljoin("https://www.reddit.com", path)


def _normalize_text(*parts: str | None) -> str:
    chunks = [part.strip() for part in parts if part and part.strip()]
    return re.sub(r"\s+", " ", "\n\n".join(chunks)).strip()


def _is_relevant(text: str, keywords: list[str]) -> bool:
    lowered = text.casefold()
    return any(keyword.casefold() in lowered for keyword in keywords)


def _utc_from_epoch(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _next_listing_url(soup: BeautifulSoup) -> str | None:
    next_link = soup.select_one("span.next-button a[href]")
    if not next_link or not next_link.get("href"):
        return None
    href = next_link["href"].replace("&amp;", "&")
    if href.startswith("http"):
        return href
    return urljoin(OLD_REDDIT_BASE, href)


def parse_listing_posts(html: str) -> list[ScrapedPost]:
    soup = BeautifulSoup(html, "lxml")
    posts: list[ScrapedPost] = []

    for thing in soup.select("div.thing.link"):
        fullname = thing.get("data-fullname")
        if not fullname or not fullname.startswith("t3_"):
            continue

        title_el = thing.select_one("a.title")
        title = title_el.get_text(" ", strip=True) if title_el else ""

        expando = thing.select_one("div.expando div.usertext-body")
        selftext = expando.get_text(" ", strip=True) if expando else ""

        timestamp_ms = _parse_int(thing.get("data-timestamp"))
        created_utc = timestamp_ms / 1000 if timestamp_ms else 0.0

        permalink = thing.get("data-permalink") or ""
        posts.append(
            ScrapedPost(
                post_id=fullname.removeprefix("t3_"),
                fullname=fullname,
                title=title,
                selftext=selftext,
                author=thing.get("data-author"),
                score=_parse_int(thing.get("data-score")),
                created_utc=created_utc,
                permalink=permalink,
                subreddit=thing.get("data-subreddit") or "",
                num_comments=_parse_int(thing.get("data-comments-count")) or 0,
                url=thing.get("data-url") or "",
            )
        )
    return posts


def parse_thread_page(html: str) -> tuple[str, list[ScrapedComment]]:
    soup = BeautifulSoup(html, "lxml")

    submission = soup.select_one("div.thing.link.id-t3_")
    selftext = ""
    if submission:
        body = submission.select_one("div.usertext-body")
        if body:
            selftext = body.get_text(" ", strip=True)

    comments: list[ScrapedComment] = []
    for thing in soup.select("div.thing.comment"):
        fullname = thing.get("data-fullname")
        if not fullname or not fullname.startswith("t1_"):
            continue

        body_el = thing.select_one("div.usertext-body")
        body = body_el.get_text(" ", strip=True) if body_el else ""
        if not body or body in {"[deleted]", "[removed]"}:
            continue

        timestamp_ms = _parse_int(thing.get("data-timestamp"))
        created_utc = timestamp_ms / 1000 if timestamp_ms else 0.0

        comments.append(
            ScrapedComment(
                comment_id=fullname.removeprefix("t1_"),
                fullname=fullname,
                body=body,
                author=thing.get("data-author"),
                score=_parse_int(thing.get("data-score")),
                created_utc=created_utc,
                permalink=thing.get("data-permalink") or "",
                parent_fullname=thing.get("data-parent"),
            )
        )
    return selftext, comments


def iter_listing_posts(
    scraper: OldRedditScraper,
    start_url: str,
    *,
    max_pages: int = MAX_PAGES_PER_SOURCE,
    max_posts: int = 1000,
) -> Iterable[ScrapedPost]:
    seen_ids: set[str] = set()
    url = start_url

    for _ in range(max_pages):
        try:
            html = scraper.fetch_html(url)
        except ScrapeError:
            break
        posts = parse_listing_posts(html)
        if not posts:
            break

        for post in posts:
            if post.post_id in seen_ids:
                continue
            seen_ids.add(post.post_id)
            yield post
            if len(seen_ids) >= max_posts:
                return

        soup = BeautifulSoup(html, "lxml")
        next_url = _next_listing_url(soup)
        if not next_url or next_url == url:
            break
        url = next_url


def post_to_item(
    post: ScrapedPost,
    *,
    discovery_method: str,
) -> BenchmarkItem | None:
    text = _normalize_text(post.title, post.selftext)
    if not text:
        return None

    item = make_reddit_item(
        item_id=f"reddit:post:{post.post_id}",
        text=text,
        timestamp=_utc_from_epoch(post.created_utc),
        url=_reddit_url(post.permalink),
        author_id=post.author,
        score=float(post.score) if post.score is not None else None,
        metadata={
            "item_type": "post",
            "reddit_id": post.fullname,
            "post_id": post.post_id,
            "subreddit": post.subreddit,
            "title": post.title,
            "discovery_method": discovery_method,
            "num_comments": post.num_comments,
            "external_url": post.url,
        },
    )
    return tag_item(item)


def comment_to_item(
    comment: ScrapedComment,
    *,
    post: ScrapedPost,
    discovery_method: str,
) -> BenchmarkItem:
    item = make_reddit_item(
        item_id=f"reddit:comment:{comment.comment_id}",
        text=comment.body,
        timestamp=_utc_from_epoch(comment.created_utc),
        url=_reddit_url(comment.permalink),
        author_id=comment.author,
        score=float(comment.score) if comment.score is not None else None,
        metadata={
            "item_type": "comment",
            "reddit_id": comment.fullname,
            "comment_id": comment.comment_id,
            "post_id": post.post_id,
            "parent_id": comment.parent_fullname,
            "subreddit": post.subreddit,
            "thread_title": post.title,
            "discovery_method": discovery_method,
        },
    )
    return tag_item(item)


def _load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return set(payload.get("collected_ids", []))


def _save_checkpoint(path: Path, collected_ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"collected_ids": sorted(collected_ids)}, handle, indent=2)


def _load_existing_items(path: Path) -> list[BenchmarkItem]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return [BenchmarkItem.from_dict(entry) for entry in payload]


def collect_reddit(
    *,
    manifest_path: Path = REDDIT_MANIFEST,
    output_dir: Path = REDDIT_RAW_DIR,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
    only_subreddits: list[str] | None = None,
    skip_subreddits: list[str] | None = None,
    include_global_search: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    subreddit_configs = manifest.get("subreddits", [])
    if only_subreddits:
        only = {name.lower() for name in only_subreddits}
        subreddit_configs = [cfg for cfg in subreddit_configs if cfg["name"].lower() in only]
    if skip_subreddits:
        skip = {name.lower() for name in skip_subreddits}
        subreddit_configs = [cfg for cfg in subreddit_configs if cfg["name"].lower() not in skip]
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "checkpoint.json"
    combined_path = output_dir / "all_reddit.json"
    collected_ids = _load_checkpoint(checkpoint_path)

    scraper = OldRedditScraper(delay_seconds=delay_seconds)
    keywords = manifest.get("relevance_keywords", [])
    max_posts = manifest.get("max_submissions_per_source", 1000)
    max_comments = manifest.get("max_comments_per_submission", 200)

    existing_items = {item.id: item for item in _load_existing_items(combined_path)}
    collected_ids |= set(existing_items.keys())
    items: list[BenchmarkItem] = list(existing_items.values())

    posts_seen: set[str] = {
        item.metadata["post_id"]
        for item in items
        if item.metadata.get("post_id") and item.metadata.get("item_type") == "post"
    }
    thread_urls_seen: set[str] = set()

    def store_item(item: BenchmarkItem) -> None:
        if item.id in collected_ids:
            return
        items.append(item)
        collected_ids.add(item.id)
        if len(collected_ids) % 25 == 0:
            _save_checkpoint(checkpoint_path, collected_ids)

    listing_jobs: list[tuple[str, str, bool, int]] = []
    source_errors: list[str] = []
    for subreddit_config in subreddit_configs:
        require_relevance = subreddit_config.get("collect_mode") != "all"
        max_pages = subreddit_config.get("max_pages", MAX_PAGES_PER_SOURCE)
        for url, discovery_method in scraper.listing_urls_for_subreddit(subreddit_config):
            listing_jobs.append((url, discovery_method, require_relevance, max_pages))

    if include_global_search:
        for url, discovery_method in scraper.global_search_urls(manifest):
            listing_jobs.append((url, discovery_method, True, MAX_PAGES_PER_SOURCE))

    for start_url, discovery_method, require_relevance, max_pages in listing_jobs:
        try:
            post_iter = iter_listing_posts(
                scraper,
                start_url,
                max_posts=max_posts,
                max_pages=max_pages,
            )
        except ScrapeError as exc:
            source_errors.append(f"{discovery_method}: {exc}")
            continue

        for post in post_iter:
            if post.post_id in posts_seen:
                continue
            posts_seen.add(post.post_id)

            post_text = _normalize_text(post.title, post.selftext)
            if require_relevance and not _is_relevant(post_text, keywords):
                continue

            if post.num_comments > 0:
                thread_url = urljoin(OLD_REDDIT_BASE, post.permalink)
                if thread_url not in thread_urls_seen:
                    thread_urls_seen.add(thread_url)
                    try:
                        thread_html = scraper.fetch_html(thread_url)
                        thread_selftext, comments = parse_thread_page(thread_html)
                        if thread_selftext:
                            post.selftext = thread_selftext
                        for comment in comments[:max_comments]:
                            store_item(
                                comment_to_item(
                                    comment,
                                    post=post,
                                    discovery_method=f"{discovery_method}:comments",
                                )
                            )
                    except Exception:
                        pass

            post_item = post_to_item(post, discovery_method=discovery_method)
            if post_item:
                store_item(post_item)

    _save_checkpoint(checkpoint_path, collected_ids)

    posts = [item for item in items if item.metadata.get("item_type") == "post"]
    comments = [item for item in items if item.metadata.get("item_type") == "comment"]

    posts_path = output_dir / "posts.json"
    comments_path = output_dir / "comments.json"

    with posts_path.open("w", encoding="utf-8") as handle:
        json.dump([item.to_dict() for item in posts], handle, indent=2, ensure_ascii=False)
    with comments_path.open("w", encoding="utf-8") as handle:
        json.dump([item.to_dict() for item in comments], handle, indent=2, ensure_ascii=False)
    with combined_path.open("w", encoding="utf-8") as handle:
        json.dump([item.to_dict() for item in items], handle, indent=2, ensure_ascii=False)

    summary = summarize_reddit_items(items, submissions_seen=len(posts_seen))
    if source_errors:
        summary["source_errors"] = source_errors
    summary_path = output_dir / "collection_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    return {
        "items": items,
        "posts": posts,
        "comments": comments,
        "summary": summary,
        "combined_path": combined_path,
    }


def summarize_reddit_items(items: Iterable[BenchmarkItem], *, submissions_seen: int) -> dict[str, Any]:
    from collections import Counter

    items = list(items)
    split_counts = Counter(item.split or "untagged" for item in items)
    subreddit_counts = Counter(item.metadata.get("subreddit") for item in items)
    type_counts = Counter(item.metadata.get("item_type") for item in items)

    return {
        "total_items": len(items),
        "submissions_seen": submissions_seen,
        "type_counts": dict(type_counts),
        "split_counts": dict(split_counts),
        "subreddit_counts": dict(subreddit_counts),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scraper": "old.reddit.com HTML",
    }
