#!/usr/bin/env python3
"""Read your thesis, number its paragraphs, map its structure and detect its citations.

The thesis folder is set in config.json (`thesis_dir`, default: thesis/). It can be anywhere on disk.
- LaTeX: the main .tex file is detected (the one with \\documentclass and \\begin{document};
  `thesis_main` in config.json overrides it), and every \\input, \\include, \\subfile, \\import and
  \\subimport is followed recursively, so chapters kept in separate files are read in order.
- Otherwise the first .docx, .md or .txt file in the folder is used.

Outputs (in extracted/):
    thesis.md               the text, each paragraph tagged [P0001]... with <!-- file: ... --> markers
    thesis_structure.json   included files, chapters/sections and the paragraph range of each,
                            plus where every paragraph comes from (file and line)
    detected_citations.csv  every citation found (a checklist for /cite-claims)

Usage:
    python scripts/extract_thesis.py
    python scripts/extract_thesis.py path/to/main.tex
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from common import DETECTED, EXTRACTED, STRUCTURE, THESIS_MD, load_config, thesis_dir, write_json

TEXT_FORMATS = (".docx", ".md", ".txt")
SKIP_NAMES = ("README.txt",)
MAIN_NAMES = ("main", "thesis", "tesis", "memoria", "dissertation", "tfm", "tfg")
UPPER = "A-ZÁÉÍÓÚÑÜÇ"

RE_LATEX_CITE = re.compile(r"\\(?:cite|citep|citet|parencite|textcite|autocite|footcite|citeauthor|citeyear)\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}")
RE_PAREN = re.compile(r"\(([^()]*?\b(?:19|20)\d{2}[a-z]?\b[^()]*)\)")
RE_NARRATIVE = re.compile(
    rf"\b([{UPPER}][\w'\-]+(?:\s+(?:et al\.|y|and|&|e)\s+[{UPPER}][\w'\-]+)?(?:\s+et\s+al\.)?)\s*\(((?:19|20)\d{{2}}[a-z]?)(?:[,:][^)]*)?\)"
)
RE_NUMERIC = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
RE_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
HEADING_STYLE = re.compile(r"(heading|título|titulo|titre|überschrift)\s*(\d)")

# LaTeX
RE_COMMENT = re.compile(r"(?<!\\)%.*")
RE_INCLUDE = re.compile(
    r"\\(input|include|subfile|import|subimport|includefrom|subincludefrom)\*?\s*"
    r"(?:\{([^{}]*)\}(?:\s*\{([^{}]*)\})?|\s+([^\s{}\\]+))"
)
RE_HEADING = re.compile(r"\\(part|chapter|section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{")
LEVEL = {"part": 1, "chapter": 2, "section": 3, "subsection": 4, "subsubsection": 5}
RE_COMMAND = re.compile(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])*(?:\{[^{}]*\})*")


# ---------------------------------------------------------------- citations

def detect_citations(text: str):
    for m in RE_LATEX_CITE.finditer(text):
        for key in m.group(1).split(","):
            yield "latex", key.strip()
    for m in RE_PAREN.finditer(text):
        for part in m.group(1).split(";"):
            part = part.strip()
            if RE_YEAR.search(part) and re.search(rf"[{UPPER}]", part):
                yield "author-year", part
    for m in RE_NARRATIVE.finditer(text):
        yield "author-year (narrative)", f"{m.group(1)} ({m.group(2)})"
    for m in RE_NUMERIC.finditer(text):
        yield "numeric", f"[{m.group(1)}]"


# ---------------------------------------------------------------- finding the thesis

def is_main_tex(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    head = RE_COMMENT.sub("", head)
    return bool(re.search(r"\\documentclass(?:\[[^\]]*\])?\{(?!subfiles)", head)) and "\\begin{document}" in head


def find_thesis(folder: Path, configured: str = "") -> Path | None:
    if configured:
        p = (folder / configured) if not Path(configured).is_absolute() else Path(configured)
        if p.is_file():
            return p
    if not folder.is_dir():
        return None
    for depth in (1, 2):
        pattern = "*.tex" if depth == 1 else "*/*.tex"
        mains = [p for p in sorted(folder.glob(pattern)) if is_main_tex(p)]
        if mains:
            mains.sort(key=lambda p: (p.stem.lower() not in MAIN_NAMES, len(p.name)))
            return mains[0]
    texts = [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in TEXT_FORMATS
             and p.name not in SKIP_NAMES and not p.name.startswith("~$")]
    return texts[0] if texts else None


def main_tex_candidates(folder: Path) -> list[str]:
    """Every .tex in the folder (two levels) that looks like a main file; used by the viewer."""
    if not folder.is_dir():
        return []
    found = [p for pat in ("*.tex", "*/*.tex") for p in sorted(folder.glob(pat)) if is_main_tex(p)]
    return [p.relative_to(folder).as_posix() for p in found]


# ---------------------------------------------------------------- LaTeX reader

def balanced(text: str, start: int) -> tuple[str, int]:
    """Text inside braces starting right after an opening '{' at text[start-1]."""
    depth, i = 1, start
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[start:i - 1], i


def resolve_include(kind: str, args: tuple, current: Path, main_dir: Path) -> Path | None:
    a, b, bare = args
    if kind in ("import", "includefrom"):
        bases, name = [main_dir / (a or "")], b
    elif kind in ("subimport", "subincludefrom"):
        bases, name = [current.parent / (a or "")], b
    else:
        bases, name = [main_dir, current.parent], (a or bare)
    if not name:
        return None
    for base in bases:
        for candidate in (base / name, base / f"{name}.tex"):
            if candidate.is_file():
                return candidate.resolve()
    return None


def tex_stream(path: Path, root: Path, main_dir: Path, visited: set, parent: str | None = None):
    """Yield ('enter', rel, parent) / ('line', rel, n, text) / ('exit', rel) / ('missing', rel, target)."""
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
    visited.add(path)
    yield ("enter", rel, parent)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    has_doc = any("\\begin{document}" in RE_COMMENT.sub("", l) for l in lines)
    inside, in_comment = not has_doc, False
    for n, raw in enumerate(lines, 1):
        line = re.sub(r"\\label\{[^{}]*\}", "", RE_COMMENT.sub("", raw))
        if has_doc:
            if "\\begin{document}" in line:
                inside, line = True, line.split("\\begin{document}", 1)[1]
            elif "\\end{document}" in line:
                yield ("line", rel, n, line.split("\\end{document}", 1)[0])
                break
            if not inside:
                continue
        if "\\begin{comment}" in line:
            in_comment = True
        if in_comment:
            in_comment = "\\end{comment}" not in line
            continue
        pos = 0
        for m in RE_INCLUDE.finditer(line):
            yield ("line", rel, n, line[pos:m.start()])
            pos = m.end()
            target = resolve_include(m.group(1), (m.group(2), m.group(3), m.group(4)), path, main_dir)
            if target is None:
                yield ("missing", rel, (m.group(3) or m.group(2) or m.group(4) or "").strip())
            elif target not in visited:
                yield from tex_stream(target, root, main_dir, visited, rel)
        yield ("line", rel, n, line[pos:])
    yield ("exit", rel)


def clean_title(title: str) -> str:
    """'\\emph{Remote} work\\label{x}' -> 'Remote work'."""
    t = re.sub(r"\\label\{[^{}]*\}", "", title)
    for _ in range(3):  # unwrap \cmd{text} -> text, nested a few levels
        t = re.sub(r"\\[a-zA-Z@]+\*?\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z@]+\*?", "", t).replace("{", "").replace("}", "").replace("~", " ")
    return " ".join(t.split()) or title.strip()


def has_prose(text: str) -> bool:
    return len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", RE_COMMAND.sub(" ", text))) >= 3


class Builder:
    """Collects paragraphs, headings and files into thesis.md + structure."""

    def __init__(self, source: str, main: str, root: Path):
        self.md = [f"<!-- Generated from {main} by scripts/extract_thesis.py. Do not edit by hand. -->", ""]
        self.structure = {"source": source, "main": main, "root": str(root), "files": [], "headings": [],
                          "missing": [], "paragraphs": {}}
        self.rows, self.section, self.n = [], "", 0
        self.buffer, self.buf_file, self.buf_line = [], None, None
        self.open_files, self.current_file = [], None

    def paragraph(self, text: str, file: str, line):
        text = " ".join(text.split())
        if not text or not has_prose(text):
            return
        self.n += 1
        pid = f"P{self.n:04d}"
        if file != self.current_file:
            self.md += [f"<!-- file: {file} -->", ""]
            self.current_file = file
        self.md += [f"[{pid}] {text}", ""]
        self.structure["paragraphs"][pid] = {"file": file, "line": line}
        for kind, citation in detect_citations(text):
            self.rows.append({"paragraph": pid, "file": file, "line": line or "", "section": self.section,
                              "kind": kind, "citation": citation})

    def flush(self):
        if self.buffer:
            self.paragraph(" ".join(self.buffer), self.buf_file, self.buf_line)
        self.buffer, self.buf_file, self.buf_line = [], None, None

    def add_line(self, text: str, file: str, line):
        if not text.strip():
            self.flush()
            return
        if self.buf_file not in (None, file):
            self.flush()
        if not self.buffer:
            self.buf_file, self.buf_line = file, line
        self.buffer.append(text.strip())

    def heading(self, level: int, title: str, file: str, line):
        self.flush()
        title = clean_title(title)
        self.section = title
        if file != self.current_file:
            self.md += [f"<!-- file: {file} -->", ""]
            self.current_file = file
        self.md += [f"{'#' * min(level, 6)} {title}", ""]
        self.structure["headings"].append({"level": level, "title": title, "file": file, "line": line,
                                           "first": self.n + 1})

    def enter(self, file: str, parent):
        self.flush()
        self.structure["files"].append({"file": file, "parent": parent, "depth": len(self.open_files),
                                        "first": self.n + 1})
        self.open_files.append(len(self.structure["files"]) - 1)

    def exit(self):
        self.flush()
        self.structure["files"][self.open_files.pop()]["last"] = self.n

    def finish(self):
        self.flush()
        hs = self.structure["headings"]
        if hs:  # normalize levels so the top level used is 1
            top = min(h["level"] for h in hs)
            for h in hs:
                h["level"] -= top - 1
        for i, h in enumerate(hs):  # a heading ends where the next one of the same or higher rank starts
            nxt = next((x for x in hs[i + 1:] if x["level"] <= h["level"]), None)
            h["last"] = (nxt["first"] - 1) if nxt else self.n
        self.structure["paragraph_count"] = self.n


def read_latex(main: Path, root: Path) -> Builder:
    b = Builder("latex", main.relative_to(root).as_posix() if main.is_relative_to(root) else main.name, root)
    for ev in tex_stream(main.resolve(), root.resolve(), main.parent.resolve(), set()):
        if ev[0] == "enter":
            b.enter(ev[1], ev[2])
        elif ev[0] == "exit":
            b.exit()
        elif ev[0] == "missing":
            b.structure["missing"].append({"in": ev[1], "target": ev[2]})
        else:
            _, file, n, text = ev
            m = RE_HEADING.search(text)
            while m:
                b.add_line(text[:m.start()], file, n)
                title, end = balanced(text, m.end())
                b.heading(LEVEL[m.group(1)], title, file, n)
                text = text[end:]
                m = RE_HEADING.search(text)
            b.add_line(text, file, n)
    b.finish()
    return b


# ---------------------------------------------------------------- Word / Markdown / text

def docx_paragraphs(path: Path):
    import docx

    for p in docx.Document(str(path)).paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "").lower() if p.style is not None else ""
        m = HEADING_STYLE.search(style)
        yield (int(m.group(2)), text) if m else (0, text)


def text_paragraphs(path: Path):
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="replace")):
        b = block.strip()
        if not b:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", b)
        yield (len(m.group(1)), m.group(2)) if m else (0, " ".join(b.split()))


def read_plain(path: Path, root: Path) -> Builder:
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
    b = Builder(path.suffix.lower().lstrip("."), rel, root)
    b.enter(rel, None)
    reader = docx_paragraphs if path.suffix.lower() == ".docx" else text_paragraphs
    for level, text in reader(path):
        if level:
            b.heading(level, text, rel, None)
        else:
            b.paragraph(text, rel, None)
    b.exit()
    b.finish()
    return b


# ---------------------------------------------------------------- main

def main() -> int:
    config = load_config()
    root = thesis_dir()
    path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else find_thesis(root, config.get("thesis_main", ""))
    print(f"Thesis folder: {root}")
    if path is None:
        print("No thesis found there. Pick the folder in the viewer (a LaTeX project, or a .docx/.md/.txt file).")
        return 1
    if not path.is_relative_to(root):
        root = path.parent
    builder = read_latex(path, root) if path.suffix.lower() == ".tex" else read_plain(path, root)

    EXTRACTED.mkdir(parents=True, exist_ok=True)
    THESIS_MD.write_text("\n".join(builder.md), encoding="utf-8")
    write_json(STRUCTURE, builder.structure)
    with DETECTED.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["paragraph", "file", "line", "section", "kind", "citation"])
        w.writeheader()
        w.writerows(builder.rows)

    s = builder.structure
    print(f"Main file: {s['main']}  ({len(s['files'])} file(s), {len(s['headings'])} headings)")
    for f in s["files"]:
        print(f"  {'  ' * f['depth']}{f['file']}  [{f['first']}–{f.get('last', f['first'] - 1)}]")
    print(f"{builder.n} paragraphs, {len(builder.rows)} citations detected.")
    print("  -> extracted/thesis.md, extracted/thesis_structure.json, extracted/detected_citations.csv")
    for miss in s["missing"]:
        print(f"[!] {miss['in']} includes '{miss['target']}', which was not found.")
    if not builder.rows:
        print("[!] No citations detected. With an unusual style, /cite-claims will still find them by reading the text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
