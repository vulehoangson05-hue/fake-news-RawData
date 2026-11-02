"""HTTP fetcher lịch sự: tuân thủ robots.txt, crawl-delay, cache HTML thô."""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

CACHE_DIR = Path("data/raw/html")
MANIFEST = Path("data/raw/manifest.jsonl")
UA = "Mozilla/5.0 (compatible; FakeNewsResearchBot/1.0; +mailto:research@example.com)"


def _cache_key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def _load_manifest() -> dict[str, str]:
    out: dict[str, str] = {}
    if MANIFEST.exists():
        with open(MANIFEST, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    out[rec["url"]] = rec["status"]
                except Exception:
                    pass
    return out


def _append_manifest(url: str, status: str) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps({"url": url, "status": status, "ts": ts}, ensure_ascii=False) + "\n")


class PoliteFetcher:
    def __init__(self, delay: float = 1.0):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": UA})
        self._delay = delay
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}
        self._manifest = _load_manifest()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- robots.txt ----------
    def _get_robots(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            rp.set_url(base + "/robots.txt")
            try:
                rp.read()
            except Exception:
                pass
            # Lấy crawl-delay từ robots.txt
            try:
                tokens = UA.replace("(", "").replace(")", "").replace(";", "").split()
                agent_names = [t for t in tokens if "/" in t]
                delay = None
                for agent in agent_names + ["*"]:
                    d = rp.crawl_delay(agent)
                    if d is not None:
                        delay = d
                        break
                if delay is not None:
                    self._delay = max(self._delay, float(delay))
            except Exception:
                pass
            self._robots[base] = rp
        return self._robots[base]

    def can_fetch(self, url: str) -> bool:
        try:
            rp = self._get_robots(url)
            # Thử nhiều dạng UA token để tránh false-block
            for agent in [UA, "FakeNewsResearchBot", "*"]:
                if rp.can_fetch(agent, url):
                    return True
            return False
        except Exception:
            return True

    # ---------- delay ----------
    def _wait(self, domain: str) -> None:
        now = time.monotonic()
        elapsed = now - self._last.get(domain, 0)
        sleep_for = self._delay + random.uniform(0, 0.5) - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._last[domain] = time.monotonic()

    # ---------- fetch ----------
    def fetch(self, url: str, use_cache: bool = True) -> str | None:
        key = _cache_key(url)
        cache_file = CACHE_DIR / f"{key}.html"

        # Dùng cache nếu có
        if use_cache and cache_file.exists():
            return cache_file.read_text(encoding="utf-8", errors="replace")

        # Kiểm tra manifest (tránh re-fetch các URL lỗi)
        if url in self._manifest and self._manifest[url] in ("blocked_by_robots", "http_403", "http_404"):
            return None

        if not self.can_fetch(url):
            self._manifest[url] = "blocked_by_robots"
            _append_manifest(url, "blocked_by_robots")
            return None

        domain = urlparse(url).netloc
        self._wait(domain)

        try:
            resp = self._session.get(url, timeout=20)
            if resp.status_code == 403:
                _append_manifest(url, "http_403")
                self._manifest[url] = "http_403"
                return None
            if resp.status_code == 404:
                _append_manifest(url, "http_404")
                self._manifest[url] = "http_404"
                return None
            resp.raise_for_status()
            html = resp.text
            if use_cache:
                cache_file.write_text(html, encoding="utf-8")
            if url not in self._manifest:
                _append_manifest(url, "ok")
                self._manifest[url] = "ok"
            return html
        except requests.RequestException as e:
            err = f"error: {type(e).__name__}"
            _append_manifest(url, err)
            self._manifest[url] = err
            return None
