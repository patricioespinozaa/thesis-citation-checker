#!/usr/bin/env python3
"""Local viewer: a page at http://localhost:8765 to review citations and launch verifications.

Verifications run through Claude Code with YOUR account (`claude -p`), not the API.
The server only listens on your own machine (127.0.0.1); nothing is published.

Usage:
    python scripts/viewer.py               # opens the page in your default browser
    python scripts/viewer.py --port 9000 --no-open
"""
from __future__ import annotations

import json
import os
import re
import shutil
import string
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import report
from common import (LANGUAGES, PAPER_INDEX, RESULTS, REVIEW, ROOT, STRUCTURE, load_config, papers_dir, pdf_path,
                    read_csv, read_json, read_manifest, read_pages, read_result, read_review, save_config,
                    thesis_dir, write_json)
from extract_thesis import find_thesis, main_tex_candidates

VIEWER = ROOT / "viewer" / "index.html"
COMMANDS = ROOT / ".claude" / "commands"
KEY_OK = re.compile(r"^[\w\-.]{1,100}$")
ARGS_OK = re.compile(r"^[\w\s\-.,:áéíóúÁÉÍÓÚñÑüÜ]{0,200}$")
REVIEW_STATES = {"apply", "fixed", "keep", "discuss"}
LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}
ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")
NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}  # no console flash on Windows

# Actions the page may launch. "claude": runs Claude Code; "python": scripts without AI.
ACTIONS = {
    "scan": ("python", ["extract_papers.py", "extract_thesis.py"]),
    "init": ("claude", "cite-init"),
    "claims": ("claude", "cite-claims"),
    "verify": ("claude", "cite-verify"),
    "review": ("claude", "cite-review"),
    "report": ("python", ["check_quotes.py", "report.py"]),
}


def claude_exe() -> str | None:
    return shutil.which("claude")


def permission_flags() -> list[str]:
    """The project's tool permissions, passed on the command line.

    Claude Code ignores the allow list in .claude/settings.json until you accept its "trust this
    folder" dialog once, and a background run (`claude -p`) cannot show that dialog. Rules given
    with --allowedTools / --disallowedTools are honored either way, so the viewer passes them itself.
    """
    perms = read_json(ROOT / ".claude" / "settings.json", {}).get("permissions", {})
    flags = []
    if perms.get("allow"):
        flags += ["--allowedTools", ",".join(perms["allow"])]
    if perms.get("deny"):
        flags += ["--disallowedTools", ",".join(perms["deny"])]
    return flags


BLOCKED_HELP = ("Claude Code blocked an action that needs your permission, and a background run cannot ask you. "
                "Fix: open a terminal in this project folder, run `claude` once, accept the “trust this folder” "
                "question, close it, and try again.")


# ---------------------------------------------------------------- data

def sources() -> dict:
    config = load_config()
    p, t = papers_dir(), thesis_dir()
    main = find_thesis(t, config.get("thesis_main", "")) if t.is_dir() else None
    return {
        "papers_dir": str(p), "papers_exists": p.is_dir(),
        "thesis_dir": str(t), "thesis_exists": t.is_dir(),
        "thesis_main": (main.relative_to(t).as_posix() if main and main.is_relative_to(t) else (main.name if main else "")),
        "thesis_main_set": bool(config.get("thesis_main")),
        "thesis_candidates": main_tex_candidates(t),
    }


def project_data() -> dict:
    rows = report.consolidate()
    manifest = read_manifest()
    index = {r.get("key", ""): r for r in read_csv(PAPER_INDEX)}
    papers = []
    for key in sorted(set(manifest) | {r["paper_key"] for r in rows if r.get("paper_key")}):
        res, meta, man = read_result(key) or {}, index.get(key, {}), manifest.get(key, {})
        papers.append({
            "key": key, "pdf": key in manifest, "file": man.get("file", ""), "folder": man.get("folder", ""),
            "pages": man.get("pages"), "scanned": man.get("scanned", False),
            "authors": meta.get("authors", ""), "year": meta.get("year", ""), "title": meta.get("title", ""),
            "summary": res.get("paper_summary", ""), "date": res.get("date", ""),
        })
    structure = read_json(STRUCTURE, None)
    return {"project": ROOT.name, "claims": rows, "papers": papers, "structure": structure,
            "sources": sources(), "config": load_config(), "claude": bool(claude_exe()),
            "generated": datetime.now().isoformat(timespec="seconds")}


# ---------------------------------------------------------------- folder browsing

def list_folder(raw: str) -> dict:
    home = Path.home()
    path = Path(raw).expanduser() if raw else home
    try:
        path = path.resolve()
        entries = sorted((e for e in path.iterdir() if not e.name.startswith(".")), key=lambda e: e.name.lower())
    except (OSError, PermissionError) as e:
        return {"error": str(e), "path": str(path)}
    dirs, pdfs, tex = [], 0, 0
    for e in entries:
        try:
            if e.is_dir():
                dirs.append({"name": e.name, "path": str(e)})
            elif e.suffix.lower() == ".pdf":
                pdfs += 1
            elif e.suffix.lower() in (".tex", ".docx", ".md"):
                tex += 1
        except OSError:
            continue
    roots = [{"name": "~", "path": str(home)}]
    if os.name == "nt":
        roots += [{"name": f"{d}:", "path": f"{d}:\\"} for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        roots.append({"name": "/", "path": "/"})
        for extra in ("/Volumes", "/mnt", "/media"):
            if Path(extra).is_dir():
                roots.append({"name": extra, "path": extra})
    parent = str(path.parent) if path.parent != path else None
    return {"path": str(path), "parent": parent, "dirs": dirs, "pdfs": pdfs, "docs": tex, "roots": roots}


PICKER = """
import sys
try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    sys.exit(3)
root = tk.Tk(); root.withdraw()
try:
    root.attributes("-topmost", True)
except Exception:
    pass
path = filedialog.askdirectory(title=sys.argv[1], initialdir=sys.argv[2] or None, mustexist=True)
print(path or "")
"""


def native_pick(title: str, initial: str) -> dict:
    """Open the operating system's folder dialog in a separate process (works on Windows, macOS, Linux)."""
    try:
        p = subprocess.run([sys.executable, "-c", PICKER, title, initial], capture_output=True, text=True,
                           timeout=600, **NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return {"error": "unavailable"}
    if p.returncode != 0:
        return {"error": "unavailable"}
    return {"path": p.stdout.strip()}


# ---------------------------------------------------------------- Claude account

def _find(data, pattern: str, want=lambda v: isinstance(v, str) and v):
    """First value whose key matches `pattern`, searching nested objects."""
    if isinstance(data, dict):
        for k, v in data.items():
            if re.search(pattern, k, re.I) and want(v):
                return v
        for v in data.values():
            found = _find(v, pattern, want)
            if found:
                return found
    return None


class Account:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache, self.cached_at = None, 0.0
        self.login_proc: subprocess.Popen | None = None
        self.login = {"active": False, "url": "", "needs_code": False, "output": "", "ok": None}

    def status(self, fresh: bool = False) -> dict:
        exe = claude_exe()
        if not exe:
            return {"installed": False, "logged_in": False}
        with self.lock:
            if not fresh and self.cache and time.time() - self.cached_at < 20:
                return self.cache
        try:
            p = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30, **NO_WINDOW)
            data = json.loads(p.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return {"installed": True, "logged_in": False, "error": "status_failed"}
        logged = bool(data.get("loggedIn"))
        info = {
            "installed": True, "logged_in": logged, "method": data.get("authMethod", ""),
            "email": _find(data, r"email", lambda v: isinstance(v, str) and "@" in v) or "",
            "name": _find(data, r"^(display_?name|full_?name|name|user_?name)$") or "",
            "organization": _find(data, r"org(anization)?_?name|^organization$") or "",
            "plan": _find(data, r"subscription|plan|tier") or "",
            "expires": data.get("loginExpiresAt"),
        }
        with self.lock:
            self.cache, self.cached_at = info, time.time()
        return info

    def start_login(self) -> tuple[bool, str]:
        exe = claude_exe()
        if not exe:
            return False, "not_installed"
        with self.lock:
            if self.login_proc and self.login_proc.poll() is None:
                return True, "already_running"
            self.login = {"active": True, "url": "", "needs_code": False, "output": "", "ok": None}
            self.login_proc = subprocess.Popen([exe, "auth", "login", "--claudeai"], stdin=subprocess.PIPE,
                                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                               encoding="utf-8", errors="replace", bufsize=1, **NO_WINDOW)
        threading.Thread(target=self._watch_login, daemon=True).start()
        return True, "ok"

    def _watch_login(self):
        proc, buf = self.login_proc, ""
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            buf += ch
            clean = ANSI.sub("", buf)
            m = re.search(r"https://\S+", clean)
            with self.lock:
                self.login["output"] = clean[-1500:]
                if m and not self.login["url"] and (clean.endswith("\n") or "Paste" in clean):
                    self.login["url"] = m.group(0).rstrip(".,)")
                self.login["needs_code"] = "paste code" in clean.lower()
        code = proc.wait()
        with self.lock:
            self.login.update(active=False, ok=(code == 0))
            self.cache = None
        self.status(fresh=True)

    def send_code(self, code: str) -> bool:
        with self.lock:
            proc = self.login_proc
        if not proc or proc.poll() is not None or not re.fullmatch(r"[\w\-#.~]{4,400}", code):
            return False
        proc.stdin.write(code + "\n")
        proc.stdin.flush()
        return True

    def cancel_login(self):
        with self.lock:
            if self.login_proc and self.login_proc.poll() is None:
                self.login_proc.terminate()

    def logout(self) -> bool:
        exe = claude_exe()
        if not exe:
            return False
        p = subprocess.run([exe, "auth", "logout"], capture_output=True, text=True, timeout=60, **NO_WINDOW)
        with self.lock:
            self.cache = None
        return p.returncode == 0

    def login_state(self) -> dict:
        with self.lock:
            return dict(self.login)


ACCOUNT = Account()


# ---------------------------------------------------------------- background jobs (Claude Code)

class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.blocked: list[str] = []
        self.state = {"active": False, "action": None, "args": "", "log": [], "started": None, "finished": None, "ok": None}

    def log(self, kind: str, text: str, sub: bool = False):
        with self.lock:
            self.state["log"].append({"t": time.strftime("%H:%M:%S"), "kind": kind, "text": text[:2000], "sub": sub})
            del self.state["log"][:-400]

    def snapshot(self, since: int = 0) -> dict:
        with self.lock:
            s = dict(self.state)
            s["total"] = len(s["log"])
            s["log"] = s["log"][since:] if since <= len(s["log"]) else s["log"][-50:]
            return s

    def start(self, action: str, args: str) -> tuple[bool, str]:
        if action not in ACTIONS:
            return False, "unknown_action"
        if not ARGS_OK.match(args or ""):
            return False, "bad_arguments"
        with self.lock:
            if self.state["active"]:
                return False, "busy"
            self.state = {"active": True, "action": action, "args": args, "log": [],
                          "started": datetime.now().isoformat(timespec="seconds"), "finished": None, "ok": None}
        threading.Thread(target=self._run, args=(action, args), daemon=True).start()
        return True, "ok"

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.log("warning", "Cancelled by the user.")

    def _python(self, script: str) -> int:
        self.log("cmd", f"python scripts/{script}")
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", **NO_WINDOW)
        for line in (p.stdout + p.stderr).splitlines():
            if line.strip():
                self.log("output", line)
        return p.returncode

    def _prompt(self, command: str, args: str) -> str:
        text = (COMMANDS / f"{command}.md").read_text(encoding="utf-8")
        text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)  # drop frontmatter
        text = text.replace("$ARGUMENTS", args or "")
        language = LANGUAGE_NAMES[load_config()["language"]]
        return ("You are running non-interactively, launched from the local viewer. Do not ask the user questions: "
                f"when something is ambiguous, make the most reasonable choice and note it in your final summary. "
                "Run every command from the current directory (the project root) exactly as written, e.g. "
                "`python scripts/status.py --pending`, without `cd`, `&&` or pipes, so the pre-approved "
                "permissions apply. "
                f"Write your messages to the user in {language}.\n\n" + text)

    def _run(self, action: str, args: str):
        kind, target = ACTIONS[action]
        ok = True
        try:
            if kind == "python":
                ok = all(self._python(script) == 0 for script in target)
            else:
                ok = self._claude(target, args)
                if action in ("verify", "review", "claims"):
                    self._python("check_quotes.py")
                    self._python("report.py")
        except Exception as e:  # noqa: BLE001
            ok = False
            self.log("error", f"{type(e).__name__}: {e}")
        with self.lock:
            self.state.update(active=False, finished=datetime.now().isoformat(timespec="seconds"), ok=ok)
        self.proc = None

    def _claude(self, command: str, args: str) -> bool:
        exe = claude_exe()
        if not exe:
            self.log("error", "Claude Code ('claude') was not found. Install it and sign in.")
            return False
        if not ACCOUNT.status().get("logged_in"):
            self.log("error", "You are not signed in to Claude. Use the account menu (top right) to sign in.")
            return False
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
               *permission_flags()]
        self.blocked = []
        self.log("cmd", f"claude -p  ← /{command} {args}".rstrip())
        # The prompt goes through stdin: safe quoting on every OS (including claude.cmd on Windows).
        self.proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                     **NO_WINDOW)
        self.proc.stdin.write(self._prompt(command, args))
        self.proc.stdin.close()
        for line in self.proc.stdout:
            self._event(line)
        code = self.proc.wait()
        if self.blocked:
            self.log("error", BLOCKED_HELP)
            self.log("error", "Blocked: " + "; ".join(sorted(set(self.blocked)))[:600])
            return False
        return code == 0

    def _event(self, line: str):
        line = line.strip()
        if not line:
            return
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            if "has not been trusted" in line:
                return  # expected for background runs: the permissions are passed on the command line instead
            self.log("output", line)
            return
        sub = bool(ev.get("parent_tool_use_id"))
        if ev.get("type") == "assistant":
            for c in ev.get("message", {}).get("content", []):
                if c.get("type") == "text" and c.get("text", "").strip():
                    self.log("text", c["text"].strip(), sub)
                elif c.get("type") == "tool_use":
                    i = c.get("input", {})
                    detail = i.get("description") or i.get("command") or i.get("file_path") or i.get("pattern") or i.get("prompt", "")
                    self.log("tool", f"{c.get('name')}: {str(detail)[:160]}", sub)
        elif ev.get("type") == "result":
            for d in ev.get("permission_denials") or []:
                i = d.get("tool_input") or {}
                self.blocked.append(f"{d.get('tool_name', '?')}: {str(i.get('command') or i.get('file_path') or '')[:120]}")
            if ev.get("is_error"):
                self.log("error", str(ev.get("result") or ev.get("subtype") or "Error"))
            else:
                self.log("done", str(ev.get("result", "")).strip() or "Done.")


JOB = Job()


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the terminal quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path | None, content_type: str):
        if not path or not path.exists():
            return self._json({"error": "not_found"}, 404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _local_host(self) -> bool:
        # Rejects DNS-rebinding tricks: the page must be opened as localhost / 127.0.0.1.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("localhost", "127.0.0.1", "[::1]")

    def _same_origin(self) -> bool:
        # Stops any other website open in your browser from triggering actions here.
        origin, host = self.headers.get("Origin") or "", self.headers.get("Host") or ""
        return (not origin) or origin.endswith("//" + host)

    def do_GET(self):
        if not self._local_host():
            return self._json({"error": "host_not_allowed"}, 403)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        arg = lambda name, default="": q.get(name, [default])[0]
        if u.path in ("/", "/index.html"):
            return self._file(VIEWER, "text/html; charset=utf-8")
        if u.path == "/api/data":
            return self._json(project_data())
        if u.path == "/api/job":
            return self._json(JOB.snapshot(int(arg("since", "0") or 0)))
        if u.path == "/api/account":
            return self._json({**ACCOUNT.status(fresh=arg("fresh") == "1"), "login": ACCOUNT.login_state()})
        if u.path == "/api/fs":
            return self._json(list_folder(arg("path")))
        if u.path == "/api/page":
            key, p = arg("key"), arg("p", "0")
            if not KEY_OK.match(key):
                return self._json({"error": "bad_key"}, 400)
            pages = dict(read_pages(key))
            n = int(p) if p.isdigit() else 0
            return self._json({"key": key, "page": n, "total": len(pages), "text": pages.get(n, "")})
        if u.path.startswith("/pdf/"):
            key = u.path[5:]
            if not KEY_OK.match(key):
                return self._json({"error": "bad_key"}, 400)
            return self._file(pdf_path(key), "application/pdf")  # only PDFs listed in the manifest
        if u.path in ("/reports/report.xlsx", "/reports/report.md"):
            kind = ("text/markdown; charset=utf-8" if u.path.endswith(".md")
                    else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            return self._file(ROOT / u.path.lstrip("/"), kind)
        return self._json({"error": "not_found"}, 404)

    def do_POST(self):
        if not self._local_host() or not self._same_origin():
            return self._json({"error": "origin_not_allowed"}, 403)
        u = urlparse(self.path)
        b = self._body()
        if u.path == "/api/run":
            ok, msg = JOB.start(str(b.get("action", "")), str(b.get("args", "")).strip())
            return self._json({"ok": ok, "message": msg}, 200 if ok else 409)
        if u.path == "/api/cancel":
            JOB.cancel()
            return self._json({"ok": True})
        if u.path == "/api/config":
            config = load_config()
            if b.get("language") in LANGUAGES:
                config["language"] = b["language"]
                save_config(config)
            return self._json(config)
        if u.path == "/api/sources":
            config = load_config()
            for field in ("papers_dir", "thesis_dir"):
                if field in b:
                    folder = Path(str(b[field])).expanduser()
                    if not folder.is_dir():
                        return self._json({"ok": False, "message": "not_a_folder"}, 400)
                    config[field] = str(folder.resolve())
                    if field == "thesis_dir":
                        config["thesis_main"] = ""
            if "thesis_main" in b:
                config["thesis_main"] = str(b["thesis_main"] or "")
            save_config(config)
            started, _ = JOB.start("scan", "")  # re-read the folders right away (no AI, fast)
            return self._json({"ok": True, "scanning": started, "sources": sources()})
        if u.path == "/api/pick":
            return self._json(native_pick(str(b.get("title", "Select a folder")), str(b.get("initial", ""))))
        if u.path == "/api/account/login":
            ok, msg = ACCOUNT.start_login()
            return self._json({"ok": ok, "message": msg})
        if u.path == "/api/account/code":
            return self._json({"ok": ACCOUNT.send_code(str(b.get("code", "")).strip())})
        if u.path == "/api/account/cancel":
            ACCOUNT.cancel_login()
            return self._json({"ok": True})
        if u.path == "/api/account/logout":
            return self._json({"ok": ACCOUNT.logout()})
        if u.path == "/api/review":
            cid = str(b.get("id", ""))
            if not re.fullmatch(r"C\d{1,6}", cid):
                return self._json({"error": "bad_id"}, 400)
            review = read_review()
            status, note = b.get("status"), str(b.get("note", ""))[:2000]
            if status not in REVIEW_STATES:
                status = None
            if status is None and not note:
                review.pop(cid, None)
            else:
                review[cid] = {"status": status, "note": note, "date": datetime.now().isoformat(timespec="seconds")}
            write_json(REVIEW, review)
            return self._json({"ok": True, "review": review.get(cid)})
        return self._json({"error": "not_found"}, 404)


def main() -> int:
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    RESULTS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"Viewer at {url}  (Ctrl+C to stop)")
    if not claude_exe():
        print("[!] 'claude' is not on your PATH: you can browse results, but not sign in or launch verifications.")
    if "--no-open" not in sys.argv:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        JOB.cancel()
        ACCOUNT.cancel_login()
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
