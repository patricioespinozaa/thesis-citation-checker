---
description: Verify the claims paper by paper with the verifier subagent
argument-hint: "<key> | pending | all | section <name>"
---

Verify claims against the papers. Talk to the user in the language set in `config.json`
(`language`: `en` = English, `es` = Spanish).

Target: $ARGUMENTS

## 1. Decide which papers to verify
- One or more keys (e.g. `smith2020 lee2021`): those.
- `pending` (or empty): `python scripts/status.py --pending`.
- `all`: every key with claims in `claims/claims.csv` and a PDF in the papers folder
  (also re-verifies finished ones; warn the user it uses more of their plan).
- `section <name>`: keys of the claims whose `section` contains that text.

Skip papers without a PDF or flagged as scanned (`python scripts/status.py`) and tell the user.
If there are more than 15 papers, say how many and carry on (the user can stop at any time).

## 2. Launch one `verifier` subagent per paper
- Each one's prompt: `paper_key=<key>` and nothing else (do not pass it the thesis or your opinion,
  so it reviews without bias).
- Launch in batches of up to 4 in parallel; wait for each batch to finish.
- Do not read the papers or write the JSON files yourself: the subagent does that.

## 3. Wrap up
1. `python scripts/check_quotes.py` (safety net over every verbatim quote).
2. `python scripts/report.py`.
3. Summarize in a few lines: totals per verdict and the claims that are **misrepresented**,
   **not found** or have **unverified evidence**, with their id and the reason.
   Point to `reports/report.xlsx` and the viewer (`python scripts/viewer.py`) for the details.
   Suggest `/cite-review <id>` to discuss any case.
