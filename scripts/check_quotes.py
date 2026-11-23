#!/usr/bin/env python3
"""Check, WITHOUT AI, that every verbatim quote returned by the verifier exists in the PDF.

This is the safety net against invented evidence: if the AI says "the paper says X on p. 4",
this script looks for X in extracted/papers/<key>.txt and records in results/<key>.json:
    exact      found as is (after normalizing whitespace, hyphens and quote marks)
    close      >= 90 % match (minor PDF extraction differences)
    doubtful   70-90 %: check by hand
    not_found  < 70 %: treat as INVENTED evidence
It also flags quotes found on a different page than the one stated.

Usage:
    python scripts/check_quotes.py              # every result file
    python scripts/check_quotes.py smith2020    # one or more papers
Exit code 1 if any quote is not found (the verifier uses it to correct itself).
"""
from __future__ import annotations

import sys
from datetime import datetime

from common import RESULTS, normalize, read_pages, read_result, write_json

try:
    from rapidfuzz import fuzz  # optional, improves approximate matching
except ImportError:
    fuzz = None

CLOSE, DOUBTFUL = 90, 70
JOIN_CHARS = 1500  # characters taken from each side of a page break


def ngrams(words: list[str], n: int) -> set:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def similarity(quote: str, text: str) -> float:
    words = quote.split()
    n = 3 if len(words) >= 6 else 2 if len(words) >= 3 else 1
    q = ngrams(words, n)
    if not q:
        return 0.0
    score = 100 * len(q & ngrams(text.split(), n)) / len(q)
    if fuzz is not None and score < CLOSE:
        score = max(score, fuzz.partial_ratio(quote, text))
    return score


def find_fragment(fragment: str, pages: list[tuple[int, str]]) -> dict:
    norm = [(n, normalize(t)) for n, t in pages]
    # Page-break zones, for quotes that start on one page and end on the next
    joins = [(norm[i][0], f"{norm[i][1][-JOIN_CHARS:]} {norm[i + 1][1][:JOIN_CHARS]}") for i in range(len(norm) - 1)]

    # 1) exact match: each page alone first, then the page breaks
    for zones in (norm, joins):
        for num, text in zones:
            if fragment in text:
                return {"status": "exact", "found_page": num, "similarity": 100.0}

    # 2) approximate match, same priority (a page break only wins when clearly better)
    best_page, best = None, 0.0
    for num, text in norm:
        s = similarity(fragment, text)
        if s > best:
            best_page, best = num, s
    for num, text in joins:
        s = similarity(fragment, text)
        if s > best + 5:
            best_page, best = num, s
    status = "close" if best >= CLOSE else "doubtful" if best >= DOUBTFUL else "not_found"
    return {"status": status, "found_page": best_page if status != "not_found" else None, "similarity": round(best, 1)}


def find_quote(quote: str, pages: list[tuple[int, str]]) -> dict:
    """Locate a quote; quotes glued with '...' are checked piece by piece (worst piece wins)."""
    fragments = [f.strip(" \"'") for f in normalize(quote).split("...")]
    fragments = [f for f in fragments if len(f.split()) >= 3] or [normalize(quote).strip(" \"'")]
    result = min((find_fragment(f, pages) for f in fragments), key=lambda r: r["similarity"])
    if len(fragments) > 1:
        result["note"] = "The quote joins fragments with '...'; each one was checked separately."
    return result


def check_paper(key: str) -> tuple[int, list[str]]:
    data = read_result(key)
    if data is None:
        print(f"  {key}: no results/{key}.json")
        return 0, []
    pages = read_pages(key)
    if not pages:
        print(f"  {key}: extracted/papers/{key}.txt is missing (run extract_papers.py)")
        return 0, []

    counts = {"exact": 0, "close": 0, "doubtful": 0, "not_found": 0}
    problems = []
    for r in data.get("results", []):
        verified = False
        for ev in r.get("evidence", []) or []:
            quote = (ev.get("quote") or "").strip()
            if not quote:
                continue
            check = find_quote(quote, pages)
            stated = ev.get("page")
            if check["found_page"] and stated and str(stated) != str(check["found_page"]):
                check["page_warning"] = {"stated": stated, "found": check["found_page"]}
            ev["check"] = check
            counts[check["status"]] += 1
            verified = verified or check["status"] in ("exact", "close")
            if check["status"] in ("not_found", "doubtful"):
                problems.append(f"{r.get('claim_id')}: [{check['status']}] \"{quote[:80]}...\"")
        r["evidence_verified"] = verified
    data["checked_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(RESULTS / f"{key}.json", data)

    summary = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    print(f"  {key}: {sum(counts.values())} verbatim quotes -> {summary or 'none'}")
    return counts["not_found"], problems


def main() -> int:
    keys = sys.argv[1:] or sorted(p.stem for p in RESULTS.glob("*.json"))
    if not keys:
        print("No results to check yet.")
        return 0
    print("Checking verbatim quotes against the PDF text:")
    missing, problems = 0, []
    for key in keys:
        n, p = check_paper(key)
        missing += n
        problems += [f"{key} / {x}" for x in p]
    if problems:
        print("\nQuotes to review (possibly invented or miscopied evidence):")
        for p in problems:
            print(f"  - {p}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
