"""Trích xuất claim tin giả từ bài debunk bằng Heuristic Regex (offline, không tốn token)."""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from .common import make_id, read_jsonl, write_jsonl

# ─── Các pattern heuristic để trích claim tiếng Việt ─────────────────────────
CLAIM_PATTERNS = [
    # "Thông tin … là sai/không chính xác"
    r'[Tt]h[oô]ng\s+tin\s+"?([^"\.]{15,200})"?\s+(?:là\s+)?(?:sai|không\s+chính\s+xác|không\s+đúng|bịa\s+đặt|thất\s+thiệt)',
    # "Clip/Video … bị cắt ghép/lan truyền sai"
    r'(?:[Cc]lip|[Vv]ideo|[Hh]ình\s+ảnh)\s+"?([^"\.]{15,200})"?\s+(?:bị\s+)?(?:cắt\s+ghép|lan\s+truyền\s+sai|dàn\s+dựng)',
    # Câu phủ định dạng: "Không có chuyện … "
    r'[Kk]h(?:ô|o)ng\s+(?:có\s+chuyện|có\s+việc|phải)\s+"?([^"\.]{15,200})"?',
    # Tin đồn / tin giả / thông tin giả mạo về…
    r'(?:[Tt]in\s+đồn|[Tt]in\s+giả|[Tt]hông\s+tin\s+giả\s+mạo)\s+(?:về|rằng|cho\s+rằng)\s+"?([^"\.]{15,200})"?',
    # "… khẳng định/tuyên bố/cho rằng …" trong ngữ cảnh bác bỏ
    r'(?:[Cc]ác\s+tài\s+khoản?|[Mm]ột\s+số\s+trang|[Nn]hiều\s+người)\s+(?:khẳng\s+định|tuyên\s+bố|cho\s+rằng|đăng)\s+"?([^"\.]{20,200})"?',
]

_COMPILED = [re.compile(p, re.UNICODE) for p in CLAIM_PATTERNS]


def extract_claims(text: str) -> list[str]:
    claims = []
    for pat in _COMPILED:
        for m in pat.finditer(text):
            claim = m.group(1).strip().rstrip(".,;:")
            if len(claim) >= 15:
                claims.append(claim)
    return claims


def process_file(input_path: Path, out_path: Path) -> int:
    records = read_jsonl(input_path)
    results = []
    for rec in records:
        text = (rec.get("text") or "") + " " + (rec.get("title") or "")
        claims = extract_claims(text)
        for claim in claims:
            results.append({
                "id": make_id(claim),
                "text": claim,
                "title": "",
                "lang": rec.get("lang", "vi"),
                "label": "fake",
                "label_source": rec.get("label_source", input_path.stem),
                "role": "claim",
                "url": rec.get("url", ""),
                "domain": rec.get("domain", ""),
                "date": rec.get("date", ""),
                "topic": rec.get("topic", ""),
            })
    write_jsonl(out_path, results)
    return len(results)


def main():
    parser = argparse.ArgumentParser(description="Trích xuất claim tin giả từ bài debunk")
    parser.add_argument("--input", required=True, help="File JSONL đầu vào (bài debunk)")
    parser.add_argument("--out", required=True, help="File JSONL đầu ra (claim)")
    args = parser.parse_args()

    n = process_file(Path(args.input), Path(args.out))
    print(f"Đã trích xuất {n} claim -> {args.out}")


if __name__ == "__main__":
    main()
