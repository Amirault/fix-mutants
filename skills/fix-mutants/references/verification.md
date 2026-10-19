# Step 5 — Scoped mutation re-verification

Read it before the first `verify` of a session.

For every target, run `mutant_checks.py verify` against the final raw mutation report (Step 3 can supply it without a
redundant rerun):

- **Test:** match file/location/operator, require `Killed` and the named new test in `killedBy`.
- **`verify` output:** success is the **exit code 0** only — it prints the remaining-mutants JSON (large), no `OK` line.
  It fails with `target must uniquely match location/mutator` when another mutant sits at the same location with the same
  mutator (typical for an equivalent mutant): that mutant is `skipped` (`equivalent`), not a failed fix.
- **Removal:** prove the staged source deletion/code removal and its absence from the report. A deleted file retained as
  `source: ""` is a failure. No mutation score is expected when nothing remains to mutate.
- **Move:** require source deletion and a staged nonempty destination outside the production scope; report "out of
  scope", never "killed". Review that the move is otherwise as-is.
- All reported mutants outside the targeted file must be `Ignored`; `testFiles` must be nonempty and belong only to the
  profile's test scope. Use the latest successful run; rerun the mutation tool if source, tests or relevant build inputs
  changed.

Match the target mutant between the baseline report and this run by **(file, location line/column, mutator name)**, never
by `id` alone — mutation tools assign `id`s per run and they are not stable across runs.

After the final mutation run, do the profile's cleanup (stale mutant binaries must not survive), then, once all targets
are done, a clean analyzer-enabled build and unit/spec tests (Step 7); per target only the new test and the mutation run
are needed. Repeat the cleanup if another mutation run occurs; do not repeat unchanged validations merely to satisfy two
step headings.

**Order constraints.** Run `verify` for a target right after its mutation run, before editing that same source file
again (it refuses a report older than the file); edits to other files do not matter. `check`/`verify` read the index: run
them, and Step 6's re-runs, **before** the commit, after staging everything (a formatter run by the build can reformat
files, so the index must match the tree). A later mutation run includes the tests of earlier targets: `killedBy` must
still name the new test of the target being verified.

**Never delete the raw report output** (observed once: over-eager cleanup destroyed the raw report, the independent
reviewer could not re-run `verify`, and the fix required a full scoped re-run). The raw JSON of the final successful run
is the evidence Steps 5 and 6 rest on — keep it in place and copy it outside the worktree with its sha256 recorded in the
sync log, so a later cleanup cannot invalidate the PR's claims.

Record alive-mutant counts before/after in the mutated scope, and the list of any mutants still alive there.
