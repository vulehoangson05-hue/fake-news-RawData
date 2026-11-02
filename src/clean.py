"""Làm sạch, dedupe và chia tập dữ liệu."""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datasketch import MinHash, MinHashLSH

from .common import normalize_text, read_jsonl, write_jsonl

PARSED_DIR = Path("data/parsed")
CLEAN_FILE = Path("data/clean.jsonl")
SPLITS_DIR = Path("data/splits")

# Regex xóa dấu hiệu nhận diện tên báo
SOURCE_PATTERNS_CI = [
    r"vnexpress\.net", r"vn ?express", r"dantri\.com\.vn", r"dân trí",
    r"tuoitre\.vn", r"tuổi trẻ", r"tingia\.gov\.vn",
    r"\(dân trí\)", r"\(vnexpress\)", r"\(tuổi trẻ\)",
    r"©\s*\d{4}", r"all rights reserved",
]
_PAT = re.compile("|".join(SOURCE_PATTERNS_CI), re.IGNORECASE)


def clean_text(text: str) -> str:
    text = normalize_text(text)
    text = _PAT.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


# ─── MinHash dedupe ───────────────────────────────────────────────────────────

def shingles(text: str, k: int = 5) -> set[str]:
    words = text.split()
    if len(words) < k:
        return {text}
    return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}


def build_minhash(text: str, num_perm: int = 64) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for s in shingles(text):
        m.update(s.encode("utf-8"))
    return m


def dedupe(records: list[dict], threshold: float = 0.85) -> list[dict]:
    lsh = MinHashLSH(threshold=threshold, num_perm=64)
    kept: list[dict] = []
    for i, rec in enumerate(records):
        key = str(i)
        m = build_minhash(rec["text"])
        result = lsh.query(m)
        if not result:
            lsh.insert(key, m)
            kept.append(rec)
    return kept


# ─── Build ───────────────────────────────────────────────────────────────────

def cmd_build(_args):
    all_records: list[dict] = []
    for path in sorted(PARSED_DIR.glob("*.jsonl")):
        rows = read_jsonl(path)
        print(f"  {path.name}: {len(rows)} bài")
        for r in rows:
            r["text"] = clean_text(r.get("text", ""))
            if len(r["text"]) >= 80:
                all_records.append(r)

    print(f"Trước dedupe: {len(all_records)}")
    all_records = dedupe(all_records)
    print(f"Sau dedupe: {len(all_records)}")

    write_jsonl(CLEAN_FILE, all_records)
    print(f"Đã lưu -> {CLEAN_FILE}")

    # Thống kê label
    stats: dict[str, int] = defaultdict(int)
    for r in all_records:
        stats[r.get("label", "?")] += 1
    for lbl, cnt in stats.items():
        print(f"  {lbl}: {cnt}")


# ─── Split ───────────────────────────────────────────────────────────────────

def cmd_split(args):
    records = read_jsonl(CLEAN_FILE)
    if not records:
        print("Chưa có data/clean.jsonl. Chạy build trước.")
        return

    ood_domains: set[str] = set()
    if args.ood_domains:
        ood_domains = {d.strip() for d in args.ood_domains.split(",")}

    ood = [r for r in records if r.get("domain", "") in ood_domains]
    rest = [r for r in records if r.get("domain", "") not in ood_domains]

    import random
    random.seed(42)
    random.shuffle(rest)

    n = len(rest)
    n_train = int(n * 0.7)
    n_val = int(n * 0.15)

    splits = {
        "train": rest[:n_train],
        "val": rest[n_train:n_train + n_val],
        "test": rest[n_train + n_val:],
    }
    if ood:
        splits["ood_test"] = ood

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    for split_name, rows in splits.items():
        path = SPLITS_DIR / f"{split_name}.jsonl"
        write_jsonl(path, rows)
        print(f"  {split_name}: {len(rows)} bài -> {path}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("build", help="Làm sạch + dedupe -> data/clean.jsonl")

    split_p = sub.add_parser("split", help="Chia train/val/test")
    split_p.add_argument("--ood_domains", default="", help="Domain cách nhau bởi dấu phẩy")

    args = parser.parse_args()
    if args.cmd == "build":
        cmd_build(args)
    elif args.cmd == "split":
        cmd_split(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
