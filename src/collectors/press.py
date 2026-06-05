"""Press article fetcher."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from readability import Document

from config.settings import PRESS_MANIFEST, PRESS_RAW_DIR, USER_AGENT
from src.benchmark.schema import BenchmarkItem, make_press_item
from src.benchmark.temporal import tag_item

REQUEST_DELAY_SECONDS = 1.0


def load_manifest(path: Path = PRESS_MANIFEST) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return session


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return _clean_text(og_title["content"])
    if soup.title and soup.title.string:
        return _clean_text(soup.title.string)
    return fallback


def _extract_published_date(soup: BeautifulSoup, fallback: str) -> datetime:
    candidates: list[str] = []
    for key in ("article:published_time", "og:updated_time", "datePublished"):
        tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            candidates.append(tag["content"])

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for key in ("datePublished", "dateModified", "uploadDate"):
                if node.get(key):
                    candidates.append(node[key])

    time_tag = soup.find("time")
    if time_tag:
        if time_tag.get("datetime"):
            candidates.append(time_tag["datetime"])
        elif time_tag.string:
            candidates.append(time_tag.string.strip())

    for candidate in candidates:
        try:
            return date_parser.parse(candidate).astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            continue

    return date_parser.parse(fallback).replace(tzinfo=timezone.utc)


def _extract_author(soup: BeautifulSoup) -> str | None:
    for key in ("author", "article:author"):
        tag = soup.find("meta", property=key) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return _clean_text(tag["content"])

    byline = soup.find(class_=re.compile(r"author|byline", re.I))
    if byline:
        return _clean_text(byline.get_text(" ", strip=True))

    return None


def _extract_full_article(soup: BeautifulSoup) -> str:
    article = soup.find("article") or soup.select_one("main") or soup
    paragraphs = [
        _clean_text(p.get_text(" ", strip=True))
        for p in article.find_all("p")
        if len(p.get_text(" ", strip=True).split()) >= 8
    ]
    return _clean_text("\n\n".join(paragraphs))


def _extract_section_by_heading(soup: BeautifulSoup, heading: str) -> str:
    target = heading.casefold()
    nodes = soup.find("article") or soup.select_one("main") or soup
    capture = False
    chunks: list[str] = []

    for element in nodes.find_all(["h2", "h3", "h4", "p", "li"]):
        if element.name in {"h2", "h3", "h4"}:
            label = _clean_text(element.get_text(" ", strip=True))
            if label.casefold() == target:
                capture = True
                chunks.append(label)
                continue
            if capture:
                break
        elif capture:
            text = _clean_text(element.get_text(" ", strip=True))
            if text:
                chunks.append(text)

    return _clean_text("\n\n".join(chunks))


def _paragraph_text(element) -> str:
    return _clean_text(element.get_text(" ", strip=True))


def _extract_mention_block(soup: BeautifulSoup, keyword: str) -> str:
    nodes = soup.find("article") or soup.select_one("main") or soup
    paragraphs = [p for p in nodes.find_all("p") if _paragraph_text(p)]
    if not paragraphs:
        return ""

    needle = keyword.casefold()
    anchor_index = next(
        (index for index, paragraph in enumerate(paragraphs) if needle in _paragraph_text(paragraph).casefold()),
        None,
    )
    if anchor_index is None:
        return ""

    start = anchor_index
    while start > 0:
        previous = _paragraph_text(paragraphs[start - 1])
        if previous.casefold().startswith("who :") and needle not in previous.casefold():
            start -= 1
            break
        if previous.casefold().startswith("who :"):
            start -= 1
            continue
        if any(marker in previous.casefold() for marker in ("who :", "what :", "where")):
            start -= 1
            continue
        break

    end = anchor_index
    while end + 1 < len(paragraphs):
        nxt = _paragraph_text(paragraphs[end + 1])
        if nxt.casefold().startswith("who :") and needle not in nxt.casefold():
            break
        if nxt.casefold().startswith("who :") and end + 1 > anchor_index:
            break
        end += 1

    return _clean_text("\n\n".join(_paragraph_text(paragraphs[i]) for i in range(start, end + 1)))


def _extract_body(html: str, soup: BeautifulSoup, entry: dict[str, Any]) -> str:
    extract_mode = entry.get("extract_mode", "readability")

    if extract_mode == "mention_block" and entry.get("mention_keyword"):
        block = _extract_mention_block(soup, entry["mention_keyword"])
        if len(block.split()) >= 20:
            return block

    if extract_mode == "section_heading" and entry.get("section_heading"):
        section = _extract_section_by_heading(soup, entry["section_heading"])
        if len(section.split()) >= 30:
            return section

    if extract_mode == "full_article":
        full = _extract_full_article(soup)
        if len(full.split()) >= 80:
            return full

    doc = Document(html)
    article_html = doc.summary(html_partial=True)
    article_soup = BeautifulSoup(article_html, "lxml")
    text = article_soup.get_text("\n", strip=True)
    if len(text.split()) >= 80:
        return _clean_text(text)

    selectors = [
        "article",
        "[data-component='text-block']",
        ".article-body",
        ".article__body",
        ".article-content",
        ".post-content",
        ".entry-content",
        ".body",
        "main",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        candidate = _clean_text(node.get_text("\n", strip=True))
        if len(candidate.split()) >= 80:
            return candidate

    full = _extract_full_article(soup)
    if len(full.split()) >= 50:
        return full

    return _clean_text(doc.summary())


def fetch_article(entry: dict[str, Any], session: requests.Session) -> BenchmarkItem:
    response = session.get(entry["url"], timeout=30)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup, entry["title"])
    published = _extract_published_date(soup, entry["published_date"])
    author = _extract_author(soup)
    body = _extract_body(html, soup, entry)

    if len(body.split()) < 50:
        raise ValueError(f"Extracted body too short for {entry['id']} ({len(body.split())} words)")

    metadata = {
        "title": title,
        "outlet": entry["source"],
        "article_type": entry.get("article_type"),
        "extract_mode": entry.get("extract_mode"),
        "manifest_published_date": entry["published_date"],
        "word_count": len(body.split()),
        "hostname": urlparse(entry["url"]).netloc,
    }
    if entry.get("score") is not None:
        metadata["critic_score"] = entry["score"]

    item = make_press_item(
        item_id=f"press:{entry['id']}",
        text=body,
        timestamp=published,
        url=entry["url"],
        author_id=author,
        score=entry.get("score"),
        metadata=metadata,
    )
    return tag_item(item)


def collect_press(
    *,
    manifest_path: Path = PRESS_MANIFEST,
    output_dir: Path = PRESS_RAW_DIR,
    delay_seconds: float = REQUEST_DELAY_SECONDS,
) -> list[BenchmarkItem]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(manifest_path)
    session = _session()
    items: list[BenchmarkItem] = []
    failures: list[tuple[str, str]] = []

    for index, entry in enumerate(manifest):
        if index:
            time.sleep(delay_seconds)

        try:
            item = fetch_article(entry, session)
        except Exception as exc:  # noqa: BLE001 — collect all failures, report at end
            failures.append((entry["id"], str(exc)))
            continue

        items.append(item)

        item_path = output_dir / f"{entry['id']}.json"
        with item_path.open("w", encoding="utf-8") as handle:
            json.dump(item.to_dict(), handle, indent=2, ensure_ascii=False)

    if items:
        combined_path = output_dir / "all_press.json"
        with combined_path.open("w", encoding="utf-8") as handle:
            json.dump([item.to_dict() for item in items], handle, indent=2, ensure_ascii=False)

    if failures:
        failed_lines = "\n".join(f"  - {item_id}: {message}" for item_id, message in failures)
        raise RuntimeError(f"Failed to collect {len(failures)} article(s):\n{failed_lines}")

    return items
