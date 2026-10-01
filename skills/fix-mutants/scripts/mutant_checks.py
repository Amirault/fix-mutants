#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROFILE_RELATIVE = Path(".fix-mutants") / "profile.json"
ALIVE = {"Survived", "NoCoverage"}
PRODUCTION = Path()
TEST_ROOTS = []
GATE_ALLOW = []
SCHEMA_VERSION = "2"
DECLARATIONS = ""


def use_profile(path):
    """Load a project profile (see references/profile.md) into the module settings."""
    global PRODUCTION, TEST_ROOTS, SCHEMA_VERSION, DECLARATIONS
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    PRODUCTION = Path(profile["production_root"])
    TEST_ROOTS = [Path(root) for root in profile["test_roots"]]
    SCHEMA_VERSION = str(profile.get("report_schema_version", "2"))
    GATE_ALLOW[:] = [Path(path) for path in profile.get("gate_allow", [])]
    DECLARATIONS = profile["declaration_pattern"]


def find_profile(start=None, repo=None):
    """Nearest .fix-mutants/profile.json walking up from `start`, else the only one under `repo`."""
    here = Path(start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / PROFILE_RELATIVE).is_file():
            return folder / PROFILE_RELATIVE
    if repo:
        found = [
            path for path in Path(repo).resolve().rglob(str(PROFILE_RELATIVE))
            if not {"node_modules", ".git"}.intersection(path.parts)
        ]
        if len(found) == 1:
            return found[0]
        if found:
            raise ValueError("several profiles found, pass --profile: " + ", ".join(map(str, found)))
    raise ValueError("no .fix-mutants/profile.json found: run scripts/init_profile.py first")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def git(repo, *arguments):
    return subprocess.check_output(
        ["git", "--no-pager", *arguments], cwd=repo, stderr=subprocess.PIPE
    ).decode("utf-8-sig")


def inside(root, name):
    path = (Path(root) / name).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError(f"path outside expected root: {name}")
    return path


def staged_source(repo, name):
    source = inside(repo, name).read_text(encoding="utf-8-sig")
    if not source.strip() or source != git(repo, "show", f":{name}"):
        raise ValueError("source must be nonempty and match the staged version")
    return source


def check_move(repo, base, target, destination):
    if not destination or inside(repo, destination).is_relative_to((Path(repo) / PRODUCTION).resolve()):
        raise ValueError("move destination must be outside the production scope")
    changed = git(
        repo, "diff", "--cached", "--no-renames", "--diff-filter=AM", "--name-only",
        base, "--", destination,
    )
    if destination not in changed.splitlines():
        raise ValueError("move destination must be changed in the staged diff")
    original = git(repo, "show", f"{base}:{target}")
    names = set(re.findall(DECLARATIONS, original))
    if not names or not names.issubset(re.findall(DECLARATIONS, staged_source(repo, destination))):
        raise ValueError("move destination must retain the original declarations")


def check_change(repo, base, target, outcome, *, destination=None, removed_code=None):
    if removed_code is not None and outcome != "removed":
        raise ValueError("removed code is only valid for a removal")
    source = inside(repo, target)
    if not source.is_relative_to((Path(repo) / PRODUCTION).resolve()):
        raise ValueError("target must be inside the production scope")
    if outcome == "test":
        return
    if outcome == "moved":
        check_move(repo, base, target, destination)
    if outcome == "removed" and removed_code is not None:
        original = git(repo, "show", f"{base}:{target}")
        if not removed_code.strip() or removed_code not in original:
            raise ValueError("removed code must occur in the base revision")
        if re.sub(r"\s+", "", removed_code) in re.sub(r"\s+", "", staged_source(repo, target)):
            raise ValueError("removed code still exists")
        return
    if source.exists() or (Path(repo) / target).is_symlink():
        raise ValueError("removed source still exists")
    deleted = git(repo, "diff", "--cached", "--no-renames", "--diff-filter=D", "--name-only", base, "--", target)
    if target not in deleted.splitlines():
        raise ValueError("source deletion must be staged")


def check_removed_span(repo, base, target, removed_code):
    if removed_code is None:
        return
    original = git(repo, "show", f"{base}:{target['path']}")
    lines = original.splitlines(keepends=True)
    offsets = []
    for boundary in ("start", "end"):
        position = target["location"][boundary]
        line, column = position["line"], position["column"]
        if not 1 <= line <= len(lines) or not 1 <= column <= len(lines[line - 1]) + 1:
            raise ValueError("target span is outside the base source")
        offsets.append(sum(map(len, lines[:line - 1])) + column - 1)
    if not any(
        match.start() <= offsets[0] < offsets[1] <= match.end()
        for match in re.finditer(re.escape(removed_code), original)
    ):
        raise ValueError("removed code must contain the target span")
    target_source = re.sub(r"\s+", "", original[offsets[0]:offsets[1]])
    current = re.sub(r"\s+", "", staged_source(repo, target["path"]))
    if not target_source or target_source in current:
        raise ValueError("target span still exists; removal cannot be confirmed")


def report_files(report, repo):
    project = inside(repo, report["projectRoot"])
    if project != (Path(repo) / PRODUCTION).resolve():
        raise ValueError("report projectRoot must be the current production project checkout")
    return {inside(project, name): data for name, data in report["files"].items()}


def report_tests(report, repo):
    inventory = report.get("testFiles", {})
    if not inventory:
        raise ValueError("test inventory is empty")
    roots = [(Path(repo) / root).resolve() for root in TEST_ROOTS]
    tests = []
    for name, data in inventory.items():
        path = (Path(report["projectRoot"]) / name).resolve()
        if not any(path.is_relative_to(root) for root in roots):
            raise ValueError("test inventory contains a foreign test project")
        tests.extend(data.get("tests", []))
    return tests


def same_replacement(mutant, target):
    """Tell apart mutants sharing location and mutator (`>= 5` -> `> 5` and `< 5`) by their replacement text."""
    wanted = target.get("replacement")
    return not wanted or mutant.get("replacement") in (None, wanted)


def verify_report(report, repo, target, outcome, *, new_test=None, removed_code=None):
    if str(report.get("schemaVersion")) != SCHEMA_VERSION:
        raise ValueError(f"expected a raw mutation-testing-elements schemaVersion {SCHEMA_VERSION} report")
    files = report_files(report, repo)
    tests = report_tests(report, repo)
    source = inside(repo, target["path"])
    remaining = []
    for path, data in files.items():
        for mutant in data["mutants"]:
            if path != source and mutant["status"] != "Ignored":
                raise ValueError(f"active mutant outside scope: {path}")
            if path == source and mutant["status"] in ALIVE:
                remaining.append(mutant)
    result = {"outcome": outcome, "alive_in_scope": len(remaining), "remaining": remaining}
    if outcome in {"removed", "moved"} and not removed_code:
        if source in files:
            raise ValueError("report still contains the deleted source")
        return result
    data = files.get(source)
    if not data or data["source"] != source.read_text(encoding="utf-8-sig"):
        raise ValueError("report source differs from current source")
    matches = [
        mutant for mutant in data["mutants"]
        if mutant["location"] == target["location"] and mutant["mutatorName"] == target["mutator"]
        and same_replacement(mutant, target)
    ]
    if outcome == "removed":
        if matches:
            raise ValueError("target mutation still exists in the report")
        if removed_code in data["source"]:
            raise ValueError("report still contains removed code")
        return result
    if len(matches) != 1 or matches[0]["status"] != "Killed":
        raise ValueError("target must uniquely match location/mutator and be Killed")
    killers = {
        str(test["id"]) for test in tests
        if new_test and (test["name"] == new_test or test["name"].endswith("." + new_test))
    }
    if not killers or not killers.intersection(map(str, matches[0].get("killedBy", []))):
        raise ValueError("target was not killed by the named new test")
    return result


def select_target(baseline, mutant_id):
    matches = [m for m in baseline["mutants"] if str(m["id"]) == str(mutant_id)]
    if len(matches) != 1 or matches[0]["status"] not in ALIVE:
        raise ValueError("select exactly one alive mutant from the verified baseline")
    return matches[0]


UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc(value):
    return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)


def humanize(seconds):
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [f"{days}d", f"{hours}h", f"{minutes}m", f"{secs}s"]
    first = next(index for index, value in enumerate((days, hours, minutes, secs)) if value or index == 3)
    return " ".join(parts[first:])


def duration(start, end):
    seconds = int((parse_utc(end) - parse_utc(start)).total_seconds())
    if seconds < 0:
        raise ValueError("end must not be before start")
    return {"seconds": seconds, "human": humanize(seconds)}


def check_test_only(repo):
    """The staged diff may touch only test roots, the .fix-mutants folder and profile-allowed paths."""
    staged = git(
        repo, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMRDT", "--no-renames"
    ).split("\0")
    staged = [name for name in staged if name]
    if not staged:
        raise ValueError("staged diff is empty")
    allowed = [*TEST_ROOTS, Path(".fix-mutants"), *GATE_ALLOW]
    outside = [
        name for name in staged
        if not any(Path(name).is_relative_to(root) for root in allowed)
    ]
    if outside:
        raise ValueError("not test-only, production or other files staged: " + ", ".join(outside))
    return staged


def make_baseline(repo, report_path, now=None):
    """Normalize a raw mutation-testing-elements report into the baseline shape the other commands read."""
    raw = Path(report_path).read_bytes()
    report = json.loads(raw)
    root = Path(repo).resolve()
    project = Path(report.get("projectRoot") or root)
    counts, mutants = {}, []
    for name, data in report["files"].items():
        path = (project / name).resolve()
        relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else name
        for mutant in data["mutants"]:
            counts[mutant["status"]] = counts.get(mutant["status"], 0) + 1
            if mutant["status"] in ALIVE:
                mutants.append({
                    "id": mutant["id"],
                    "path": relative,
                    "mutator": mutant["mutatorName"],
                    "location": mutant["location"],
                    "status": mutant["status"],
                    "replacement": mutant.get("replacement"),
                })
    try:
        sha = git(root, "rev-parse", "HEAD").strip()
    except (OSError, subprocess.CalledProcessError):
        sha = None
    counts["remaining"] = len(mutants)
    return {
        "generated_at": (now or datetime.now(timezone.utc)).strftime(UTC_FORMAT),
        "source": {"sha": sha},
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "scope": {"project": report.get("projectRoot"), "mutate": None},
        "counts": counts,
        "mutants": mutants,
    }


def describe_mutants(repo, baseline, limit=None):
    """Alive mutants in report order, each with the original code at its location."""
    rows = []
    for index, mutant in enumerate(baseline["mutants"]):
        try:
            lines = (Path(repo) / mutant["path"]).read_text(encoding="utf-8-sig").splitlines()
            start, end = mutant["location"]["start"], mutant["location"]["end"]
            if start["line"] == end["line"]:
                original = lines[start["line"] - 1][start["column"] - 1:end["column"] - 1]
            else:
                original = lines[start["line"] - 1][start["column"] - 1:] + " …"
        except (OSError, IndexError):
            original = "?"
        rows.append({
            "index": index,
            "id": mutant["id"],
            "where": f'{mutant["path"]}:{mutant["location"]["start"]["line"]}',
            "mutator": mutant["mutator"],
            "status": mutant["status"],
            "original": original.strip(),
            "mutated": mutant.get("replacement"),
        })
    return rows[:limit]


def parser():
    cli = argparse.ArgumentParser(description="Check mutant outcomes without creating files.")
    cli.add_argument("--profile", help="project profile JSON (default: nearest .fix-mutants/profile.json)")
    commands = cli.add_subparsers(dest="action", required=True)
    for action in ("check", "verify"):
        check = commands.add_parser(action)
        for option in ("repo", "base", "baseline", "mutant-id"):
            check.add_argument("--" + option, required=True)
        check.add_argument("--outcome", choices=("test", "removed", "moved"), required=True)
        check.add_argument("--moved-to")
        check.add_argument("--removed-code")
        if action == "verify":
            check.add_argument("--report", required=True)
            check.add_argument("--new-test")
    gate = commands.add_parser("gate", help="Fail unless the staged diff only touches tests and the tracker.")
    gate.add_argument("--repo", required=True)
    baseline = commands.add_parser("baseline", help="Normalize a raw report into a baseline (alive mutants only).")
    baseline.add_argument("--repo", required=True)
    baseline.add_argument("--report", required=True)
    baseline.add_argument("--out", required=True)
    listing = commands.add_parser("list", help="List the alive mutants of a baseline, in report order.")
    listing.add_argument("--repo", required=True)
    listing.add_argument("--baseline", required=True)
    listing.add_argument("--limit", type=int)
    elapsed = commands.add_parser("duration", help="Print the human-readable time between two UTC timestamps.")
    elapsed.add_argument("--start", required=True, help="UTC, e.g. 2026-09-30T08:15:02Z")
    elapsed.add_argument("--end", required=True, help="UTC, e.g. 2026-09-30T08:53:31Z")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == "baseline":
            result = make_baseline(args.repo, args.report)
            Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"remaining": result["counts"]["remaining"], "report_sha256": result["report_sha256"]}))
            return 0
        if args.action == "list":
            for row in describe_mutants(args.repo, read_json(args.baseline), args.limit):
                print(json.dumps(row, ensure_ascii=False))
            return 0
        if args.action == "gate":
            use_profile(args.profile or find_profile(repo=args.repo))
            print(json.dumps({"test_only": True, "staged": check_test_only(args.repo)}))
            return 0
        if args.action in {"check", "verify"}:
            use_profile(args.profile or find_profile(repo=args.repo))
        if args.action == "duration":
            print(json.dumps(duration(args.start, args.end)))
            return 0
        target = select_target(read_json(args.baseline), args.mutant_id)
        check_change(
            args.repo, args.base, target["path"], args.outcome,
            destination=args.moved_to, removed_code=args.removed_code,
        )
        check_removed_span(args.repo, args.base, target, args.removed_code)
        if args.action == "check":
            print(json.dumps({"phase": "preflight", "outcome": args.outcome}))
            return 0
        print(json.dumps(verify_report(
            read_json(args.report), args.repo, target, args.outcome,
            new_test=args.new_test, removed_code=args.removed_code,
        ), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"mutant-checks: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
