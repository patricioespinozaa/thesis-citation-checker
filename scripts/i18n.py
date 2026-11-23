"""Labels for the generated reports (Excel and Markdown), in English and Spanish.

Code, logs and file formats stay in English; only what the user reads in a report is localized.
The viewer has its own copy of these labels in viewer/index.html.
"""

ACTIONS = ["fix", "unverified", "improve", "manual", "pending", "no_pdf", "ok"]

TEXT = {
    "en": {
        "action": {"ok": "OK", "improve": "IMPROVE", "fix": "FIX", "manual": "REVIEW BY HAND",
                   "unverified": "REVIEW (unverified evidence)", "pending": "PENDING", "no_pdf": "NO PDF"},
        "verdict": {"correct": "correct", "partial": "partial", "misrepresented": "misrepresented",
                    "not_found": "not found", "unverifiable": "unverifiable"},
        "check": {"exact": "exact", "close": "close", "doubtful": "doubtful", "not_found": "NOT FOUND",
                  "unchecked": "not checked"},
        "page_warning": "Says p. {stated}, but the text is on p. {found}",
        "sheets": {"summary": "Summary", "problems": "Problems", "all": "All"},
        "columns": {"id": "id", "section": "section", "paper_key": "paper", "action": "action",
                    "verdict": "verdict", "severity": "severity", "fidelity": "fidelity", "error_types": "error types",
                    "confidence": "confidence", "claim": "claim", "explanation": "explanation",
                    "suggestion": "suggested wording", "quotes": "paper quotes", "pages": "pages",
                    "quote_check": "quote check", "secondary_citation": "secondary citation",
                    "citation_in_thesis": "citation", "paragraph": "paragraph", "your_decision": "your decision"},
        "title": "Citation check — literature review",
        "generated": "Generated",
        "by_action": "Action", "claims": "Claims", "by_section": "By section", "no_section": "(no section)",
        "why": "Why", "paper_says": "The paper says", "check_label": "check",
        "secondary": "Careful: the paper only mentions this while citing another source (secondary citation).",
        "suggestion": "Suggested wording", "yes": "yes",
    },
    "es": {
        "action": {"ok": "OK", "improve": "MEJORAR", "fix": "CORREGIR", "manual": "REVISAR A MANO",
                   "unverified": "REVISAR (evidencia no verificada)", "pending": "PENDIENTE", "no_pdf": "SIN PDF"},
        "verdict": {"correct": "correcta", "partial": "parcial", "misrepresented": "tergiversada",
                    "not_found": "no encontrada", "unverifiable": "no verificable"},
        "check": {"exact": "exacta", "close": "aproximada", "doubtful": "dudosa", "not_found": "NO ENCONTRADA",
                  "unchecked": "sin comprobar"},
        "page_warning": "Dice p. {stated}, pero el texto está en p. {found}",
        "sheets": {"summary": "Resumen", "problems": "Problemas", "all": "Todas"},
        "columns": {"id": "id", "section": "sección", "paper_key": "paper", "action": "acción",
                    "verdict": "veredicto", "severity": "gravedad", "fidelity": "fidelidad", "error_types": "tipos de error",
                    "confidence": "confianza", "claim": "afirmación", "explanation": "explicación",
                    "suggestion": "redacción sugerida", "quotes": "citas del paper", "pages": "páginas",
                    "quote_check": "comprobación", "secondary_citation": "cita secundaria",
                    "citation_in_thesis": "cita", "paragraph": "párrafo", "your_decision": "tu decisión"},
        "title": "Verificación de citas — revisión de literatura",
        "generated": "Generado",
        "by_action": "Acción", "claims": "Afirmaciones", "by_section": "Por sección", "no_section": "(sin sección)",
        "why": "Por qué", "paper_says": "El paper dice", "check_label": "comprobación",
        "secondary": "Ojo: el paper solo lo menciona citando a otra fuente (cita secundaria).",
        "suggestion": "Redacción sugerida", "yes": "sí",
    },
}
