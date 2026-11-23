#!/usr/bin/env python3
"""Validate claims/claims.csv: header, duplicate ids, empty fields and allowed values.

Usage:
    python scripts/validate_claims.py
Exit code 1 when there are errors that must be fixed.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter

from common import CLAIM_COLUMNS, CLAIM_TYPES, CLAIMS, pdf_keys


def main() -> int:
    if not CLAIMS.exists():
        print("claims/claims.csv does not exist")
        return 1
    errors, warnings, rows = [], [], []
    with CLAIMS.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        if header != CLAIM_COLUMNS:
            errors.append(f"Wrong header.\n    Expected: {','.join(CLAIM_COLUMNS)}\n    Found:    {','.join(header)}")
        for n, row in enumerate(reader, 2):
            if not any(c.strip() for c in row):
                continue
            if len(row) != len(CLAIM_COLUMNS):
                errors.append(f"Line {n}: {len(row)} columns instead of {len(CLAIM_COLUMNS)} "
                              f"(unquoted comma?) -> {','.join(row)[:90]}")
                continue
            rows.append((n, dict(zip(CLAIM_COLUMNS, row))))

    pdfs = pdf_keys()
    for cid, count in Counter(r["id"] for _, r in rows).items():
        if count > 1:
            errors.append(f"Duplicate id: {cid} ({count} times)")
    for n, r in rows:
        if not re.fullmatch(r"C\d{3,}", r["id"]):
            errors.append(f"Line {n}: id '{r['id']}' is not in the C001 format")
        for field in ("paper_key", "claim"):
            if not r[field].strip():
                errors.append(f"Line {n} ({r['id']}): '{field}' is empty")
        if r["type"] and r["type"] not in CLAIM_TYPES:
            errors.append(f"Line {n} ({r['id']}): type '{r['type']}' is not one of {sorted(CLAIM_TYPES)}")
        if r["multiple_citation"] and r["multiple_citation"] not in ("yes", "no"):
            errors.append(f"Line {n} ({r['id']}): multiple_citation must be 'yes' or 'no'")
        if r["paper_key"] and r["paper_key"] not in pdfs:
            warnings.append(f"{r['id']}: no PDF for '{r['paper_key']}' (it will show as NO PDF)")

    for e in errors:
        print(f"[ERROR] {e}")
    for w in sorted(set(warnings)):
        print(f"[warning] {w}")
    print(f"{len(rows)} claims read, {len(errors)} errors, {len(set(warnings))} warnings.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
