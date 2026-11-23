#!/usr/bin/env python3
"""Show where the verification of each paper stands.

Usage:
    python scripts/status.py             # full table
    python scripts/status.py --pending   # only print the pending keys (one per line)
"""
from __future__ import annotations

import sys
from collections import Counter

from common import pdf_keys, read_claims, read_manifest, read_result


def paper_states() -> list[tuple[str, int, str]]:
    claims = read_claims()
    per_paper = Counter((c.get("paper_key") or "").strip() for c in claims)
    pdfs = pdf_keys()
    manifest = read_manifest()

    rows = []
    for key in sorted((set(per_paper) | pdfs) - {""}):
        res = read_result(key)
        done = {r.get("claim_id") for r in (res or {}).get("results", [])}
        ids = {c["id"] for c in claims if (c.get("paper_key") or "").strip() == key}
        missing = ids - done
        if key not in pdfs:
            state = "no_pdf"
        elif manifest.get(key, {}).get("scanned"):
            state = "needs_ocr"
        elif not ids:
            state = "not_cited"
        elif res is None:
            state = "pending"
        elif missing:
            state = f"incomplete ({len(missing)} new)"
        elif "checked_at" not in res:
            state = "quotes_not_checked"
        else:
            state = "verified"
        rows.append((key, len(ids), state))
    return rows


def main() -> int:
    rows = paper_states()
    if "--pending" in sys.argv:
        print("\n".join(k for k, _, s in rows if s == "pending" or s.startswith("incomplete")))
        return 0
    if not rows:
        print("No papers or claims yet. Start with /cite-init.")
        return 0
    width = max(len(r[0]) for r in rows)
    print(f"{'paper':<{width}}  claims  state")
    print("-" * (width + 30))
    for key, n, state in rows:
        print(f"{key:<{width}}  {n:>6}  {state}")
    counts = Counter(r[2].split(" (")[0] for r in rows)
    print("\n" + ", ".join(f"{n} {s}" for s, n in counts.most_common()))
    no_pdf = [r[0] for r in rows if r[2] == "no_pdf"]
    if no_pdf:
        print(f"[!] Cited in the thesis but not found in the papers folder: {', '.join(no_pdf)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
