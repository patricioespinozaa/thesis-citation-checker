#!/usr/bin/env python3
"""Print the thesis claims that cite one paper, as JSON (used by the verifier subagent).

Usage:
    python scripts/claims_for.py smith2020
"""
from __future__ import annotations

import json
import sys

from common import PAPER_TEXT, load_config, read_claims, read_manifest

FIELDS = ["id", "section", "claim", "citation_in_thesis", "cited_page", "type", "multiple_citation", "context"]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/claims_for.py <paper_key>")
        return 2
    key = sys.argv[1]
    claims = [c for c in read_claims() if c.get("paper_key", "").strip() == key]
    if not claims:
        print(f"No claims with paper_key = {key} in claims/claims.csv")
        return 1
    print(json.dumps({
        "paper_key": key,
        "paper_text": f"extracted/papers/{key}.txt",
        "paper_text_exists": (PAPER_TEXT / f"{key}.txt").exists(),
        "pdf_file": read_manifest().get(key, {}).get("file", ""),
        "explanation_language": load_config()["language"],
        "claim_count": len(claims),
        "claims": [{k: c.get(k, "") for k in FIELDS} for c in claims],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
