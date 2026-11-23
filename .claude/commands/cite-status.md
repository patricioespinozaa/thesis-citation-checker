---
description: Show verification progress (pending papers, missing PDFs, PDFs that need OCR)
---

Run `python scripts/status.py` and summarize the result in 3–5 lines, in the language set in
`config.json` (`language`: `en` = English, `es` = Spanish): how many papers are verified, pending,
missing a PDF or needing OCR, and the next step (`/cite-init`, `/cite-claims` or `/cite-verify pending`).
