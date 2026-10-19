# Ledger — `.fix-mutants/ledger.jsonl`

Every mutant already examined on this project: one JSON object per line, oldest first. Answers "has this mutant been
dealt with?" in one lookup. Read and write it only through `scripts/ledger.py`: every write is validated, never edit the
file by hand.

## Fields

| Field      | Value                                                                                                                         |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `file`     | repo-relative path of the mutated file; a row may group files (`,` `+`, globs): `find` by file name, not full path            |
| `lines`    | line or range at the baseline `source.sha` where the mutant was first seen alive (`"12"`, `"22–81"`)                          |
| `mutator`  | the mutation tool's mutator name, or the group (`"4 mutants (ids 104–106, 108)"`)                                             |
| `status`   | `fixed`, `resolved`, `skipped`, `queued`, `regressed` or `superseded` (below)                                                 |
| `category` | skipped rows only, mandatory: `real-defect`, `unclaimable`, `equivalent`, `unobservable` (`decision-rules.md`)                |
| `pr`       | PR number, `"pending"` until the PR exists, or `null` (recorded without a PR)                                                 |
| `commit`   | optional, historical rows only: the merged commit (never a branch-only sha)                                                   |
| `note`     | evidence and reason in one or two sentences; starts with `Removal.` for dead code removed, `Blocked move:` for a blocked move |

Lines and ids drift between baselines: re-locate a row's mutant by `(file, mutator, code snippet)`.

## Statuses

| Status       | Meaning                                                                                              |
| ------------ | ---------------------------------------------------------------------------------------------------- |
| `fixed`      | killed by a new test or removed as dead code by a dedicated target; only once absent from the report |
| `resolved`   | gone as a side effect (sibling of a removal, moved out of scope); only once absent from the report   |
| `skipped`    | deliberately left alive, with its `category`                                                         |
| `queued`     | examined, claimable, not taken yet: the next runs' targets, in report order, path in `note`          |
| `regressed`  | was `fixed`/`resolved`, alive again in a later baseline: flag it in the PR's _Review focus_          |
| `superseded` | replaced by later rows that hold its mutants: ignore it                                              |

## Commands

`L=<skill>/scripts/ledger.py`. It finds the nearest `.fix-mutants/ledger.jsonl` walking up from the working directory;
pass `--ledger <path>` when a monorepo has several profiles.

| Task                                                        | Command                                                                                             |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Rows of a file (add folders to tell same-named files apart) | `python3 $L find --file Shop/LoyaltyDiscount.cs`                                                   |
| Target list                                                 | `python3 $L find --status queued`                                                                   |
| Record an examined mutant                                   | `python3 $L add '{"file": …, "lines": …, "mutator": …, "status": …, "pr": "pending", "note": …}'`   |
| Change a row (`row` printed by `find`)                      | `python3 $L update 108 '{"status": "fixed", "pr": "pending", "note": …}'` (`null` drops `category`) |
| Fill the PR number once the PR exists                       | `python3 $L fill-pr 42`                                                                             |
| Check the schema                                            | `python3 $L validate` (wire it into a pre-commit hook if the project has one)                       |
