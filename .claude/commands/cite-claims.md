---
description: Extract every thesis claim that cites a paper and record it in claims/claims.csv
argument-hint: "[optional section, e.g. '2.3' or 'Theoretical framework']"
---

Build or update the claims table `claims/claims.csv`. Talk to the user in the language set in
`config.json` (`language`: `en` = English, `es` = Spanish).

Scope: $ARGUMENTS (if empty, the whole thesis).

## Inputs
- `extracted/thesis.md` — the whole thesis (every included LaTeX file, in order) with numbered paragraphs
  `[P0001]` and `<!-- file: ... -->` markers. If missing, first run `python scripts/extract_thesis.py`.
- `extracted/thesis_structure.json` — chapters/sections with their paragraph ranges (use it to find a section's paragraphs).
- `extracted/detected_citations.csv` — checklist of automatically detected citations (with file and line).
- `claims/papers.csv` — key, file, folder, authors, year and title of each paper in the papers folder.

## What a claim is
Any piece of the thesis that attributes something to a source. One row per **(claim, paper)**:
if a sentence cites 3 works, that is 3 rows with the same `claim` and `multiple_citation` = `yes`.

## Columns (in this order)
`id,section,paragraph,paper_key,claim,citation_in_thesis,cited_page,type,multiple_citation,context`
- `id`: C001, C002… If the CSV already exists, **keep the ids** of rows that are unchanged and
  number new rows after the highest id. If a claim's wording changed, update its text and keep its id.
- `section`: the nearest heading it appears under (chapter/section title).
- `paragraph`: the paragraph id (P0012).
- `paper_key`: the `key` from `claims/papers.csv`. Match the citation to a paper by surname(s) + year,
  using `authors`/`year`/`title` and, when those are empty, the PDF `file` name. With LaTeX citation keys
  (`\citep{smith2020}`), match them the same way (the citation key is not the paper key).
  If there is no PDF for that citation, write a key like `garcia_2019` so it shows as "NO PDF".
  If two papers could match, pick the one whose title fits the claim and mention it at the end.
- `claim`: the **exact** sentence(s) of the thesis containing the claim (copied, not summarized).
- `citation_in_thesis`: how the citation appears, e.g. `(Smith et al., 2020, p. 14)`.
- `cited_page`: the page if the thesis gives one; otherwise empty.
- `type`: `direct_quote` (quotation marks), `data` (figures, percentages, sizes), `paraphrase` (everything else).
- `multiple_citation`: `yes` / `no`.
- `context`: only if the claim cannot be understood without the previous sentence; then copy it here.

## Coverage check (mandatory)
When done, go through `extracted/detected_citations.csv` (filtered to the requested scope) and confirm
every citation is covered by at least one row. Also look for citations the detector missed
(unusual styles, footnotes).

Write the CSV in UTF-8 with a header. To avoid comma and quote errors, generate it with a small
Python script that uses `csv.writer` (do not write it by hand).
If the scope is one section, **do not delete** rows from other sections.

Then run `python scripts/validate_claims.py` and fix every `[ERROR]` before finishing.

## At the end
Show: number of new/updated claims, number of papers involved, citations without a PDF, and any
citation you could not match. Suggested next step: `/cite-verify pending`.
