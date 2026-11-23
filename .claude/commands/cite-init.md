---
description: Set up the project - install dependencies, read the papers and thesis folders, fill in the paper index
---

Set up the verification project. Talk to the user in the language set in `config.json` (`language`: `en` = English, `es` = Spanish).

1. Install dependencies: `python -m pip install -r requirements.txt` (use `python3` if `python` does not exist).
   Then try `python -m pip install -r requirements-extra.txt`; if it fails, carry on:
   the scripts have fallbacks.
2. The folders are set in `config.json`: `papers_dir` (PDFs, subfolders included) and `thesis_dir`
   (a LaTeX project or a .docx/.md/.txt file). Both default to `papers/` and `thesis/` inside the project,
   and the user normally picks them in the viewer. If a folder does not exist or is empty, tell the user
   to choose it in the viewer (`python scripts/viewer.py`) or to edit `config.json`, and stop.
3. Run `python scripts/extract_papers.py`. If it flags scanned PDFs, tell the user
   (they need OCR, see README) and continue with the rest.
4. Run `python scripts/extract_thesis.py`. Mention the main file it used, how many included files it followed
   and any included file it could not find.
5. Fill in `claims/papers.csv` (columns: `key,file,folder,authors,year,title`; the script already wrote
   `key`, `file` and `folder`):
   - For each row with empty `authors`, `year` or `title`, read only the first ~80 lines of
     `extracted/papers/<key>.txt` and fill in the authors' surnames (separated by `;`), the year and the title.
   - Never change values that are already filled in (the user may have fixed them by hand), nor `key`, `file` or `folder`.
   - If you cannot determine a value, leave it empty; do not invent it.
   - Write the CSV with a small Python script that uses `csv.DictWriter`.
6. Show a short summary: number of papers and folders, the thesis structure (chapters), citations detected,
   and files with problems. Suggested next step: `/cite-claims`.
