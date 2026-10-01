# The project profile (`.fix-mutants/`)

The skill core knows nothing about a stack or a project. Everything specific lives in `.fix-mutants/` at the project root
(or at the project's folder inside a monorepo). `scripts/init_profile.py` generates it; after that it belongs to the project.

| File                   | Role                                                                                              |
| ---------------------- | ------------------------------------------------------------------------------------------------- |
| `profile.json`         | Read by `mutant_checks.py` (below)                                                                |
| `PROFILE.md`           | Everything else the agent must follow (sections below)                                            |
| `report-fetch.md`      | How to obtain and verify the mutation report                                                      |
| `MUTATION-TRACKING.md` | The ledger: `🟢 Fixed`, `⚪ Resolved-incidentally`, `🟡 Skipped`, `🔴 Regressed`, score trend, sync log, execution history |

## `profile.json`

All paths are relative to the **git root**, also for a project that lives in a sub-folder.

| Key                     | Meaning                                                                                                          |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `production_root`       | Root of the mutated project; the report's `projectRoot` must be it or a folder containing it                      |
| `test_roots`            | Roots of the test projects allowed in the report's `testFiles`, and by the test-only gate                         |
| `report_schema_version` | `schemaVersion` of the raw [mutation-testing-elements](https://github.com/stryker-mutator/mutation-testing-elements) report: `"2"` Stryker.NET, `"1.0"` StrykerJS 8 (check yours) |
| `declaration_pattern`   | Regex with one capture group naming a type/function declaration; a move must keep every captured name            |
| `gate_allow`            | Extra paths the test-only gate accepts (default: the `.fix-mutants/` folder, coverage baselines, snapshots…)     |

## `PROFILE.md` sections

1. **Scope** — production and test projects, mutation tool, tracker, working directory
2. **Report source** — pointer to `report-fetch.md`
3. **Environment setup** — toolchain activation, one-time restores
4. **Mutation command** — the exact scoped command, its working directory, pitfalls, cleanup and evidence rules
5. **Test-only gate** — `mutant_checks.py gate`, or the project's own command
6. **Layers and misplaced code** — what counts as a real caller, where misplaced code moves
7. **Caller search** — untruncated production/test searches for the stack
8. **Build-forced edits in moves** — edits a compiler/linter forces when code changes project
9. **Conventions** — test conventions, commit scope, PR title rules

The generated layers section is generic: **edit it** to name the project's layers. That is the one place the skill cannot
guess.

## Report order and integrity

`mutant_checks.py baseline` turns a raw report into `{mutants: [...alive only...], counts, source.sha, report_sha256}` —
array order is the "reported alive" order. If the project already publishes its report (CI artifact, release asset, a
branch), replace `report-fetch.md` with the fetch + checksum steps for that source; the rest is unchanged.

## Supporting another tool

Any tool that writes a mutation-testing-elements JSON report works (Stryker.NET, StrykerJS, Stryker4s, Pitest with its
elements reporter…). Run `init_profile.py --stack generic`, fill the TODOs (scoped command, schema version, caller search) and
check the first `baseline` + `verify` round-trip on a throwaway mutant. Tools with another report format (e.g. mutmut,
cosmic-ray) need a converter to that schema first.
