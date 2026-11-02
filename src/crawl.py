"""Thu thập bài báo từ các nguồn đã cấu hình trong config/sources.yaml."""
from __future__ import annotations

import argparse
import io
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import sys
import io

# Buộc stdout/stderr dùng UTF-8 (Windows)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import yaml
from bs4 import BeautifulSoup
import trafilatura

from .common import Record, domain_of, make_id, normalize_text, read_jsonl, write_jsonl
from .fetcher import PoliteFetcher

CONFIG = Path("config/sources.yaml")
PARSED_DIR = Path("data/parsed")


# ─────────────────────────── helpers ────────────────────────────────────────

def urls_from_sitemap(fetcher: PoliteFetcher, sitemap_url: str,
                      article_regex: str | None, visited: set[str]) -> list[str]:
    """Đệ quy parse sitemap index + sitemap thường."""
    html = fetcher.fetch(sitemap_url)
    if not html:
        return []
    urls = []
    soup = BeautifulSoup(html, "xml")
    # Sitemap index: chứa <sitemap><loc>…</loc></sitemap>
    for sm in soup.find_all("sitemap"):
        loc = sm.find("loc")
        if loc:
            child_url = loc.text.strip()
            if child_url not in visited:
                visited.add(child_url)
                urls += urls_from_sitemap(fetcher, child_url, article_regex, visited)
    # Sitemap thường: chứa <url><loc>…</loc></url>
    pat = re.compile(article_regex) if article_regex else None
    for u in soup.find_all("url"):
        loc = u.find("loc")
        if not loc:
            continue
        link = loc.text.strip()
        if pat and not pat.search(link):
            continue
        urls.append(link)
    return urls


def urls_from_listing(fetcher: PoliteFetcher, base_url: str,
                       pages: list[int], article_regex: str | None) -> list[str]:
    """Lấy link bài viết từ các trang danh sách có phân trang."""
    pat = re.compile(article_regex) if article_regex else None
    urls = []
    start, end = (pages[0], pages[1]) if len(pages) == 2 else (1, pages[0])
    for page in range(start, end + 1):
        if "{page}" in base_url:
            page_url = base_url.replace("{page}", str(page))
        elif base_url.endswith("/"):
            page_url = f"{base_url}p{page}"
        else:
            page_url = f"{base_url}/p{page}"
        html = fetcher.fetch(page_url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            full = urljoin(page_url, href)
            if pat and not pat.search(full):
                continue
            urls.append(full)
    return list(dict.fromkeys(urls))  # dedupe, giữ thứ tự


def parse_article(html: str, url: str) -> tuple[str, str]:
    """Trả về (title, text) đã làm sạch."""
    title = ""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1:
        title = normalize_text(h1.get_text())
    text = trafilatura.extract(html, include_comments=False,
                               include_tables=False, no_fallback=False) or ""
    return title, normalize_text(text)


# ─────────────────────────── runner ─────────────────────────────────────────

def run_source(fetcher: PoliteFetcher, name: str, src: dict, max_articles: int | None):
    out_path = PARSED_DIR / f"{name}.jsonl"
    done_urls = {r["url"] for r in read_jsonl(out_path)}

    lang = src.get("lang", "vi")
    label = src.get("label", "real")
    role = src.get("role", "article")
    label_source = name
    cap = max_articles or src.get("max_articles")

    # ── Khám phá URL ──
    candidate_urls: list[str] = []
    visited_sitemaps: set[str] = set()

    if "sitemaps" in src:
        for sm_url in src["sitemaps"]:
            candidate_urls += urls_from_sitemap(
                fetcher, sm_url, src.get("article_regex"), visited_sitemaps)

    if "listing_pages" in src:
        for entry in src["listing_pages"]:
            base = entry if isinstance(entry, str) else entry["url"]
            pages = [1, src.get("pages", 1)] if "pages" not in src else src["pages"]
            if isinstance(src.get("listing_pages"), list):
                # pages cấu hình per-source
                pages = src.get("pages", [1, 5])
            candidate_urls += urls_from_listing(
                fetcher, base, pages, src.get("article_regex"))

    candidate_urls = list(dict.fromkeys(candidate_urls))
    print(f"[{name}] {len(candidate_urls)} URL ứng viên, đã parse {len(done_urls)}", flush=True)

    parsed = 0
    records: list[dict] = []

    for url in candidate_urls:
        if url in done_urls:
            continue
        if cap and parsed >= cap:
            break

        html = fetcher.fetch(url)
        if not html:
            continue

        title, text = parse_article(html, url)
        if len(text) < 100:
            continue

        rec = Record(
            id=make_id(url),
            text=text,
            title=title,
            lang=lang,
            label=label,
            label_source=label_source,
            role=role,
            url=url,
            domain=domain_of(url),
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            topic=src.get("topic", ""),
        )
        records.append(rec.to_dict())
        done_urls.add(url)
        parsed += 1

        # Flush mỗi 20 bài để không mất data khi Ctrl+C
        if len(records) >= 20:
            write_jsonl(out_path, records, mode="a")
            records = []

    if records:
        write_jsonl(out_path, records, mode="a")
    print(f"[{name}] xong, +{parsed} bài -> {out_path}", flush=True)


# ─────────────────────────── CLI ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Chạy crawl")
    run_p.add_argument("--only", help="Chỉ chạy nguồn này")
    run_p.add_argument("--max", type=int, help="Số bài tối đa mỗi nguồn")

    sm_p = sub.add_parser("sitemaps", help="In sitemap của một nguồn")
    sm_p.add_argument("source", help="Tên nguồn")

    args = parser.parse_args()

    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    sources: dict = cfg.get("sources", {})
    fetcher = PoliteFetcher(delay=float(cfg.get("default_delay", 1.5)))

    if args.cmd == "sitemaps":
        src = sources.get(args.source, {})
        visited: set[str] = set()
        urls = []
        for sm in src.get("sitemaps", []):
            urls += urls_from_sitemap(fetcher, sm, src.get("article_regex"), visited)
        for u in urls[:50]:
            print(u)
        print(f"… tổng {len(urls)} URL")

    elif args.cmd == "run":
        for name, src in sources.items():
            if not src.get("enabled", False):
                continue
            if args.only and name != args.only:
                continue
            run_source(fetcher, name, src, args.max)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
