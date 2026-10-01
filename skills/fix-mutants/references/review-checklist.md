# Step 6 — independent review prompt

Launch a fresh independent reviewer using the available delegation mechanism and wait for its verdict.
Keep it read-only: no edits, staging or parallel mutation/build runs. It must have **no prior context** from the implementation —
brief it fully so it reviews the diff cold, the way a human reviewer would.

## Prompt template

```
Independently review a mutation-testing fix in <project> before it gets committed. You were not
involved in writing it — read the diff and the codebase yourself; do not take the summary below on faith.

Mutant(s) targeted: <id, file, class/method, mutator, original code, mutated code — one block per mutant>

Path taken: <"test" | "last-resort production code change">
<if last-resort: paste the evidence gathered — grep results, git log -S findings, library/native check>

Diff to review: <git diff / file paths changed, or point the agent at `git diff main...HEAD`>
Current mutation report: <path to the final raw JSON report>
Validation: <build/test/gate results, exact mutation command and working directory>
Project profile: <path to profiles/<project>/PROFILE.md — read it: scope, layers, conventions, gate>
Inspect the code/report yourself. Do not start concurrent mutation runs in the implementation checkout.

Check, and report a clear verdict on each:

1. COHERENCE — does the new test (or code removal) actually kill the mutant for the right reason?
   For a test: does it fail specifically because of the mutated branch, not by accident? Would it
   still pass if the mutation were reverted (i.e. is it a real assertion of correct behaviour, not a
   tautology)? For a code removal: is the evidence of unreachability actually conclusive — did the
   reviewing agent independently re-check (grep, git log) rather than trust the stated evidence?
   Include implicit consumers: the implicit consumers the profile lists (DI, reflection, serialization, generated code…).
2. RIGHT LAYER — is the test driven through the correct adapter/use-case public entry point per the
   profile's test conventions, or does it construct a leaf type in isolation (wrong layer, tests an
   implementation detail)? Independently grep every real (non-test) call site of the mutated member —
   confirm at least one actually reads its value. A class being directly `new`'d elsewhere does not by
   itself justify testing it in isolation if the specific mutated member has no real reader. Also check
   the mutated code itself belongs in the production scope: if no real caller lives there, or it is adapter
   plumbing the profile names (cloud clients, connection-string parsing, config binding), flag it as misplaced — a test
   in the scoped test project would lock that in; the fix is a move (Step 4 → Misplaced code) — unless no real
   caller exists in any layer, in which case it is dead and removal is the fix.
3. NECESSITY AND SCOPE — exactly one new test (or the minimal code removal) for exactly the
   requested mutant(s)? No existing test/fixture/helper modified? No unrelated mutant "fixed" as a
   side effect being claimed as intentional? No unrelated files touched (build config, mutation
   config, other production code)?
4. LAST-RESORT DISCIPLINE — if production code changed, was it truly unavoidable (a meaningful test
   was actually impossible, not just inconvenient)? Is it the smallest change — the dead code plus only
   what must go with it to build, orphans and cleanup left to the tracking sync log, a move kept as-is? No
   behaviour-changing fix bundled in (those must be skipped, not fixed)?
5. CODEBASE CONVENTIONS — the profile's test conventions (structure, naming, categories, assertion
   library), the repository's language rules, no dead/commented code left behind, the project's
   AGENTS.md craftsmanship rules.
6. VALIDATION — clean build, targeted tests pass, scoped mutation result and test-only gate are
   consistent with the path taken. Verify tool versions and command cwd.
   Re-run the read-only check/verify commands with the same arguments.
   A removed file must be absent on disk and staged as D (`git diff --cached --no-renames`), not zero
   bytes. Its final report entry must be absent, not `source: ""`. A removed member's original region
   must actually be gone, not reformatted; a move needs a nonempty staged destination outside
   the production scope, and is out-of-scope, never a test kill. For every outcome, check `testFiles` lists only
   the scoped test project (otherwise the mutation tool ran unscoped, e.g. solution mode —
   PROBLEM). For the test path only, confirm the new test appears in the target mutant's `killedBy`. Note: a scoped
   `--mutate` run's JSON report still lists mutants for every analyzed file in the project, not just
   the mutated one — anything outside the `--mutate` glob shows status `Ignored` ("Removed by mutate
   filter" in the run log). Seeing other files' mutants in the report is expected and is not evidence
   of an unscoped run; only flag a PROBLEM here if a mutant outside scope has a status other than
   `Ignored` (e.g. it was actually `Killed`/`Survived`/tested).
   Confirm any narrower requested line/range filter independently; the mechanical scope gate is file-level.
   Confirm the mutation tool was rerun after any relevant source/test/build-input changes. Broader mandatory hook suites are
   separate from scoped task-directed validation; never ask to bypass them.
7. MEASUREMENT — one attempt for the selected target, not one timing per incidental sibling.
   Check baseline/target identity, UTC start, agent and exact model metadata; unavailable fields must
   say unknown. Return your own runtime-reported model ID if exposed, otherwise unknown. The lead
   records UTC end and the human-readable fix duration in Execution history only after this review and before commit.
   The request → PR duration cannot exist yet (no PR): the `Request → PR` cell must be `pending`, not guessed.
   Retries/waits count; setup before selection and commit/PR/merge work do not. Flag mixed-model
   attempts and missing measurements rather than inferring metadata from branding or timestamps.

Report: a verdict per point (OK / PROBLEM, with the specific line/reason for any PROBLEM), and one
overall recommendation — ready to commit, or fix first (with what to fix).
```

## Acting on the result

- All OK → record the attempt's end time and metrics, then proceed to Step 7 (commit/PR),
  including the review outcome in the PR description.
- Any PROBLEM → fix it, then re-run this review before committing (don't skip re-review after a fix).
- Sub-agent disagrees but you have stronger, concrete evidence it missed → say so explicitly to the
  user rather than silently overriding the finding.
