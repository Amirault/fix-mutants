# Decision rules

Rules learned from multi-mutant runs. SKILL.md points here; these are mandatory, not tips.

## Caller search — never truncated

A truncated grep once listed only test hits and made live code look dead (a helper had two real callers in another
layer). For every mutated member, search the whole monorepo **without `head`/`tail`** and split the result production vs
test, using the profile's _Caller search_ commands. Generic shape:

```bash
rg -n -g '<source glob>' -g '!<build output>' -w '<Member>' . | rg -v '<test path pattern>'   # production + tooling
rg -l -g '<source glob>' -g '!<build output>' -w '<Member>' . | rg '<test path pattern>'      # tests
```

Search the member name, not only its type: extension methods, free functions and re-exports are called without the type
name. Vendored copies and sibling projects in other namespaces are not callers, but confirm nothing outside the project
references it before discarding them. Registered-but-never-resolved services (DI, plugin registries, route tables) are not
reachable.

## What counts as a layer

The profile defines the layers (e.g. application, infrastructure, web). A caller in tooling (benchmarks, script runners,
smoke tests) or in a test project is not a real caller, so code used only there is **dead** under Step 3.0's precedence.
Editing a tooling caller is build-forced and allowed when behaviour-identical (e.g. inline the exact call the wrapper
forwarded to); editing a test, fixture or helper is not (see skip categories).

## Skip categories

Record each as status `skipped` with its `category` (`real-defect`, `unclaimable`, `equivalent`, `unobservable`) and the
concrete blocker in `note` (`references/ledger.md`). Group mutants of one member/file with the same reason into one row.

| Category     | Signal                                                                                                                                                                                        | Why not fixed                                                   |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Real defect  | The mutated code is live and wrong                                                                                                                                                            | Behaviour change — fix test-first in a dedicated PR             |
| Unclaimable  | Dead, but its span is not unique (below) and no other claimable target covers it                                                                                                              | Removal cannot be verified                                      |
| Equivalent   | The change does not alter observable behaviour (e.g. `>=` → `>` where both branches write the same value), so no test can fail; often shares its location and mutator with a killable sibling | Nothing to fix; killing it would need a behaviour-changing edit |
| Unobservable | Live code whose only effect lands where the test host cannot read it back (telemetry spans without an agent, a real cloud lease), shown by a probe                                            | No test can see it; re-check when the host gains a readback     |

_Dead but tested_, _Test-helper only_ and _Blocked move_ are **not** skips: they have a path of their own (below).

## Tested dead code and test-only helpers

Both touch existing tests, an exception to the no-edit rule that the PR must flag (⚠️ warning in the block).

**Dead but tested** — no production caller, only tests call it. Delete the code, then settle the tests:

- Every test that exists only for this behaviour (it asserts nothing else) → delete the test with the code.
- A test that also covers other behaviour (shared setup, several assertions, a parameterised case list) → keep it and
  adapt it minimally: remove only the part that reached the deleted code.

Kill type `⚠️🗑️ Dead code deleted`, plus `⚠️✏️` when a test was adapted. Name each deleted/adapted test in the PR block.

**Test-helper only** — only fixtures, fakes or helpers in test projects call it.

- Implementation that lives in the production scope but serves no production purpose → **move it to the test project,
  next to its usage**, as-is (namespaces and imports only, build-forced edits per _Build-forced edits in moves_).
  Kill type `⚠️📦 Code moved to another project`; the mutants leave the production scope (`resolved`).
- The code is also useful to production (or the test helper itself is the only thing that makes it look unused) → it is
  not test-helper-only: handle it as a normal live member (Step 3).

**Blocked move** — misplaced code whose move would force edits to existing tests beyond the build-forced ones, or cannot be
checked (member move out of a file that stays: `mutant_checks.py` only verifies whole-file moves). Do **not** take the
risky move. Kill the mutant **in place** with a new test (Step 3), through the nearest reachable entry point even if that
layer is not the ideal one. Keep the history: the ledger row is `fixed` with a note starting `Blocked move:` (what the
move would have touched and why it was too risky), and the PR block flags the code as misplaced for a later move.

## Non-unique spans

`mutant_checks.py` confirms a member removal only if the target's span text is absent from the **whole** file, so
`true`/`false`/`null` mutants are usually unclaimable when sibling members stay. Never broaden `--removed-code` to game
it. Instead, in this order:

1. If every member of the file is dead, remove the whole file (whole-file check).
2. Otherwise target the next mutant of the same dead member, or of the build-forced group (e.g. a dead caller that must go
   with the removed member), whose span is unique; record the unclaimable one as `resolved`.
3. If neither applies, skip it as _Unclaimable_.

## Build-forced edits in moves

Moving code to another project can break the build through rules the old location muted (nullable baselines, folder-level
analyzer config, unused-import errors). Only the edits the profile lists under _Build-forced edits in moves_ are allowed;
name each in the commit body. Never use them to trim or clean up: that goes to the tracker's sync log.

## Multi-mutant runs ("fix N")

- **Plan first.** Before any edit, walk report order and write the plan: array index, id, path (test / remove / move /
  skip + category), until N valid targets are reached. Send the whole plan to one independent reviewer (Step 6 prompt,
  adapted) and fix it before touching code. Cross-target mistakes (wrong skips, report-order gaps) only show at this level.
- **Report order is strict.** Never claim a later target while an earlier claimable one is left out.
- **Record everything you examine.** Every alive mutant the survey or plan looks at gets a ledger row in this PR, claimed or
  not: `skipped` with its category and the concrete blocker, or `queued` when it is claimable but past the cut (with the
  entry point or caller evidence found). Prose in the sync log is not enough: the next run reads rows, not paragraphs. The
  survey of the next run is then limited to mutants without a row and files changed since the baseline, and the plan review
  covers only those and the targets.
- **A `queued` row is a recommendation, not a verdict.** Step 3.0 still applies when the row is taken (no caller in the
  production scope means misplaced code, not a plain test): record the path after that check, and fall back to a Blocked
  move (kill in place, `Blocked move:` note) if the move fails. A removal and the incidental siblings it drags in
  (unclaimable spans) count as one target toward N.
- **Twin files.** When the codebase clones files (two near-identical use cases, copied adapters), look up the same member in
  the twin before claiming a dead member (or a skip) in one copy: a twin claimable earlier in report order must be claimed
  first. Re-verify a ledger disposition before relying on it when it contradicts what you find: ledger rows are decisions,
  not facts.
- **Counting.** Only dedicated targets (their own commit, verified by `mutant_checks.py`) count toward N. Incidental
  siblings and moved mutants are reported separately.
- **Cut.** Stop at the Nth valid target; the PR covers report indexes `0..k` with every mutant in it accounted for
  (fixed, sibling, moved or skipped).
- **Bundling.** When the user asks for one PR, add the ledger rows of skipped targets to the PR's single commit.

## Measurement

- The survey and plan get their **own** Execution-history row (`plan`), so per-target clocks start at selection and are
  not upper/lower bounds of each other.
- Take `date -u` the moment a target's `verify` is green, before anything else. If the session pauses before that, record
  only measured bounds, never the resume time. The batched review has no fix clock.
- Skipped targets decided in the plan have `unknown` timing; say "decided in the plan, batch-reviewed".
- Request → PR clock: the **request UTC** is taken at the very start of Step 0 and the **PR UTC** the moment the PR
  URL is known (before the PR-link/duration follow-up edit). If the session paused or was resumed in between, the
  duration is a lower bound: record `≥ <human>` and say why in the sync log, like the fix clock.
- Durations are always written human-readable (`45s`, `38m 29s`, `1h 5m 12s`, `1d 2h 3m 4s`), computed with
  `scripts/mutant_checks.py duration`. Keep bound qualifiers in front (`≥`, `≤`) and `unknown` when unmeasured.
- Multi-mutant, one PR per mutant: PR N+1's request → PR clock starts at PR N's PR UTC (PR 1: the request UTC).
  A bundled PR has a single request → PR duration covering the whole run including the survey/plan.

## Commit and PR hygiene

- Commit subjects ≤ 72 characters (commit hooks usually check only the format). PR title ≤ 63 characters: the squash
  merge appends ` (#NNNN)` (adjust if the project's merge strategy differs).
- PRs land as squash merges: never cite branch-only SHAs in commit bodies or the tracker; say "earlier in this PR" or use
  the attempt label (T1, T2 …).
- Follow the profile's branch/push conventions (e.g. a first push with upstream); see `SKILL.md` Step 7 for the
  follow-up tracker commit.

## Speed pitfalls (observed on long multi-target runs)

- **Commits are the slowest step** when hooks build, test and check coverage (~1.5 min each): one commit per PR runs them
  once. Hooks that refuse unstaged modifications also make per-target commits sweep unrelated pending edits together.
- **`verify` needs one mutated file per mutation run**, and the baseline line numbers must still match. When an earlier
  target of the same file shifted the lines (a removal above a test target), verify the later target against a temporary
  copy of the base version of that file (`git show <base>:<file>`), then restore the file. Never skip the verify.
- **`verify` input**: the report `id` (not the array index) and the fully qualified test name from `testFiles`; it refuses a
  report older than the current source, so finish `mutation run → verify` for a target before editing that same source
  file again (other files do not matter).
- **Probe before assuming a fixture value is an input** (a spreadsheet cell may be a formula, a config key may be
  overridden): one probe assertion that prints the values beats several mutation runs.
- **Existing assertions can hide an overload or a type** (an integer equals a boxed float in loose assertions): assert the
  type or the exact call when the mutant is about it.
- **Never start a shell command that reads stdin by accident** (a stray `cat > file` blocked a run for minutes).
- **Subject length is usually checked by review, not by hooks**: write it right the first time.
- **Take a clock per target**: `date -u` at each target start and when its `verify` is green, or every fix duration ends
  up `unknown`.
- **New test files**: honour the profile's _Conventions_ (analyzers, linters, nullable rules) from the first write to save
  build loops.
