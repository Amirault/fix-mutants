# Read-only mutant outcome checks

Requires Python 3.10+ (standard library only) and Git; the project's own toolchain only for the validation commands the profile gives.
The verifier reads the checkout, index, verified baseline and current raw mutation report; it prints
the result without creating files or wrapping validation commands.

## Setup

Activate the toolchain as the profile's _Environment setup_ says, then complete the baseline checksum verification in the
profile's `report-fetch.md`. Before editing, note the base commit and selected baseline ID. Replace example paths and IDs
with the actual inputs (`<profile>` = `.fix-mutants/profile.json`):

```bash
REPO="$(git rev-parse --show-toplevel)"
BASE="$(git rev-parse HEAD)"
TOOL="<path to the installed skill>/scripts/mutant_checks.py"
PROFILE="$REPO/.fix-mutants/profile.json"
```

## Before expensive validation

Stage the intended change, then check its postconditions:

```bash
python3 "$TOOL" --profile "$PROFILE" check \
  --repo "$REPO" --base "$BASE" --baseline /tmp/verified-baseline.json \
  --mutant-id 0 --outcome removed
```

- Whole-file removal requires physical absence (not empty or a dangling symlink) and staged deletion
  relative to the pre-edit base, with rename detection disabled.
- Partial removal: add `--removed-code 'exact original member/branch text'`. It must contain the
  entire target span, occur at the base revision and be absent from the nonempty staged/current
  source. Whitespace-only rewrites and a surviving original target span fail. The textual checks
  are conservative: stop on ambiguous or duplicated spans rather than broadening the excerpt.
- Move: use `--outcome moved --moved-to <repo path outside the production scope>`.
  The source must be deleted and the destination outside the production scope, nonempty, added/modified in
  the index, and retaining the original declaration names. Independently review that the body is
  relocated as-is apart from required namespace/usings; the declaration check is not a C# parser.

## After the scoped mutation run

Run build/tests/mutation directly as specified in the skill. Use the raw JSON from the latest
successful scoped mutation run, not the normalized published baseline:

```bash
python3 "$TOOL" --profile "$PROFILE" verify \
  --repo "$REPO" --base "$BASE" --baseline /tmp/verified-baseline.json \
  --mutant-id 0 --outcome removed \
  --report /path/to/current/mutation-report.json
```

Use the same removal/move arguments as the preflight check. For a test fix, use `--outcome test`
and `--new-test "exact test name from testFiles"`. Verification matches file/location/operator,
requires `Killed` plus the new test in `killedBy`, and rejects current/report source mismatches.
Deleted/moved sources must have no report entry at all, not even `source: ""`.
Partial removals must have no remaining exact target mutation.

All reported mutants outside the targeted file must be `Ignored`, and `testFiles` must be
nonempty and limited to the profile's test scope. Independently inspect narrower line/range filters.
The verifier does not track prior runs: rerun the mutation tool whenever source, tests or relevant build
inputs change, and never use a failed/older run to claim success.

Semantic reachability, implicit consumers and as-is moves still require independent review.
Record duration/model information directly in the tracker, following Steps 0, 2, 6 and 7.
Compute every duration with the script, from the repository root (it reads no repository state):

```bash
python3 "$TOOL" duration \
  --start 2026-09-30T08:15:02Z --end 2026-09-30T08:53:31Z   # {"seconds": 2309, "human": "38m 29s"}
```
