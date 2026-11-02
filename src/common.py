"""Kiểu dữ liệu và hàm dùng chung."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Record:
    id: str
    text: str
    title: str
    lang: str
    label: str
    label_source: str
    role: str
    url: str
    domain: str
    date: str
    topic: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def make_id(url: str) -> str:
    return sha1(url.encode()).hexdigest()[:16]


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def write_jsonl(path: Path | str, rows: list[dict], mode: str = "w") -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)
