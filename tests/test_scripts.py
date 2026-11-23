"""Unit tests for the scripts that run without AI.

Run from the project root:
    python -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_quotes  # noqa: E402
import report  # noqa: E402
from common import list_pdfs, normalize, slug  # noqa: E402
from extract_thesis import detect_citations, find_thesis, read_latex  # noqa: E402

PAGES = [
    (1, "Abstract. This study examines remote work in a sample of 412 software\n"
        "engineers in Germany. Results suggest that remote work is associ-\n"
        "ated with lower self-reported stress, although the effect was small.\n"
        "The final paragraph of this page starts a sentence that"),
    (2, "continues on the next page and ends here. Discussion. These findings should\n"
        "not be interpreted causally, since the design was cross-sectional."),
]


class NormalizeTests(unittest.TestCase):
    def test_joins_hyphenated_words_and_collapses_whitespace(self):
        self.assertEqual(normalize("associ-\nated   with\nlower"), "associated with lower")

    def test_unifies_curly_quotes_and_dashes(self):
        self.assertEqual(normalize("“Remote” work – it’s"), '"remote" work - it\'s')


class FindQuoteTests(unittest.TestCase):
    def test_exact_quote_across_line_break_and_hyphenation(self):
        r = check_quotes.find_quote("Results suggest that remote work is associated with lower self-reported stress", PAGES)
        self.assertEqual((r["status"], r["found_page"]), ("exact", 1))

    def test_quote_on_second_page_is_attributed_to_page_two(self):
        r = check_quotes.find_quote("These findings should not be interpreted causally", PAGES)
        self.assertEqual((r["status"], r["found_page"]), ("exact", 2))

    def test_quote_spanning_a_page_break(self):
        r = check_quotes.find_quote("starts a sentence that continues on the next page", PAGES)
        self.assertEqual((r["status"], r["found_page"]), ("exact", 1))

    def test_invented_quote_is_not_found(self):
        r = check_quotes.find_quote("Autonomy was the strongest predictor of satisfaction in our data.", PAGES)
        self.assertEqual(r["status"], "not_found")
        self.assertIsNone(r["found_page"])

    def test_slightly_altered_quote_is_not_exact(self):
        r = check_quotes.find_quote("in a sample of 412 software engineers from Germany, using a survey", PAGES)
        self.assertNotEqual(r["status"], "exact")

    def test_ellipsis_checks_each_fragment(self):
        ok = check_quotes.find_quote("remote work in a sample of 412 ... the design was cross-sectional", PAGES)
        self.assertEqual(ok["status"], "exact")
        bad = check_quotes.find_quote("remote work in a sample of 412 ... autonomy drives all satisfaction", PAGES)
        self.assertEqual(bad["status"], "not_found")


class DetectCitationsTests(unittest.TestCase):
    def citations(self, text):
        return [c for _, c in detect_citations(text)]

    def test_parenthetical_with_several_works(self):
        found = self.citations("Autonomy matters (Smith et al., 2020; Hackman & Oldham, 1976).")
        self.assertIn("Smith et al., 2020", found)
        self.assertIn("Hackman & Oldham, 1976", found)

    def test_narrative_citation(self):
        self.assertIn("Smith et al. (2020)", self.citations("Smith et al. (2020) found a small effect."))

    def test_latex_and_numeric(self):
        found = self.citations(r"As \citep[p.~3]{lee2021,smith2020} and others [3, 5-7] show.")
        self.assertIn("lee2021", found)
        self.assertIn("smith2020", found)
        self.assertIn("[3, 5-7]", found)


class ConsolidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        corpus = Path(self.tmp.name)
        (corpus / "smith2020.txt").write_text("=== [p. 1] ===\ntext\n", encoding="utf-8")
        claims = [{"id": f"C00{i}", "paper_key": k, "claim": "x", "section": "2.1"}
                  for i, k in enumerate(["smith2020"] * 4 + ["missing2019"], 1)]
        result = {"results": [
            {"claim_id": "C001", "verdict": "correct", "evidence_verified": True},
            {"claim_id": "C002", "verdict": "correct", "evidence_verified": False},
            {"claim_id": "C003", "verdict": "misrepresented", "evidence_verified": True},
        ]}
        self.patches = [
            mock.patch.object(report, "PAPER_TEXT", corpus),
            mock.patch.object(report, "read_claims", return_value=claims),
            mock.patch.object(report, "read_result", side_effect=lambda k: result if k == "smith2020" else None),
            mock.patch.object(report, "read_review", return_value={"C003": {"status": "apply"}}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_actions(self):
        rows = {r["id"]: r for r in report.consolidate()}
        self.assertEqual(rows["C001"]["action"], "ok")
        self.assertEqual(rows["C002"]["action"], "unverified")  # "correct" but its quote is not in the PDF
        self.assertEqual(rows["C003"]["action"], "fix")
        self.assertEqual(rows["C004"]["action"], "pending")
        self.assertEqual(rows["C005"]["action"], "no_pdf")
        self.assertEqual(rows["C003"]["review"], {"status": "apply"})


class PaperFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def pdf(self, rel, content=b"%PDF-1.4 a"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def test_slug(self):
        self.assertEqual(slug("Smith et al. (2020) – Remote Work"), "smith_et_al_2020_remote_work")
        self.assertEqual(slug("Pérez & Gómez 2019"), "perez_gomez_2019")

    def test_subfolders_are_scanned_and_hidden_ones_skipped(self):
        self.pdf("A/one.pdf")
        self.pdf("A/B/two.PDF", b"other")
        self.pdf(".trash/three.pdf", b"x")
        found = {e["key"]: e["folder"] for e in list_pdfs(self.root)}
        self.assertEqual(found, {"one": "A", "two": "A/B"})

    def test_identical_copies_count_once(self):
        self.pdf("A/paper.pdf")
        self.pdf("B/paper.pdf")
        entries = list_pdfs(self.root)
        self.assertEqual([e["key"] for e in entries], ["paper"])
        self.assertEqual(entries[0]["duplicates"], ["B/paper.pdf"])

    def test_different_files_with_same_name_get_stable_keys(self):
        self.pdf("A/paper.pdf", b"first")
        self.pdf("B/paper.pdf", b"second")
        keys = {e["file"]: e["key"] for e in list_pdfs(self.root)}
        self.assertEqual(len(set(keys.values())), 2)
        self.assertTrue(all(k.startswith("paper_") for k in keys.values()))
        # Keys depend on content, not on which folder is the root
        self.assertEqual(keys, {e["file"]: e["key"] for e in list_pdfs(self.root)})


class LatexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        files = {
            "main.tex": "\\documentclass{report}\n% \\input{draft}\n\\begin{document}\n\\include{chapters/intro}\n"
                        "\\input chapters/review\n\\input{chapters/missing}\n\\end{document}\n",
            "chapters/intro.tex": "\\chapter{Introduction}\\label{ch:intro}\nThis thesis studies remote work and stress.\n",
            "chapters/review.tex": "\\chapter{Literature review}\n\\section{Remote \\emph{work}}\n"
                                   "Remote work reduces stress \\citep{smith2020}. % a comment\n\n"
                                   "\\subimport{sections/}{family}\n",
            "chapters/sections/family.tex": "\\section{Family}\nThe effect is universal across groups (Lee, 2021).\n",
            "notes.tex": "\\documentclass[main.tex]{subfiles}\n\\begin{document}\nNot the main file at all.\n\\end{document}\n",
        }
        for rel, text in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_main_file(self):
        self.assertEqual(find_thesis(self.root).name, "main.tex")

    def test_follows_includes_in_order(self):
        s = read_latex(self.root / "main.tex", self.root).structure
        self.assertEqual([f["file"] for f in s["files"]],
                         ["main.tex", "chapters/intro.tex", "chapters/review.tex", "chapters/sections/family.tex"])
        self.assertEqual([(h["level"], h["title"]) for h in s["headings"]],
                         [(1, "Introduction"), (1, "Literature review"), (2, "Remote work"), (2, "Family")])
        self.assertEqual(s["missing"], [{"in": "main.tex", "target": "chapters/missing"}])

    def test_paragraphs_know_their_file_and_line(self):
        b = read_latex(self.root / "main.tex", self.root)
        paras = b.structure["paragraphs"]
        self.assertEqual(len(paras), 3)
        self.assertEqual(paras["P0002"], {"file": "chapters/review.tex", "line": 3})
        text = "\\n".join(b.md)
        self.assertNotIn("a comment", text)
        self.assertNotIn("\\label", text)
        self.assertEqual([r["citation"] for r in b.rows], ["smith2020", "Lee, 2021"])

    def test_heading_ranges_cover_their_paragraphs(self):
        hs = {h["title"]: (h["first"], h["last"]) for h in read_latex(self.root / "main.tex", self.root).structure["headings"]}
        self.assertEqual(hs["Literature review"], (2, 3))
        self.assertEqual(hs["Family"], (3, 3))


if __name__ == "__main__":
    unittest.main()
