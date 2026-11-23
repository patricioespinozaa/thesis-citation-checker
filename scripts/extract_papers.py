#!/usr/bin/env python3
"""Extract the text of every PDF in the papers folder (and its subfolders) to extracted/papers/<key>.txt.

The papers folder is set in config.json (`papers_dir`, default: papers/). It can be anywhere on disk,
and your files keep their names: each one gets a key derived from its file name
("Smith et al 2020.pdf" -> smith_et_al_2020). The keys are listed in claims/papers.csv.
Scanned PDFs (no text layer) are flagged so they can be OCR'd first.

Usage:
    python scripts/extract_papers.py            # only new or modified PDFs
    python scripts/extract_papers.py --force    # re-extract everything
"""
from __future__ import annotations

import csv
import sys

from common import (INDEX_COLUMNS, PAPER_INDEX, PAPER_TEXT, PAPERS_MANIFEST, list_pdfs, papers_dir,
                    read_csv, write_json)

MIN_CHARS_PER_PAGE = 200  # below this on average => probably scanned


def extract_pages(pdf) -> list[str]:
    try:
        import fitz  # PyMuPDF: better quality, used when installed

        with fitz.open(pdf) as doc:
            return [page.get_text("text") for page in doc]
    except ImportError:
        from pypdf import PdfReader

        return [page.extract_text() or "" for page in PdfReader(str(pdf)).pages]


def update_index(entries: list[dict]) -> None:
    """Keep claims/papers.csv in sync: add new papers, refresh file/folder, keep the user's metadata."""
    rows = {r["key"]: r for r in read_csv(PAPER_INDEX)}
    for e in entries:
        row = rows.setdefault(e["key"], {c: "" for c in INDEX_COLUMNS} | {"key": e["key"]})
        row["file"], row["folder"] = e["file"], e["folder"]
    PAPER_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with PAPER_INDEX.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r.get("folder", ""), r["key"])))


def main() -> int:
    force = "--force" in sys.argv
    folder = papers_dir()
    pdfs = list_pdfs(folder)
    print(f"Papers folder: {folder}")
    if not pdfs:
        print("No PDFs found there (subfolders included). Pick the folder in the viewer or set papers_dir in config.json.")
        return 1
    PAPER_TEXT.mkdir(parents=True, exist_ok=True)

    manifest, warnings = [], []
    for e in pdfs:
        key, pdf = e["key"], e["path"]
        target = PAPER_TEXT / f"{key}.txt"
        if target.exists() and not force and target.stat().st_mtime >= pdf.stat().st_mtime:
            text = target.read_text(encoding="utf-8")
            n_pages, chars, state = text.count("=== [p. "), len(text), "cached"
        else:
            try:
                pages = extract_pages(pdf)
            except Exception as ex:  # damaged or protected PDF
                warnings.append(f"Could not read {e['file']}: {ex}")
                continue
            target.write_text("".join(f"=== [p. {i}] ===\n{t.strip()}\n\n" for i, t in enumerate(pages, 1)),
                              encoding="utf-8")
            n_pages, chars, state = len(pages), sum(len(t) for t in pages), "extracted"

        scanned = n_pages > 0 and chars / n_pages < MIN_CHARS_PER_PAGE
        if scanned:
            warnings.append(f"{e['file']}: almost no text ({chars} characters in {n_pages} pages). "
                            f"Probably scanned -> run OCR on it (see README).")
        manifest.append({"key": key, "file": e["file"], "folder": e["folder"], "pages": n_pages,
                         "chars": chars, "scanned": scanned, "duplicates": e["duplicates"]})
        if e["duplicates"]:
            warnings.append(f"{e['file']} also appears as identical copies: {', '.join(e['duplicates'])} (counted once).")
        print(f"  {state:9}  {key:<40} {e['file']}")

    # Drop texts of PDFs that are no longer in the folder
    keep = {m["key"] for m in manifest}
    for stale in PAPER_TEXT.glob("*.txt"):
        if stale.stem not in keep:
            stale.unlink()
    write_json(PAPERS_MANIFEST, manifest)
    update_index(manifest)
    folders = len({m["folder"] for m in manifest})
    print(f"\n{len(manifest)} papers in {folders} folder(s). Keys listed in claims/papers.csv.")
    for w in warnings:
        print(f"[!] {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
