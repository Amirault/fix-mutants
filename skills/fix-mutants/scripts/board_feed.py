#!/usr/bin/env python3
"""Live feed of a fix-mutants run for the board in ../assets/board.html.

Reads a Claude Code transcript (~/.claude/projects/**/*.jsonl), infers the board step of every tool call
and streams the steps to the board as server-sent events. The skill itself emits nothing: the feed only
watches what the agent runs, so a step done in an unusual way can be missed; the board then jumps.

Usage:
  board_feed.py serve [--port 8766] [--transcript PATH] [--open]   board at http://127.0.0.1:8766/
  board_feed.py events PATH                                        print the steps of a transcript as JSON lines

Test and production files are told apart with the project profile (`--profile`, default: the nearest
.fix-mutants/profile.json); without one, common test-folder and test-file names are used.

Python 3.9+, standard library only.
"""

import argparse
import json
import re
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_SAY = 90
RUN_SEARCH_LIMIT = 40
POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15
MAX_REPLAY_GAP_SECONDS = 2.5
PROJECTS = Path.home() / ".claude" / "projects"
BOARD = Path(__file__).resolve().parents[1] / "assets" / "board.html"

INVOCATION_RE = re.compile(r"(?:^|[\s>\"])/fix-mutants\b")
HEREDOC_RE = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2[^\n]*\n)(.*?\n\s*\3\s*)(?=\n|$)", re.S)
QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
SENTENCE_RE = re.compile(r"(.+?[.!?])(?:\s|$)", re.S)
ALIVE_RE = re.compile(r"(\d[\d,]*)\s+alive\b")
SOURCE_RE = re.compile(r"\.(?:cs|fs|vb|js|jsx|mjs|cjs|ts|tsx|py|java|kt|scala|go|rb|php|rs|swift)$")
DEFAULT_TEST_RE = re.compile(
    r"(?:^|/)(?:tests?|__tests__|specs?)/|\.Tests?/|\.(?:test|spec)\.[^/]+$|(?:^|/)test_[^/]+\.py$|Tests?\.\w+$"
)
PROFILE_RELATIVE = Path(".fix-mutants") / "profile.json"
SYSTEM_PROMPT_RE = re.compile(r"^\s*<(task-notification|system-reminder|local-command|command-)")
LEDGER_SCRIPT = r"(?:ledger\.py|\$\{?L\}?)"  # references/ledger.md calls it through L=…/ledger.py
CHECKS_SCRIPT = r"(?:mutant_checks\.py|[\"']?\$\{?[A-Za-z_]\w*\}?[\"']?)"  # agents also call it through a variable
OUTCOME_RE = re.compile(r"--outcome[=\s]+[\"']?(test|removed|moved)\b")
BRANCH_OF_OUTCOME = {"test": "test", "removed": "dead", "moved": "move"}
# Text a signal is read in: BARE without heredoc bodies and quoted strings, CODE without heredoc bodies, RAW all of it.
BARE, CODE, RAW = "bare", "code", "raw"
SIGNALS = [
    ("report", re.compile(CHECKS_SCRIPT + r"(?:\s+--profile\s+\S+)?\s+baseline\b|report_sha256"), CODE),
    ("tracker", re.compile(r"MUTATION-TRACKING\.md|ledger\.jsonl|" + LEDGER_SCRIPT + r"[\"',\s]+(?:find|validate|fill-pr)\b"), BARE),
    ("ledger_skip", re.compile(LEDGER_SCRIPT + r"[\"',\s]+(?:add|update)\b[^\n]*\"status\":\s*\"skipped\""), RAW),
    ("clock", re.compile(r"\bdate\s+-u\b"), BARE),
    ("search", re.compile(r"\b(?:rg|grep)\b[^|;&\n]*\s-[a-zA-Z]*w\b"), BARE),
    ("stryker", re.compile(r"\bstryker\b|\bpitest\b|\bmutmut\b|\bcosmic-ray\b"), BARE),  # the scoped mutation run
    ("check", re.compile(CHECKS_SCRIPT + r"\s+check\b"), CODE),
    ("check", re.compile(r"mutant_checks\.py[\"']\s*,\s*[\"']check\b"), RAW),  # subprocess list in a Python heredoc
    ("verify", re.compile(CHECKS_SCRIPT + r"\s+verify\b[^\n;&|]*"), CODE),
    ("verify", re.compile(r"mutant_checks\.py[\"']\s*,\s*[\"']verify\b[^\n]*"), RAW),
    ("remove", re.compile(r"\bgit\s+rm\b[^;&|\n]*"), BARE),
    ("stage", re.compile(r"\bgit\s+add\b"), BARE),
    ("commit", re.compile(r"\bgit\s+commit\b"), BARE),
    ("pr_create", re.compile(r"\bgh\s+pr\s+create\b"), BARE),
    ("pr_edit", re.compile(r"\bgh\s+pr\s+edit\b"), BARE),
]
REPEATABLE_STEPS = {"say", "alive"}


class Layout:
    """Where tests and production code live: the profile's roots, else common test naming."""

    def __init__(self, production_root=None, test_roots=()):
        self.production = production_root.strip("/") if production_root else None
        self.tests = [root.strip("/") for root in test_roots]

    @classmethod
    def from_profile(cls, path):
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(profile.get("production_root"), profile.get("test_roots", []))

    @staticmethod
    def _under(path, root):
        return f"/{root}/" in "/" + path.lstrip("/")

    def is_source(self, path):
        return SOURCE_RE.search(path) is not None

    def is_test(self, path):
        if self.tests:
            return any(self._under(path, root) for root in self.tests)
        return DEFAULT_TEST_RE.search(path) is not None

    def is_other_layer(self, path):
        """Source outside the production scope and the tests: where misplaced code moves to (needs a profile)."""
        return bool(self.production) and self.is_source(path) and not self.is_test(path) and not self._under(path, self.production)


def find_profile(start=None):
    origin = Path(start or Path.cwd()).resolve()
    return next((folder / PROFILE_RELATIVE for folder in (origin, *origin.parents) if (folder / PROFILE_RELATIVE).is_file()), None)


def epoch(timestamp):
    if not timestamp:
        return None
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()


def text_of(content):
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def blank(text):
    return re.sub(r"[^\n]", " ", text)


def without_heredocs(command):
    """The command with heredoc bodies blanked, same length, so positions still order the signals."""
    return HEREDOC_RE.sub(lambda m: m.group(1) + blank(m.group(4)), command)


def skeleton(command):
    """The command with heredoc bodies and quoted strings blanked: text in them never makes a step."""
    return QUOTED_RE.sub(lambda m: m.group(0)[0] + blank(m.group(0)[1:-1]) + m.group(0)[-1], without_heredocs(command))


def first_sentence(text):
    text = re.sub(r"[`*_#>]", "", text).strip()
    match = SENTENCE_RE.match(text)
    line = re.sub(r"\s+", " ", match.group(1) if match else text)
    return line if len(line) <= MAX_SAY else line[: MAX_SAY - 1] + "…"


class Mutant:
    def __init__(self):
        self.branch = None
        self.traced = False
        self.verifying = False
        self.done = False
        self.moved = False
        self.removed = False
        self.checked = False


class Feed:
    """Turns transcript entries into board steps, one entry at a time."""

    def __init__(self, layout=None):
        self.layout = layout or Layout()
        self.started = False
        self.finished = False
        self.counted = False  # the first alive count is the baseline's; later ones are about a file or a batch
        self.synced = False
        self.phase = "setup"  # setup → loop → committed → pr
        self.mutant = None
        self.handled = 0
        self.last = None
        self.t = None
        self.out = []

    def push(self, entry):
        self.out = []
        if self.finished:
            return self.out
        self.t = epoch(entry.get("timestamp")) or self.t
        message = entry.get("message") or {}
        if entry.get("type") == "user":
            self._user(text_of(message.get("content")))
        elif entry.get("type") == "assistant":
            for block in message.get("content") or []:
                if isinstance(block, dict):
                    self._assistant(block)
        return self.out

    def emit(self, step, **extra):
        if step == self.last and step not in REPEATABLE_STEPS:
            return
        if step not in REPEATABLE_STEPS:
            self.last = step
        self.out.append({"step": step, "t": self.t, **extra})

    def _start(self):
        if not self.started:
            self.started = True
            self.emit("start")

    def _user(self, text):
        if INVOCATION_RE.search(text):
            self._start()
        elif self.phase == "pr" and text.strip() and not SYSTEM_PROMPT_RE.match(text):
            self.emit("human")
            self.finished = True

    def _assistant(self, block):
        if block.get("type") == "tool_use":
            self._tool(block.get("name", ""), block.get("input") or {})
        elif block.get("type") == "text" and self.started and block.get("text", "").strip():
            self._say(block["text"])

    def _say(self, text):
        self.emit("say", say=first_sentence(text))
        alive = ALIVE_RE.search(text)
        if alive and not self.counted:
            self.counted = True
            self.emit("alive", alive=int(alive.group(1).replace(",", "")))

    def _tool(self, name, tool_input):
        if name == "Skill" and str(tool_input.get("skill", "")).endswith("fix-mutants"):
            self._start()
        if not self.started:
            return
        if name in ("Agent", "Task"):
            self._agent(tool_input.get("description", ""))
        elif name == "Read":
            self._file_read(tool_input.get("file_path", ""))
        elif name in ("Edit", "Write", "MultiEdit"):
            self._file_written(name, tool_input)
        elif name == "Bash":
            self._command(tool_input.get("command", ""))

    def _agent(self, description):
        lowered = description.lower()
        if "survey" in lowered and self.phase == "setup":
            self.emit("report", actor="survey")
        elif "review" in lowered and self.phase == "loop" and self.handled and not (self.mutant and not self.mutant.done):
            self._close_mutant()
            self.emit("review")
        elif description:
            self.emit("say", say=first_sentence(description))

    def _file_read(self, path):
        if path.endswith(("MUTATION-TRACKING.md", "ledger.jsonl")):
            self._tracker()
        elif path.endswith("report-fetch.md") and self.phase == "setup":
            self.emit("report")

    def _file_written(self, name, tool_input):
        path = tool_input.get("file_path", "")
        text = tool_input.get("new_string") or tool_input.get("content") or json.dumps(tool_input.get("edits", ""), ensure_ascii=False)
        if path.endswith(("MUTATION-TRACKING.md", "ledger.jsonl")):
            if re.search(r'"status":\s*"skipped"', text):
                self._skip()
            else:
                self._tracker()
        elif self.layout.is_source(path) and self.phase in ("setup", "loop"):
            if self.layout.is_test(path):
                self._open_mutant()
                if self._adds_code(name, tool_input):
                    self._branch("test")
            elif name == "Write" and self.layout.is_other_layer(path):
                self._open_mutant()
                self.mutant.moved = True

    @staticmethod
    def _adds_code(name, tool_input):
        """A test edit that only deletes lines goes with dead code (dead but tested), not a new test."""
        if name == "Write":
            return True
        edits = tool_input.get("edits") or [tool_input]
        return any(len(e.get("new_string", "")) >= len(e.get("old_string", "")) for e in edits)

    def _command(self, command):
        texts = {BARE: skeleton(command), CODE: without_heredocs(command), RAW: command}
        found = sorted(
            (m.start(), signal, m.group(0))
            for signal, pattern, scope in SIGNALS
            for m in pattern.finditer(texts[scope])
        )
        for _, signal, matched in found:
            getattr(self, "_on_" + signal)(matched)

    def _tracker(self):
        if self.phase == "setup" and not self.mutant:
            self.synced = True
            self.emit("sync")
        elif self.phase == "pr":
            self.emit("ledger")

    def _open_mutant(self):
        if self.mutant and self.mutant.done:
            self._close_mutant()
        if not self.mutant:
            self.mutant = Mutant()
            self.phase = "loop"
            self.emit("pick")

    def _close_mutant(self):
        if self.mutant and self.mutant.done:
            self.emit("stage")
            self.mutant = None

    def _branch(self, branch):
        if self.mutant.branch is None:
            self.mutant.branch = branch
            self.emit(branch)

    def _inferred_branch(self):
        if self.mutant.moved:
            return "move"
        if self.mutant.removed or self.mutant.checked:
            return "dead"
        return "test"

    def _start_verify(self, outcome=None):
        self._open_mutant()
        self._branch(BRANCH_OF_OUTCOME.get(outcome) or self._inferred_branch())
        if not self.mutant.verifying:
            self.mutant.verifying = True
            self.emit("verify")

    def _skip(self):
        if self.mutant and not self.mutant.done:
            self._branch("skip")
            self.mutant.done = True
            self.handled += 1

    def _on_ledger_skip(self, _):
        self._skip()

    def _on_report(self, _):
        if self.phase == "setup":
            self.emit("report")

    def _on_tracker(self, _):
        self._tracker()

    def _on_clock(self, _):
        if self.phase in ("setup", "loop") and self.mutant is None and (self.synced or self.handled):
            self._open_mutant()

    def _on_search(self, _):
        if self.phase not in ("setup", "loop"):
            return
        self._open_mutant()
        if not self.mutant.traced:
            self.mutant.traced = True
            self.emit("trace")

    def _rechecks_last_mutant(self):
        """A new mutant starts with a pick (clock, search, test edit); a bare re-run re-checks the last one."""
        return self.mutant is None and self.handled > 0

    def _on_stryker(self, _):
        if self.phase in ("setup", "loop") and not self._rechecks_last_mutant():
            self._start_verify()

    def _on_check(self, _):
        if self.mutant:
            self.mutant.checked = True

    def _on_verify(self, matched):
        if self.phase not in ("setup", "loop") or self._rechecks_last_mutant():
            return
        outcome = OUTCOME_RE.search(matched)
        self._start_verify(outcome.group(1) if outcome else None)
        if not self.mutant.done:
            self.mutant.done = True
            self.handled += 1
            self.emit("kill")

    def _on_remove(self, matched):
        paths = matched.split()[2:]
        if self.mutant and any(self.layout.is_source(p) and not self.layout.is_test(p) for p in paths):
            self.mutant.removed = True

    def _on_stage(self, _):
        self._close_mutant()

    def _on_commit(self, _):
        if self.phase == "pr":
            self.emit("ledger")
        elif self.phase != "committed":
            self._close_mutant()
            self.phase = "committed"
            self.emit("commit")

    def _on_pr_create(self, _):
        self.phase = "pr"
        self.emit("pr")

    def _on_pr_edit(self, _):
        if self.phase == "pr":
            self.emit("ledger")


def read_new_entries(path, offset):
    """Complete JSON lines appended after offset, and the offset after the last one read."""
    with open(path, "rb") as stream:
        stream.seek(offset)
        chunk = stream.read()
    end = chunk.rfind(b"\n") + 1
    entries = []
    for line in chunk[:end].splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries, offset + end


def is_run(path):
    if "fix-mutants" not in path.read_text(encoding="utf-8", errors="replace"):
        return False
    feed = Feed(LAYOUT)
    entries, _ = read_new_entries(path, 0)
    return any(feed.push(entry) and feed.started for entry in entries)


def newest_run(root):
    candidates = sorted(Path(root).rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return next((path for path in candidates[:RUN_SEARCH_LIMIT] if is_run(path)), None)


def events_of(path):
    feed = Feed(LAYOUT)
    entries, _ = read_new_entries(path, 0)
    return [event for entry in entries for event in feed.push(entry)]


LAYOUT = Layout()


class FeedHandler(BaseHTTPRequestHandler):
    transcript = None

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/board.html"):
            self._send(BOARD.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/health":
            path = self._path()
            self._send(json.dumps({"transcript": str(path) if path else None}).encode(), "application/json")
        elif url.path == "/events":
            self._stream(query.get("mode", ["live"])[0], float(query.get("speed", ["30"])[0]))
        else:
            self.send_error(404)

    def _path(self):
        return Path(self.transcript) if self.transcript else newest_run(PROJECTS)

    def _send(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _event(self, event):
        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    def _stream(self, mode, speed):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            path = self._path()
            self._event({"step": "meta", "mode": mode, "transcript": path.name if path else None})
            if path is None:
                self._event({"step": "say", "say": "No fix-mutants run found yet."})
            elif mode == "replay":
                self._replay(path, speed)
            else:
                self._live(path)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _replay(self, path, speed):
        previous = None
        for event in events_of(path):
            if previous is not None and event["t"] is not None:
                time.sleep(min(max(event["t"] - previous, 0) / speed, MAX_REPLAY_GAP_SECONDS))
            previous = event["t"] if event["t"] is not None else previous
            self._event(event)
        self._event({"step": "end"})

    def _live(self, path):
        feed, offset, quiet = Feed(LAYOUT), 0, 0.0
        entries, offset = read_new_entries(path, offset)
        for entry in entries:
            for event in feed.push(entry):
                self._event({**event, "past": True})
        self._event({"step": "now", "t": time.time()})
        while True:
            time.sleep(POLL_SECONDS)
            entries, offset = read_new_entries(path, offset)
            events = [event for entry in entries for event in feed.push(entry)]
            for event in events:
                self._event(event)
            quiet = 0.0 if events else quiet + POLL_SECONDS
            if quiet >= HEARTBEAT_SECONDS:
                self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
                quiet = 0.0

    def log_message(self, *args):
        return


def serve(port, transcript, open_browser):
    FeedHandler.transcript = transcript
    server = ThreadingHTTPServer(("127.0.0.1", port), FeedHandler)
    url = f"http://127.0.0.1:{port}/"
    print(f"fix-mutants board: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    serve_parser = commands.add_parser("serve", help="serve the board and its live feed")
    serve_parser.add_argument("--port", type=int, default=8766)
    serve_parser.add_argument("--transcript", help="transcript to follow (default: the newest fix-mutants run)")
    serve_parser.add_argument("--open", action="store_true", help="open the board in the browser")
    events_parser = commands.add_parser("events", help="print the board steps of a transcript")
    events_parser.add_argument("transcript")
    for sub in (serve_parser, events_parser):
        sub.add_argument("--profile", help="project profile JSON (default: nearest .fix-mutants/profile.json)")
    args = parser.parse_args()
    global LAYOUT
    profile = args.profile or find_profile()
    LAYOUT = Layout.from_profile(profile) if profile else Layout()
    if args.command == "serve":
        serve(args.port, args.transcript, args.open)
    else:
        for event in events_of(Path(args.transcript)):
            print(json.dumps(event, ensure_ascii=False))


if __name__ == "__main__":
    main()
