---
description: Second opinion on one claim and a proposed corrected wording
argument-hint: "<claim id, e.g. C014>"
---

Review claim $ARGUMENTS in depth with the user. Talk to the user in the language set in
`config.json` (`language`: `en` = English, `es` = Spanish).

1. Find the row in `claims/claims.csv` and its result in `results/<paper_key>.json`.
2. Show: the thesis claim, the current verdict, the evidence and its check status.
3. Go back to the paper's text (`extracted/papers/<paper_key>.txt`): re-read the cited pages and Grep for
   other relevant passages (including counter-examples or limitations the verifier may have missed).
   Do not trust the previous verdict: re-assess it.
4. Give your conclusion with verbatim quotes and pages, and propose 1–2 alternative wordings
   faithful to the paper, in the thesis's language.
5. If your conclusion differs from the stored verdict: in an interactive session, ask the user
   before updating it; when launched from the viewer, update it directly and say so. To update,
   edit that entry of the JSON (add `"manually_reviewed": true`), then run
   `python scripts/check_quotes.py <paper_key>` and `python scripts/report.py`.
6. Never edit the user's thesis file: they decide what to change.
