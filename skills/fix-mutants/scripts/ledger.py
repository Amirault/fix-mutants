#!/usr/bin/env python3
"""Read and write the fix-mutants ledger: one JSON object per line, validated on every write."""
import argparse
import json
import re
import sys
from pathlib import Path

LEDGER_RELATIVE = Path(".fix-mutants") / "ledger.jsonl"
STATUSES = ("fixed", "resolved", "skipped", "queued", "regressed", "superseded")
CATEGORIES = ("real-defect", "unclaimable", "equivalent", "unobservable")
REQUIRED = ("file", "lines", "mutator", "status", "pr", "note")
OPTIONAL = ("category", "commit")
PENDING = "pending"


def problems(entry):
    found = [f"missing field {name}" for name in REQUIRED if name not in entry]
    found += [f"unknown field {name}" for name in entry if name not in REQUIRED + OPTIONAL]
    for name in ("file", "lines", "mutator", "note"):
        if name in entry and not (isinstance(entry[name], str) and entry[name].strip()):
            found.append(f"{name} must be a non-empty string")
    if entry.get("status") not in STATUSES:
        found.append(f"status must be one of {', '.join(STATUSES)}")
    if entry.get("status") == "skipped" and entry.get("category") not in CATEGORIES:
        found.append(f"category must be one of {', '.join(CATEGORIES)} on a skipped row")
    if entry.get("status") != "skipped" and "category" in entry:
        found.append("category is only allowed on a skipped row")
    pr = entry.get("pr")
    if not (pr is None or pr == PENDING or (isinstance(pr, int) and not isinstance(pr, bool) and pr > 0)):
        found.append(f"pr must be a PR number, {PENDING!r} or null")
    if "commit" in entry and not (isinstance(entry["commit"], str) and re.fullmatch(r"[0-9a-f]{7,40}", entry["commit"])):
        found.append("commit must be a hexadecimal sha")
    return found


def find_ledger(start=None):
    """The ledger of the nearest .fix-mutants folder, walking up from `start` (default: the working directory)."""
    origin = Path(start or Path.cwd()).resolve()
    for folder in (origin, *origin.parents):
        if (folder / LEDGER_RELATIVE.parent).is_dir():
            return folder / LEDGER_RELATIVE
    raise ValueError("no .fix-mutants folder found: run scripts/init_profile.py first, or pass --ledger")


def load(path):
    entries = []
    if not Path(path).exists():
        return entries
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"row {number}: not JSON ({error.msg})") from error
        if not isinstance(entry, dict):
            raise ValueError(f"row {number}: not a JSON object")
        entries.append(entry)
    return entries


def validate(entries):
    found = [f"row {number}: {problem}" for number, entry in enumerate(entries, start=1) for problem in problems(entry)]
    if found:
        raise ValueError("\n".join(found))


def save(path, entries):
    validate(entries)
    text = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
    Path(path).write_text(text, encoding="utf-8")


def names_file(entry, file):
    return re.search(r"(^|[/,{ ])" + re.escape(file), entry.get("file", "")) is not None


def find(entries, file=None, status=None, category=None):
    for number, entry in enumerate(entries, start=1):
        if file and not names_file(entry, file):
            continue
        if status and entry.get("status") != status:
            continue
        if category and entry.get("category") != category:
            continue
        yield {"row": number, **entry}


def update(entries, number, fields):
    if not 1 <= number <= len(entries):
        raise ValueError(f"row {number} does not exist (the ledger has {len(entries)} rows)")
    merged = {**entries[number - 1], **fields}
    entries[number - 1] = {name: value for name, value in merged.items() if not (value is None and name in OPTIONAL)}


def fill_pr(entries, number):
    pending = [entry for entry in entries if entry.get("pr") == PENDING]
    if not pending:
        raise ValueError(f"no row has pr {PENDING!r}")
    for entry in pending:
        entry["pr"] = number


def parse_object(text):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--ledger", help="ledger file (default: the nearest .fix-mutants/ledger.jsonl)")
    commands = cli.add_subparsers(dest="action", required=True)
    commands.add_parser("validate", help="Check every row against the schema.")
    finder = commands.add_parser("find", help="Print matching rows as JSON lines, each with its row number.")
    finder.add_argument("--file", help="file name or path end, matched from a path boundary")
    finder.add_argument("--status", choices=STATUSES)
    finder.add_argument("--category", choices=CATEGORIES)
    adder = commands.add_parser("add", help="Append one row.")
    adder.add_argument("row", help="the row as a JSON object")
    updater = commands.add_parser("update", help="Merge fields into one row; null removes an optional field.")
    updater.add_argument("number", type=int, help="row number, as printed by find")
    updater.add_argument("fields", help="the fields as a JSON object")
    filler = commands.add_parser("fill-pr", help=f"Replace every pr {PENDING!r} with the PR number.")
    filler.add_argument("number", type=int)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        path = args.ledger or find_ledger()
        entries = load(path)
        if args.action == "validate":
            validate(entries)
        elif args.action == "find":
            for match in find(entries, args.file, args.status, args.category):
                print(json.dumps(match, ensure_ascii=False))
        else:
            if args.action == "add":
                entries.append(parse_object(args.row))
            elif args.action == "update":
                update(entries, args.number, parse_object(args.fields))
            else:
                fill_pr(entries, args.number)
            save(path, entries)
        return 0
    except (ValueError, OSError) as error:
        print(f"ledger: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
