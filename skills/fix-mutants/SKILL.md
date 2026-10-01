---
name: fix-mutants
description: "Fix surviving mutation-testing mutants on any stack (Stryker.NET, StrykerJS, any tool emitting a mutation-testing-elements report): kill each mutant with a new test driven through the right entry-point layer, production code only as a last resort. Autonomous, verified by script, always ends with an independent sub-agent review and a PR for a human to approve. Invoke to fix, kill, address or clean up mutants or mutation-testing findings."
effort: high
---

# Fix Mutants

Kill one or several mutants reported by a project's mutation-testing baseline. One increment per mutant — plan → test-or-code → validate → review → commit, then move to the next.

## Project profile (load first)

This skill is stack- and project-agnostic. Everything specific — scope, mutation command, report source, environment, layers, gate, conventions — lives in the project's `.fix-mutants/` folder (layout: `references/profile.md`), next to its code, versioned with it. Scripts find it by walking up from the working directory, or take `--profile <path>/profile.json` (needed when a monorepo has several). `mutant_checks.py` below is `<skill>/scripts/mutant_checks.py` (Python ≥ 3.9, standard library only; subcommands `baseline`, `list`, `check`, `verify`, `gate`, `duration`). Missing profile → run `python3 <skill>/scripts/init_profile.py --repo .` (it detects the stack and writes the folder), review the generated `PROFILE.md`, then continue. Below, **the profile** means `PROFILE.md` + `profile.json`, **the tracker** its `MUTATION-TRACKING.md`, **production scope** / **test scope** its `production_root` / `test_roots`.

## References

- `.fix-mutants/PROFILE.md` — the project's scope, environment, mutation command, gate, layers, caller search, conventions (**mandatory**)
- `.fix-mutants/report-fetch.md` — locate, fetch, and verify the mutation report
- `references/review-checklist.md` — the independent sub-agent review prompt (step 6)
- `references/pr-template.md` — the PR body template, with the reviewer checklist (step 7)
- `references/outcome-checks.md` — read-only verifier commands
- `references/decision-rules.md` — untruncated caller search, what counts as a layer, skip categories, non-unique spans, build-forced edits in moves, multi-mutant plan/count/cut, measurement, commit hygiene (**mandatory**)
- `.fix-mutants/MUTATION-TRACKING.md` — the ledger of every mutant already fixed/resolved/skipped, synced against the baseline in Step 1 and appended to in Step 7. The reference for "has this been dealt with before" — check it before falling back to `git log`.
- the profile's test conventions, and the project's existing tests — layer, structure, naming (mandatory reading before writing any test)
- `references/profile.md` — the profile format; `scripts/init_profile.py` writes it

## Non-negotiable rules

- **Tests only, by default.** Modifying production code is a **last resort** — only when writing a meaningful test is impossible (see Step 4). Never touch the mutation tool's config, build/analyzer config, or files unrelated to the target mutant(s).
- **Never modify an existing test, assertion, fixture, helper, or test config.** One new test per mutant, at the correct layer.
- **Never construct a leaf type (an exception, a value object) directly just to "poke" a mutant.** Drive it through the public entry point of the adapter/use-case that actually owns the mutated code (per the profile's test conventions). A test that only exercises a class in isolation when that class is normally reached through a use-case is testing an implementation detail — wrong layer.
- **Scope the mutation tool explicitly on every run** with the profile's command: project, test project, smallest file/range. Never run an unscoped whole-project mutation test. Mutation and task-directed test runs use only the intended unit/spec project. Mandatory commit hooks may run broader suites: never bypass them; report their results separately.
- **Verify outcomes, not tool messages.** Run `mutant_checks.py --profile <profile.json> check` after staging removals/moves, before expensive validation, and `verify` against the final raw mutation JSON. An empty file is not a deletion; `Killed` without the new test in `killedBy` is not a demonstrated test fix.
- **Never truncate a caller search** (`head`/`tail`/`-m`): a cut-off grep once made live code look dead. Use the profile's split production/test search (pattern in `references/decision-rules.md`).
- **Measure two durations, both human-readable.** The **fix duration** (target selection → independent review verdict, per mutant) and the **request → PR duration** (the user's request → the PR exists, per PR). Take every timestamp with `date -u +%Y-%m-%dT%H:%M:%SZ` the moment the event happens, compute the duration with `python3 <skill>/scripts/mutant_checks.py duration --start <UTC> --end <UTC>` (never by hand) and write its `human` value (`38m 29s`, `1h 5m 12s`) — not raw seconds — in the tracker, the PR description and the final message to the user. Record exact agent/model metadata. Never invent missing duration/model data.
- **Never ask the user for a decision.** This skill runs unattended end-to-end: pick the default, act, and record the reasoning in the PR (and the tracker) so the reviewer can overturn it. The PR review is the approval gate for every change, production code included — it stands in for any "ask before" rule within this skill. When a decision would change runtime behaviour (a real defect, not dead code), don't make it: mark the mutant `🟡 Skipped` with the reason, give it its own block in the PR (kill type `Skipped (not fixed)`), and move on.
- **One commit per mutant fix**, Conventional Commits, scope per the profile. Always a branch + PR, never a direct push to the main branch and never self-merged: mutant fixes affect shared test/production code and deserve a human review.

## Step 0 — Scope the request

**First action, before anything else (fetch, setup, reading):** run `date -u +%Y-%m-%dT%H:%M:%SZ` and keep it as the **request UTC** — the start of the request → PR clock. If you are resumed or the request arrived earlier than this run observed, record only what was measured (see `references/decision-rules.md` → _Measurement_).

Parse `$ARGUMENTS` for: the project profile, which mutant(s) — explicit id(s), a count ("first N alive"), a file, or "everything reported alive in project X" — and the report source (a CI run URL/artifact metadata, or "use the latest published baseline", as the profile's `report-fetch.md` defines). If the user gives an explicit selection rule (e.g. "the first one listed in the report JSON"), follow it literally — do not apply your own additional criteria (severity, file, etc.) unless asked.

**Decide and proceed** (see _Never ask_ above). If no selection rule is given, default to the first alive mutant **that is not already dealt with** in report order (array index order — see the profile's `report-fetch.md` → Report shape) from the latest published baseline. A mutant already in the ledger (`🟢 Fixed`, `⚪ Resolved-incidentally`, `🟡 Skipped`) or killed by a PR merged since the baseline (Step 1.2) is not a target: skip it silently and take the next one. The report is a snapshot, so the first selected report index is not necessarily 0 — record it in the sync log (the PR's Why does not cite report indexes: a reader does not know them). If the user hasn't said whether multiple mutants get one PR per mutant or a single bundled PR, default to one PR per mutant (see _Multiple mutants_ below).

**More than one mutant?** Plan the whole run before any edit — report order, path per target, stop at the Nth valid target — and get the plan independently reviewed (`references/decision-rules.md` → _Multi-mutant runs_). Only dedicated targets count toward N.

## Step 1 — Fetch and verify the report

Follow the profile's `report-fetch.md`. Confirm the report's integrity checksum before trusting the content. Note its scope (project, test project, mutate filter), source revision and `generated_at` (UTC timestamp — needed later for the PR).

**Environment setup:** follow the profile's _Environment setup_.

**Sync the tracker against this baseline before picking a target (pre-compute).**

1. Compare the fetched `generated_at`/source revision to the tracker's "Latest known baseline" header.
   - **Unchanged** → skip re-sync, use the tracker as-is.
   - **New baseline** → for every `🟢 Fixed`/`⚪ Resolved-incidentally` ledger row, confirm it's still gone/killed in the new report (re-locate by `(file, mutator, snippet)`, not `id` or line — both drift). If one has come back alive, mark it `🔴 Regressed` and flag it in the PR's _Review focus_ — don't silently re-fix it as if new. Then append a new Score trend row with the fresh counts, if the tracker has a Progress curve chart add the matching point (baseline date `MM-DD`, `remaining`) to it, and update the header block.
2. **Check for mutants already resolved on this branch.** The ledger only knows about mutants from _prior runs_; a mutant a _human_ fixed outside this skill, or one this same run's earlier increment touched incidentally, won't be in it yet. Before picking a target in Step 2: look the candidate up in the ledger first (O(1)); if absent, fall back to `git log <report.source.sha>..HEAD -- <candidate mutant file(s)>` — if a commit already touched the file, diff its content at `report.source.sha` against `HEAD` at the mutant's location, and if the mutated code no longer exists or was already covered, skip that mutant (note why, and record it in the tracker as part of Step 7) and move to the next one in report order.

## Step 2 — Identify each target mutant

For each selected mutant: id, `path`, `location` (start/end line+col), `mutator`, `status`. Read the source file at that location to derive the **original code** and reconstruct the **mutated code** for that mutator (e.g. `Conditional (true) mutation` replaces the condition with `true`).

Immediately note the UTC start time for the selected target (the **fix clock** start), before reachability research, using `date -u +%Y-%m-%dT%H:%M:%SZ`. Record the agent/harness and runtime-reported model ID, including effort/version when exposed; use `unknown` rather than guessing. Incidental siblings share the target's attempt, not additional fix durations.

## Step 3 — Find the right test, per mutant (preferred path)

0. **Check the mutated code belongs in the production scope at all.** Grep its real (non-test) callers first (profile → _Caller search_). If none live in the production scope — e.g. the only caller is composition-root wiring — or the code is adapter plumbing the profile names (cloud clients, connection-string parsing, config binding), it is misplaced: a test in the scoped test project would only lock that in. Go to Step 4 → _Misplaced code_ instead of writing a test. The profile defines the layers; a caller in tooling or a test project is not a real caller (`references/decision-rules.md` → _What counts as a layer_). **Precedence:** if no real caller exists in _any_ layer, the code is dead, not misplaced — Step 4 removal wins over a move (moving dead code only relocates it).
1. Trace the mutated code's call graph **up** to the nearest reachable public entry point: a use-case's public method, an adapter's port method, an endpoint. That is the layer to test (test kind per the profile's test conventions) — not the mutated line's own class in isolation, unless that class's public constructor/method genuinely _is_ the entry point a caller uses **and** a real (non-test) caller actually reads the mutated member's return value. Grep every real call site of that member — a class being directly `new`'d elsewhere is not sufficient on its own if nothing ever consumes the specific mutated member; treat that case as Step 4 instead.
2. Confirm the chosen input actually reaches the mutated branch (reason through it, don't guess) — build a small local probe if a third-party behavior is involved (e.g. what a library does with a `null` argument) rather than assuming.
3. Write exactly **one** new test (new file or appended to the right existing test file) that fails under the mutant and passes against real code, asserting functional behaviour.
4. Build, run the new test, then run the scoped mutation command directly. Confirm target `Killed` and the new test in `killedBy`. This final mutation run also serves Step 5 if no relevant code/test changes intervene.
5. Run the test-only gate on the staged diff (`python3 <skill>/scripts/mutant_checks.py --profile <profile> gate --repo .`, or the profile's own command) — it must PASS. If it fails, either the change isn't test-only (fix that) or this mutant belongs in Step 4. A profile without a gate command requires the PR to show that the diff stays inside the test scope (plus the tracker).

**Mutation command:** the profile's _Mutation command_, run from its working directory exactly as CI does, with the smallest filter that covers the target. Honour the profile's pitfalls (solution-mode traps, project-name forms, tool restore). Pin check: the local tool version and CI's must agree — mention any skew in the PR if a result looks version-dependent.

## Step 4 — Last resort: production code change

Take this path **only** when Step 3 cannot produce a test that both fails under the mutant and reflects real, reachable behaviour — typically because the mutated branch is dead code. Do not take it to avoid the effort of finding the right layer.

Before proposing any production change, gather evidence:

1. **Exhaustive reachability check** — `grep` the _whole_ repository (not just the mutant's own project) for real construction/call sites of the mutated code path.
2. **History check** — `git log -S"<construct>"` / `git log -G` on the file: was it ever reachable? If yes, find and cite the commit where it became orphaned (a deleted caller, a removed provider, etc.).
3. **Third-party/native check** — if the code wraps or mirrors a framework/library API, verify by inspecting that library's actual types/behaviour (load the assembly, list its exception types, or run a tiny probe project) — never assume names or semantics.

Then **decide and proceed — don't ask**. Make the smallest change that removes the dead branch: the target code plus only what must go with it for the build to pass (e.g. the dead callers that construct a removed type, `using`s that only served it). Anything the removal merely orphans, and any extra cleanup, goes to the the tracker sync log, not the diff. Never make a change that just makes the mutant harder to express without addressing why it's unreachable; never fix a behaviour-changing defect here (see _Never ask_ → `🟡 Skipped`). The test-only gate will correctly fail for this path (by design) — do not bypass it silently; the PR must flag that production code changed, why, and the evidence above, so the reviewer can reject it.

Stage the change and run the mechanical `check` before building: whole-file removal requires physical absence and staged deletion; member removal requires an explicit original code excerpt, absent from the staged/current source. Re-check implicit consumers (the profile lists the stack's: DI, reflection, serialization, generated code…); the script does not prove runtime unreachability. If `check` fails with "target span still exists" because the mutated text recurs in a kept member, never broaden the excerpt — follow `references/decision-rules.md` → _Non-unique spans_. Dead code that is still referenced by tests or test helpers is a skip, not a removal (→ _Skip categories_).

**Misplaced code** (from Step 3.0): move the code to the layer its callers live in (the profile names the destination), with its test moved to the matching test project. Move it **as-is** — namespaces and imports only, plus the build-forced compiler/analyzer edits the profile lists under _Build-forced edits in moves_ (name each in the commit body) — no trimming or cleanup (those go to the the tracker sync log). If the move would force edits to an existing test, skip it as a _Blocked move_. Its mutants leave the mutation scope: record them in the tracker as `⚪ Resolved-incidentally` ("moved out of scope, not killed") and say so in the PR.

If a Step 3 test was already committed/pushed/PR'd before the reachability gap surfaced: `git revert` that commit (no force-push, no history rewrite), then continue this step and update the existing PR rather than opening a new one.

## Step 5 — Scoped mutation re-verification

For every target, run `mutant_checks.py verify` against the final raw mutation report (Step 3 can supply it without a redundant rerun):

- **Test:** match file/location/operator, require `Killed` and the named new test in `killedBy`.
- **`verify` output:** success is the **exit code 0** only — it prints the remaining-mutants JSON (large), no `OK` line. It fails with `target must uniquely match location/mutator` when another mutant sits at the same location with the same mutator (typical for an equivalent mutant): that mutant is a `🟡 Skipped` (equivalent), not a failed fix.
- **Removal:** prove the staged source deletion/code removal and its absence from the report. A deleted file retained as `source: ""` is a failure. No mutation score is expected when nothing remains to mutate.
- **Move:** require source deletion and a staged nonempty destination outside the production scope; report "out of scope", never "killed". Review that the move is otherwise as-is.
- All reported mutants outside the targeted file must be `Ignored`; `testFiles` must be nonempty and belong only to the profile's test scope. Use the latest successful run; rerun the mutation tool if source, tests or relevant build inputs changed.

Match the target mutant between the baseline report and this run by **(file, location line/column, mutator name)**, never by `id` alone — mutation tools assign `id`s per run and they are not stable across runs.

After the final mutation run, do the profile's cleanup (stale mutant binaries must not survive), then a clean analyzer-enabled build and unit/spec tests before review/commit. Repeat the cleanup if another mutation run occurs; do not repeat unchanged validations merely to satisfy two step headings.

**Never delete the raw report output** (observed once: over-eager cleanup destroyed the raw report, the independent reviewer could not re-run `verify`, and the fix required a full scoped re-run). The raw JSON of the final successful run is the evidence Steps 5 and 6 rest on — keep it in place and copy it outside the worktree with its sha256 recorded in the sync log, so a later cleanup cannot invalidate the PR's claims.

Record alive-mutant counts before/after in the mutated scope, and the list of any mutants still alive there.

## Step 6 — Independent sub-agent review (mandatory, every time)

Before committing, use the available delegation mechanism to launch a **fresh independent reviewer**, read-only, and wait for its verdict. Supply `references/review-checklist.md`, the target, diff, path taken, current mutation report and validation results. The reviewer must inspect the code/report itself and report coherence, minimal scope, and compliance with the profile's test conventions and the project's AGENTS.md.

Act on findings: fix and re-review if the sub-agent flags a real problem; if it disagrees but you have stronger evidence, say so explicitly in the PR's _Review focus_ rather than silently overriding it.

After the final review, note UTC end and compute the **fix duration** with `mutant_checks.py duration` from the observed start time. Record the outcome, the human-readable duration and the reviewer model (or `unknown`). This stops the fix clock **before** ledger updates, commit hooks, PR creation and human merge/review waits. Skipped targets also get a completed attempt, identified as skipped, never as a successful fix.

## Step 7 — Commit and PR

One commit per mutant. Type `test` when Step 3's path was used; `refactor` for Step 4 (dead code). Never `fix` — behaviour-changing defects are skipped, not fixed (see _Never ask_). Commit on a dedicated branch, push it and open the PR with the host's CLI (`gh pr create`, `glab mr create`…) or, without one, print the PR body for the user to paste.

Commit from the working directory and with the toolchain activation the profile prescribes (its _Environment setup_), so the commit hooks find their tools.

**Update the mutation tracker in the same commit (post-compute).** Before staging, append this
mutant's outcome to the tracker:

- One new **Ledger** row: file, line (at the baseline sha), mutator, status (`🟢 Fixed` or `⚪
Resolved-incidentally` for a sibling mutant on the same removed/changed code), the PR link + commit
  sha (fill the PR link in after the PR exists — amend the same commit or add it as part of
  the PR description edit; the commit's own body doesn't need it), and
  a one-line note.
- One new **Sync log** entry (newest first): baseline used, what Step 1's staleness check found (if
  anything was skipped as already-resolved), which mutant was selected and why, path taken, and the
  ledger delta.
- If Step 1 found a `🔴 Regressed` mutant, record that here too regardless of whether this run
  attempts to re-fix it.
- One **Execution history** row per targeted attempt: baseline/target identity, outcome, UTC start/end,
  human-readable fix duration, observed agent/model and reviewer model, plus PR reference. Leave the
  _Request → PR_ cell as `pending` — the PR does not exist yet; it is filled in below. Include
  retries/waits in elapsed time; record model switches and blockers in the sync log. Do not estimate
  missing historical values, divide time among incidental siblings, or compare skipped/moved/deleted
  outcomes directly to test fixes as if they were equivalent work. Multi-mutant runs add a `plan` row and
  follow `references/decision-rules.md` → _Measurement_ (end time the moment the verdict arrives).

The tracker is allowlisted in the profile's test-only gate alongside the test projects (a profile without a gate allows it by convention), so staging it together with a Step 3 test-only fix still passes — a documented exception (a ledger entry, not production or test code), not a loophole.

**Request → PR duration (post-compute).** The moment the PR URL is known, run `date -u +%Y-%m-%dT%H:%M:%SZ` (the **PR UTC**) — before any follow-up edit — and compute `mutant_checks.py duration --start <request UTC> --end <PR UTC>`. Write the result with the PR link wherever the PR link is filled in (ledger/Execution-history `pending` cells, PR description), using the same amend-or-edit mechanism as the PR link; that follow-up edit's own time is not counted. One PR per mutant in a single request: the clock of PR N+1 starts when PR N was created (PR 1 starts at the request UTC) — say so in the sync log. A bundled PR has one request → PR duration and one fix duration per target. The final message to the user gives the PR description's totals and one-sentence summaries (per-target kill type and fix duration, then request → PR).

PR description follows `references/pr-template.md` and nothing more, in this order (essentials first): Why, Totals, Review focus, how each mutant was killed — no Recap table, Approach, Testing, Next steps, review-verdict or checklist sections (mutation-tool command, working directory, report timestamp and fingerprint, validation results, the Step 6 verdict, skipped mutants and leftover cleanup go in the the tracker sync log). Mutants are grouped by kill type (🧪, ⚠️✏️, ⚠️🗑️, ⚠️📦, ⏭️), each mutant being one collapsed `<details>` block whose summary line has a number `n°n` (never `#n`, which the code host turns into an issue link; 1…N across the PR, in displayed order, quoted by Review focus) (never the report's id or idx — those stay in the tracking sync log), then one plain sentence of 14 words at most (what was missed, or what was deleted — no title prefix) the number of mutants it covers and the time; the source link and class go on the first line inside the block. Each block holds: clickable source link, class/method, explicit kill type with its emoji (`🧪 New test added`/`⚠️✏️ Existing test edited` (the recorded exception to the no-edit rule; commit type `test`)/`⚠️🗑️ Dead code deleted`/`⚠️📦 Code moved to another project`/`⏭️ Skipped (not fixed)`; an edited test, deleted or moved code also gets a ⚠️ quoted warning, since no fresh test proves it), a one-sentence plain-language summary, the **code before the change** and the **code with the mutation applied** and **how it was killed** (why existing tests missed it; the new test with name + link, or the removed/moved code with the Step 4 evidence; whether production code was touched). Totals as a subtraction table: the baseline's remaining count, one `−` row per kill type (new test, edited test, deleted, moved; skipped ones are not subtracted and go in the line under the table), and the remaining after this PR as the last row, total fix duration (sum of the per-target durations, by script), `Request → PR: 52m 10s` and, under the totals, the progress chart (the the tracker Progress curve points plus a last `after this PR` point = remaining mutants); the final message to the user repeats the totals and the one-sentence summaries. The request → PR duration only exists once the PR does, so write `pending` in the description passed to `create-pr` and fill it in with the PR link (see above). Keep commit subjects ≤ 72 and the PR title ≤ 63 characters, and never cite branch-only SHAs (squash merge) — see `references/decision-rules.md` → _Commit and PR hygiene_.

## Multiple mutants

Process sequentially, one full loop (Steps 2–7) per mutant. Default to one PR per mutant (small
batches, easier review, and one clean ledger entry per PR) unless the user asks to bundle — decide,
don't ask (see Step 0). When bundling, keep one commit per target, follow the plan/count/cut rules in
`references/decision-rules.md`, and put skipped targets' ledger rows in the next code commit. After the PR, leave the worktree/branch in place.
