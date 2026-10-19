# Step 4 — Production code change (last resort)

Read it before proposing any production change, including a move of misplaced code.

Before proposing any production change, gather evidence:

1. **Exhaustive reachability check** — search the _whole_ repository (not just the mutant's own project) for real
   construction/call sites of the mutated code path, with the profile's _Caller search_.
2. **History check** — `git log -S"<construct>"` / `git log -G` on the file: was it ever reachable? If yes, find and cite
   the commit where it became orphaned (a deleted caller, a removed provider, etc.).
3. **Third-party/native check** — if the code wraps or mirrors a framework/library API, verify by inspecting that
   library's actual types/behaviour (load the package, list its types, or run a tiny probe project) — never assume names
   or semantics.

Then **decide and proceed — don't ask**. Make the smallest change that removes the dead branch: the target code plus only
what must go with it for the build to pass (e.g. the dead callers that construct a removed type, imports that only served
it). Anything the removal merely orphans, and any extra cleanup, goes to the tracker's sync log, not the diff. Never make
a change that just makes the mutant harder to express without addressing why it's unreachable; never fix a
behaviour-changing defect here (see _Never ask_ → `skipped`). The test-only gate will correctly fail for this path (by
design) — do not bypass it silently; the PR must flag that production code changed, why, and the evidence above, so the
reviewer can reject it.

Stage the change and run the mechanical `check` before building: whole-file removal requires physical absence and staged
deletion; member removal requires an explicit original code excerpt, absent from the staged/current source. Re-check
implicit consumers (the profile lists the stack's: DI, reflection, serialization, generated code…); the script does not
prove runtime unreachability. If `check` fails with "target span still exists" because the mutated text recurs in a kept
member, never broaden the excerpt — follow `decision-rules.md` → _Non-unique spans_. Dead code still referenced by tests
is removed with them (all-or-nothing tests deleted, mixed tests adapted); code referenced only by test helpers moves next
to its usage in the test project (→ _Tested dead code and test-only helpers_).

**Misplaced code** (from Step 3.0): move the code to the layer its callers live in (the profile names the destination),
with its test moved to the matching test project. Move it **as-is** — namespaces and imports only, plus the build-forced
edits the profile lists under _Build-forced edits in moves_ (name each in the commit body) — no trimming or cleanup
(those go to the tracker's sync log). If the move would force edits to an existing test beyond the build-forced ones, do
not move: kill the mutant in place (Step 3) and record a `Blocked move:` note (→ _Blocked move_). Its mutants leave the
mutation scope: record them in the ledger as `resolved` ("moved out of scope, not killed") and say so in the PR.

If the reachability gap surfaces while working, nothing is committed yet: unstage and delete your own new test
(`git restore --staged --worktree <file>`, or `git rm -f` for a new file) and continue with this step. Only if a previous
run already pushed a commit for this PR, `git revert` it (no force-push, no history rewrite) and update the existing PR.
