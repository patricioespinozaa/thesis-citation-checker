#!/usr/bin/env python3
"""Merge claims/claims.csv + results/*.json into reports/report.xlsx and reports/report.md.

The report language follows config.json (`language`), or --lang en|es.

Usage:
    python scripts/report.py
    python scripts/report.py --lang es
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime

from common import LANGUAGES, PAPER_TEXT, REPORTS, load_config, read_claims, read_result, read_review
from i18n import ACTIONS, TEXT

ACTION_BY_VERDICT = {"correct": "ok", "partial": "improve", "misrepresented": "fix",
                     "not_found": "fix", "unverifiable": "manual"}
FILL = {"ok": "D9F2DC", "improve": "FFF2CC", "fix": "F8D7DA", "manual": "E2E3F3",
        "unverified": "FCE4D6", "pending": "EEEEEE", "no_pdf": "DDDDDD"}


def consolidate() -> list[dict]:
    """One row per claim, joined with its verdict. `action` is a language-neutral code."""
    claims, review = read_claims(), read_review()
    cache: dict[str, dict | None] = {}
    rows = []
    for c in claims:
        key = (c.get("paper_key") or "").strip()
        if key not in cache:
            cache[key] = read_result(key) if key else None
        res = cache[key]
        r = next((x for x in res.get("results", []) if x.get("claim_id") == c["id"]), None) if res else None

        row = {**c, "verdict": "", "confidence": "", "fidelity": None, "severity": "", "error_types": [],
               "secondary_citation": False, "explanation": "", "suggestion": "", "evidence": [],
               "evidence_verified": False, "review": review.get(c["id"])}
        if not key or not (PAPER_TEXT / f"{key}.txt").exists():
            row["action"] = "no_pdf"
        elif r is None:
            row["action"] = "pending"
        else:
            verdict = r.get("verdict", "")
            row.update(
                verdict=verdict, confidence=r.get("confidence", ""), fidelity=r.get("fidelity"),
                severity=r.get("severity", ""), error_types=r.get("error_types") or [],
                secondary_citation=bool(r.get("secondary_citation")), explanation=r.get("explanation", ""),
                suggestion=r.get("suggestion", ""), evidence_verified=bool(r.get("evidence_verified")),
                evidence=[e for e in (r.get("evidence") or []) if e.get("quote")],
            )
            action = ACTION_BY_VERDICT.get(verdict, "manual")
            if verdict in ("correct", "partial") and not row["evidence_verified"]:
                action = "unverified"
            row["action"] = action
        rows.append(row)
    return rows


def check_text(ev: dict, T: dict) -> str:
    check = ev.get("check") or {}
    text = T["check"].get(check.get("status", "unchecked"), check.get("status", ""))
    if check.get("page_warning"):
        text += f" ({T['page_warning'].format(**check['page_warning'])})"
    return text


def flat(row: dict, T: dict) -> dict:
    """Row as plain strings for the spreadsheet."""
    ev = row["evidence"]
    return {
        **row,
        "action": T["action"][row["action"]],
        "verdict": T["verdict"].get(row["verdict"], row["verdict"]),
        "fidelity": "" if row["fidelity"] is None else row["fidelity"],
        "error_types": ", ".join(row["error_types"]),
        "quotes": "\n---\n".join(e["quote"] for e in ev),
        "pages": " | ".join(str(e.get("page", "?")) for e in ev),
        "quote_check": " | ".join(check_text(e, T) for e in ev),
        "secondary_citation": T["yes"] if row["secondary_citation"] else "",
        "your_decision": (row["review"] or {}).get("status", ""),
    }


def write_excel(rows: list[dict], path, T: dict) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    cols = [("id", 8), ("section", 22), ("paper_key", 16), ("action", 18), ("verdict", 14), ("severity", 11),
            ("fidelity", 9), ("error_types", 20), ("confidence", 10), ("claim", 60), ("explanation", 55),
            ("suggestion", 55), ("quotes", 60), ("pages", 9), ("quote_check", 18), ("secondary_citation", 10),
            ("citation_in_thesis", 22), ("paragraph", 9), ("your_decision", 14)]
    header_font, header_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="3B4A6B")
    wrap = Alignment(wrap_text=True, vertical="top")
    wb = Workbook()
    summary = wb.active
    summary.title = T["sheets"]["summary"]

    def sheet(name, data):
        ws = wb.create_sheet(name)
        for j, (c, width) in enumerate(cols, 1):
            cell = ws.cell(row=1, column=j, value=T["columns"][c])
            cell.font, cell.fill = header_font, header_fill
            ws.column_dimensions[get_column_letter(j)].width = width
        for i, row in enumerate(data, 2):
            f = flat(row, T)
            for j, (c, _) in enumerate(cols, 1):
                cell = ws.cell(row=i, column=j, value=f.get(c, ""))
                cell.alignment = wrap
                if c == "action":
                    cell.fill = PatternFill("solid", fgColor=FILL[row["action"]])
                    cell.font = Font(bold=True)
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(len(data) + 1, 2)}"

    sheet(T["sheets"]["problems"], [r for r in rows if r["action"] != "ok"])
    sheet(T["sheets"]["all"], rows)

    summary["A1"] = T["title"]
    summary["A1"].font = Font(bold=True, size=14)
    summary["A2"] = f"{T['generated']}: {datetime.now():%Y-%m-%d %H:%M}"
    summary["A4"], summary["B4"] = T["by_action"], T["claims"]
    summary["A4"].font = summary["B4"].font = Font(bold=True)
    counts = Counter(r["action"] for r in rows)
    line = 5
    for a in ACTIONS:
        if counts[a]:
            summary.cell(row=line, column=1, value=T["action"][a]).fill = PatternFill("solid", fgColor=FILL[a])
            summary.cell(row=line, column=2, value=counts[a])
            line += 1
    line += 1
    summary.cell(row=line, column=1, value=T["by_section"]).font = Font(bold=True)
    for j, a in enumerate(ACTIONS, 2):
        summary.cell(row=line + 1, column=j, value=T["action"][a]).font = Font(bold=True)
    by_section = defaultdict(Counter)
    for r in rows:
        by_section[r.get("section") or T["no_section"]][r["action"]] += 1
    for i, (sec, cnt) in enumerate(sorted(by_section.items()), line + 2):
        summary.cell(row=i, column=1, value=sec)
        for j, a in enumerate(ACTIONS, 2):
            summary.cell(row=i, column=j, value=cnt.get(a) or "")
    summary.column_dimensions["A"].width = 40
    for j in range(2, len(ACTIONS) + 2):
        summary.column_dimensions[get_column_letter(j)].width = 16
    wb.save(path)


def write_markdown(rows: list[dict], path, T: dict) -> None:
    counts = Counter(r["action"] for r in rows)
    out = [f"# {T['title']}", "", f"{T['generated']}: {datetime.now():%Y-%m-%d %H:%M}", "",
           f"| {T['by_action']} | {T['claims']} |", "|---|---|"]
    out += [f"| {T['action'][a]} | {counts[a]} |" for a in ACTIONS if counts[a]]
    out.append("")
    by_section = defaultdict(list)
    for r in rows:
        if r["action"] not in ("ok", "pending"):
            by_section[r.get("section") or T["no_section"]].append(r)
    for sec, items in sorted(by_section.items()):
        out += [f"## {sec}", ""]
        for r in items:
            verdict = T["verdict"].get(r["verdict"], "—")
            out += [f"### {r['id']} · {r['paper_key']} · **{T['action'][r['action']]}** ({verdict})", "",
                    f"> {r['claim']}", ""]
            if r["explanation"]:
                out += [f"**{T['why']}:** {r['explanation']}", ""]
            if r["evidence"]:
                out += [f"**{T['paper_says']}:**", ""]
                out += [f"- p. {e.get('page', '?')} · {T['check_label']}: {check_text(e, T)} — \"{e['quote']}\""
                        for e in r["evidence"]]
                out.append("")
            if r["secondary_citation"]:
                out += [f"**{T['secondary']}**", ""]
            if r["suggestion"]:
                out += [f"**{T['suggestion']}:** {r['suggestion']}", ""]
    path.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    lang = load_config()["language"]
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]
    if lang not in LANGUAGES:
        print(f"Unknown language '{lang}'. Use one of: {', '.join(LANGUAGES)}")
        return 2
    rows = consolidate()
    if not rows:
        print("claims/claims.csv is empty. Run /cite-claims first.")
        return 1
    T = TEXT[lang]
    REPORTS.mkdir(exist_ok=True)
    write_excel(rows, REPORTS / "report.xlsx", T)
    write_markdown(rows, REPORTS / "report.md", T)
    counts = Counter(r["action"] for r in rows)
    print(f"{len(rows)} claims: " + ", ".join(f"{n} {a}" for a, n in counts.most_common()))
    print("  -> reports/report.xlsx")
    print("  -> reports/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
