---
description: Re-check every verbatim quote and regenerate the Excel and Markdown reports
---

1. Run `python scripts/check_quotes.py`, then `python scripts/report.py`.
2. Summarize, in the language set in `config.json` (`language`: `en` = English, `es` = Spanish):
   totals per action (OK, IMPROVE, FIX, REVIEW…) and the 5–10 most serious claims
   (misrepresented or not found first), with id, paper and reason in one line each.
3. Point to `reports/report.xlsx` ("Problems" sheet), `reports/report.md` and the viewer for the details.
