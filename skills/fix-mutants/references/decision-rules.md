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

Record each as `🟡 Skipped` with the category and the concrete blocker. Group mutants of one member/file with the same
reason into one ledger row.

| Category         | Signal                                                                                                                                                                                             | Why not fixed                                                                  |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Dead but tested  | No production caller; only its own unit tests call it                                                                                                                                              | Removal deletes existing tests; a new test locks in dead code                  |
| Test-helper only | Only fixtures/fakes/helpers in test projects call it                                                                                                                                               | Removal modifies test helpers                                                  |
| Blocked move     | Misplaced, but the move forces edits to existing tests (the profile may list stack-specific cases) or cannot be checked (member move out of a file that stays) | Never modify existing tests; `mutant_checks.py` only verifies whole-file moves |
| Real defect      | The mutated code is live and wrong                                                                                                                                                                 | Behaviour change — fix test-first in a dedicated PR                            |
| Unclaimable      | Dead, but its span is not unique (below) and no other claimable target covers it                                                                                                                   | Removal cannot be verified                                                     |
| Equivalent       | The change does not alter observable behaviour (e.g. `>=` → `>` where both branches write the same value), so no test can fail; often shares its location and mutator with a killable sibling      | Nothing to fix; killing it would need a behaviour-changing edit                |

## Non-unique spans

`mutant_checks.py` confirms a member removal only if the target's span text is absent from the **whole** file, so
`true`/`false`/`null` mutants are usually unclaimable when sibling members stay. Never broaden `--removed-code` to game
it. Instead, in this order:

1. If every member of the file is dead, remove the whole file (whole-file check).
2. Otherwise target the next mutant of the same dead member, or of the build-forced group (e.g. a dead caller that must go
   with the removed member), whose span is unique; record the unclaimable one as `⚪ Resolved-incidentally`.
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
- **Counting.** Only dedicated targets (their own commit, verified by `mutant_checks.py`) count toward N. Incidental
  siblings and moved mutants are reported separately.
- **Cut.** Stop at the Nth valid target; the PR covers report indexes `0..k` with every mutant in it accounted for
  (fixed, sibling, moved or skipped).
- **Bundling.** When the user asks for one PR, keep one commit per target and add the ledger rows of skipped targets to
  the next code commit.

## Measurement

- The survey and plan get their **own** Execution-history row (`plan`), so per-target clocks start at selection and are
  not upper/lower bounds of each other.
- Take `date -u` the moment the review verdict arrives, before anything else. If the session pauses before that, record
  only measured bounds (e.g. review start + reported review duration), never the resume time.
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
- Follow the profile's branch/push conventions (e.g. a first push with upstream).
