---
name: fix-mutants
description: "Fix surviving mutation-testing mutants on any stack (Stryker.NET, StrykerJS, any tool emitting a mutation-testing-elements report): kill each mutant with a new test driven through the right entry-point layer, production code only as a last resort. Autonomous, verified by script, always ends with an independent sub-agent review and a PR for a human to approve. Invoke to fix, kill, address or clean up mutants or mutation-testing findings."
effort: high
---

# Fix Mutants

Kill one or several mutants reported by a project's mutation-testing baseline. One increment per mutant (plan → test-or-code → validate, Steps 2–5, changes staged but not committed), then ONE independent review (Step 6) and ONE commit and PR (Step 7) for the whole run.

## Project profile (load first)

This skill is stack- and project-agnostic. Everything specific — scope, mutation command, report source, environment, layers, gate, conventions — lives in the project's `.fix-mutants/` folder (layout: `references/profile.md`), next to its code, versioned with it. Scripts find it by walking up from the working directory, or take `--profile <path>/profile.json` (needed when a monorepo has several). `mutant_checks.py` below is `<skill>/scripts/mutant_checks.py` (Python ≥ 3.9, standard library only; subcommands `baseline`, `list`, `check`, `verify`, `gate`, `duration`). Missing profile → run `python3 <skill>/scripts/init_profile.py --repo .` (it detects the stack and writes the folder), review the generated `PROFILE.md`, then continue. Below, **the profile** means `PROFILE.md` + `profile.json`, **the ledger** its `ledger.jsonl`, **the tracker** its `MUTATION-TRACKING.md`, **production scope** / **test scope** its `production_root` / `test_roots`.

## References

- `.fix-mutants/PROFILE.md` — the project's scope, environment, mutation command, gate, layers, caller search, conventions (**mandatory**)
- `.fix-mutants/report-fetch.md` — locate, fetch, and verify the mutation report
- `references/review-checklist.md` — the independent sub-agent review prompt (step 6)
- `references/pr-template.md` — the PR body template, with the reviewer checklist (step 7)
- `references/outcome-checks.md` — read-only verifier commands
- `references/decision-rules.md` — untruncated caller search, what counts as a layer, skip categories, tested dead code and test-only helpers, non-unique spans, build-forced edits in moves, multi-mutant plan/count/cut, measurement, commit hygiene, speed pitfalls (**mandatory**)
- `references/tracker-sync.md` — syncing the ledger and the tracker against the baseline and spotting mutants already resolved on this branch (read in Step 1, before picking a target)
- `references/production-change.md` — evidence to gather, dead-code removal, the mechanical `check`, _Misplaced code_ moves and backing out a written test (read before any production change, Step 4)
- `references/verification.md` — per-outcome `verify` criteria, cleanup, order constraints, keeping the raw report (read before the first `verify`, Step 5)
- `references/ledger.md` — `.fix-mutants/ledger.jsonl`, one JSON row per examined mutant, read and written only with `scripts/ledger.py` (schema, statuses, commands). The reference for "has this been dealt with before" — check it before falling back to `git log`.
- `.fix-mutants/MUTATION-TRACKING.md` — baselines, score trend, execution history and sync log, synced in Step 1 and appended to in Step 7.
- the profile's test conventions, and the project's existing tests — layer, structure, naming (mandatory reading before writing any test)
- `references/profile.md` — the profile format; `scripts/init_profile.py` writes it
- `assets/board.html` + `scripts/board_feed.py serve --open` — animated board of this skill for humans: live on the newest Claude Code run, replay or demo; never needed to run the skill

## Non-negotiable rules

- **Tests only, by default.** Modifying production code is a **last resort** — only when writing a meaningful test is impossible (see Step 4). Never touch the mutation tool's config, build/analyzer config, or files unrelated to the target mutant(s).
- **Never modify an existing test, assertion, fixture, helper, or test config.** One new test per mutant, at the correct layer. Only exceptions, flagged ⚠️ in the PR: the tests deleted or adapted with _Dead but tested_ code and the build-forced edits of a _Test-helper only_ move (`references/decision-rules.md` → _Tested dead code and test-only helpers_).
- **Never construct a leaf type (an exception, a value object) directly just to "poke" a mutant.** Drive it through the public entry point of the adapter/use-case that actually owns the mutated code (per the profile's test conventions). A test that only exercises a class in isolation when that class is normally reached through a use-case is testing an implementation detail — wrong layer.
- **Scope the mutation tool explicitly on every run** with the profile's command: project, test project, smallest file/range. Never run an unscoped whole-project mutation test. Mutation and task-directed test runs use only the intended unit/spec project. Mandatory commit hooks may run broader suites: never bypass them; report their results separately.
- **Verify outcomes, not tool messages.** Run `mutant_checks.py --profile <profile.json> check` after staging removals/moves, before expensive validation, and `verify` against the final raw mutation JSON. An empty file is not a deletion; `Killed` without the new test in `killedBy` is not a demonstrated test fix.
- **Never truncate a caller search** (`head`/`tail`/`-m`): a cut-off grep once made live code look dead. Use the profile's split production/test search (pattern in `references/decision-rules.md`).
- **Measure two durations, both human-readable.** The **fix duration** (target selection → green `verify`, per target; the single batched review is not part of any fix clock) and the **request → PR duration** (the user's request → the PR exists, per PR). Take every timestamp with `date -u +%Y-%m-%dT%H:%M:%SZ` the moment the event happens, compute the duration with `python3 <skill>/scripts/mutant_checks.py duration --start <UTC> --end <UTC>` (never by hand) and write its `human` value (`38m 29s`, `1h 5m 12s`) — not raw seconds — in the tracker, the PR description and the final message to the user. Record exact agent/model metadata. Never invent missing duration/model data.
- **Never ask the user for a decision.** This skill runs unattended end-to-end: pick the default, act, and record the reasoning in the PR (and the tracker) so the reviewer can overturn it. The PR review is the approval gate for every change, production code included — it stands in for any "ask before" rule within this skill. When a decision would change runtime behaviour (a real defect, not dead code), don't make it: mark the mutant `skipped` (`real-defect`) with the reason, give it its own block in the PR (kill type `Skipped (not fixed)`) plus a _Decisions needed_ entry with a plain-language example, and move on.
- **One code commit per PR** (plus one tracker-only follow-up, Step 7), Conventional Commits, scope per the profile: commit hooks (build, tests, coverage) cost minutes per commit, and the PR body already gives one block per mutant. Stage each verified target as you go (`git add`) but commit once, after the review. Always a branch + PR, never a direct push to the main branch and never self-merged: mutant fixes affect shared test/production code and deserve a human review.

## Step 0 — Scope the request

**First action, before anything else (fetch, setup, reading):** run `date -u +%Y-%m-%dT%H:%M:%SZ` and keep it as the **request UTC** — the start of the request → PR clock. If you are resumed or the request arrived earlier than this run observed, record only what was measured (see `references/decision-rules.md` → _Measurement_).

Parse `$ARGUMENTS` for: the project profile, which mutant(s) — explicit id(s), a count ("first N alive"), a file, or "everything reported alive in project X" — and the report source (a CI run URL/artifact metadata, or "use the latest published baseline", as the profile's `report-fetch.md` defines). If the user gives an explicit selection rule (e.g. "the first one listed in the report JSON"), follow it literally — do not apply your own additional criteria (severity, file, etc.) unless asked.

**Decide and proceed** (see _Never ask_ above). If no selection rule is given, default to the first alive mutant **that is not already dealt with** in report order (array index order — see the profile's `report-fetch.md` → Report shape) from the latest published baseline. A mutant whose ledger row is `fixed`, `resolved` or `skipped` (`references/ledger.md`), or killed by a PR merged since the baseline (Step 1.3), is not a target: skip it silently and take the next one. Rows `queued` (`ledger.py find --status queued`: examined earlier, claimable, not yet taken) are the targets, in report order: start from them instead of re-surveying (re-check only files touched since the baseline, Step 1.3; a changed file whose mutant still exists and is still alive is not stale by itself: re-locate the mutant by (file, mutator, snippet), re-read the code around it and keep the row only if its plan still holds). The report is a snapshot, so the first selected report index is not necessarily 0 — record it in the sync log (the PR's Why does not cite report indexes: a reader does not know them). If the user hasn't said whether multiple mutants get one PR per mutant or a single bundled PR, default to one PR per mutant (see _Multiple mutants_ below).

**More than one mutant?** Plan the whole run before any edit — report order, path per target, stop at the Nth valid target — and get the plan independently reviewed (`references/decision-rules.md` → _Multi-mutant runs_). Only dedicated targets count toward N.

## Step 1 — Fetch and verify the report

Follow the profile's `report-fetch.md`. On a large report, start survey sub-agents as soon as it is verified (one per ~130 mutants) and set the environment up while they run; their prompt must require quoting each mutant's exact line and text at the baseline sha (`git show <sha>:<file>`), not a paraphrase. Confirm the report's integrity checksum before trusting the content. Note its scope (project, test project, mutate filter), source revision and `generated_at` (UTC timestamp — needed later for the PR).

**Environment setup:** follow the profile's _Environment setup_.

**Sync the ledger and the tracker against this baseline before picking a target (pre-compute).** Follow `references/tracker-sync.md`: unchanged vs new baseline, `regressed` rows, Score trend and Progress curve, `ledger.py validate`, and the check for mutants already resolved on this branch.

## Step 2 — Identify each target mutant

For each selected mutant: id, `path`, `location` (start/end line+col), `mutator`, `status`. Read the source file at that location to derive the **original code** and reconstruct the **mutated code** for that mutator (e.g. `Conditional (true) mutation` replaces the condition with `true`).

Immediately note the UTC start time for the selected target (the **fix clock** start), before reachability research, using `date -u +%Y-%m-%dT%H:%M:%SZ`. Record the agent/harness and runtime-reported model ID, including effort/version when exposed; use `unknown` rather than guessing. Incidental siblings share the target's attempt, not additional fix durations.

## Step 3 — Find the right test, per mutant (preferred path)

0. **Check the mutated code belongs in the production scope at all.** Grep its real (non-test) callers first (profile → _Caller search_). If none live in the production scope — e.g. the only caller is composition-root wiring — or the code is adapter plumbing the profile names (cloud clients, connection-string parsing, config binding), it is misplaced: a test in the scoped test project would only lock that in. Go to Step 4 → _Misplaced code_ instead of writing a test. The profile defines the layers; a caller in tooling or a test project is not a real caller (`references/decision-rules.md` → _What counts as a layer_). **Precedence:** if no real caller exists in _any_ layer, the code is dead, not misplaced — Step 4 removal wins over a move (moving dead code only relocates it).
1. Trace the mutated code's call graph **up** to the nearest reachable public entry point: a use-case's public method, an adapter's port method, an endpoint. That is the layer to test (test kind per the profile's test conventions) — not the mutated line's own class in isolation, unless that class's public constructor/method genuinely _is_ the entry point a caller uses **and** a real (non-test) caller actually reads the mutated member's return value. Grep every real call site of that member — a class being directly `new`'d elsewhere is not sufficient on its own if nothing ever consumes the specific mutated member; treat that case as Step 4 instead.
2. Confirm the chosen input actually reaches the mutated branch (reason through it, don't guess) — build a small local probe if a third-party behavior is involved (e.g. what a library does with a `null` argument) rather than assuming.
3. Write exactly **one** new test (new file or appended to the right existing test file) that fails under the mutant and passes against real code, asserting functional behaviour.
4. Build, run the new test, then run the scoped mutation command directly. Confirm target `Killed` and the new test in `killedBy`. This final mutation run also serves Step 5 if no relevant code/test changes intervene.
5. Run the test-only gate once, on the final cumulative staged diff just before Step 7 (not per target): `python3 <skill>/scripts/mutant_checks.py --profile <profile> gate --repo .`, or the profile's own command — it must PASS. If it fails, either the change isn't test-only (fix that) or this mutant belongs in Step 4. A profile without a gate command requires the PR to show that the diff stays inside the test scope (plus the tracker).

**Mutation command:** the profile's _Mutation command_, run from its working directory exactly as CI does, with the smallest filter that covers the target. Honour the profile's pitfalls (solution-mode traps, project-name forms, tool restore). Pin check: the local tool version and CI's must agree — mention any skew in the PR if a result looks version-dependent.

## Step 4 — Last resort: production code change

Take this path **only** when Step 3 cannot produce a test that both fails under the mutant and reflects real, reachable behaviour — typically because the mutated branch is dead code. Do not take it to avoid the effort of finding the right layer.

Before proposing any production change, read `references/production-change.md`: the evidence to gather (reachability, history, third-party checks), the decide-and-proceed rules for removing dead code, the staged `check` and _Non-unique spans_, **Misplaced code** (from Step 3.0: move as-is, `resolved`, _Blocked move_), and how to back out a test already written.

## Step 5 — Scoped mutation re-verification

For every target, run `mutant_checks.py verify` against the final raw mutation report. Before the first `verify`, read `references/verification.md`: the test/removal/move criteria, how to read `verify` output, matching by (file, location, mutator) never by `id`, cleanup, the order constraints, why the raw report is never deleted, and the alive-mutant counts to record.

## Step 6 — Independent sub-agent review (mandatory, every time)

Before committing, use the available delegation mechanism to launch ONE **fresh independent reviewer** for the whole run, read-only, and wait for its verdict. Supply `references/review-checklist.md`, every target, the whole staged diff, the path taken per target, each target's mutation report and `verify` output, and the validation results. The reviewer must inspect the code/report itself and report coherence, minimal scope, and compliance with the profile's test conventions and the project's AGENTS.md.

Act on findings: fix and re-review if the sub-agent flags a real problem; if it disagrees but you have stronger evidence, say so explicitly in the PR's _Review focus_ rather than silently overriding it.

At each target's green `verify`, take `date -u` and compute its **fix duration** with `mutant_checks.py duration` from its observed start time. Record the outcome and the human-readable duration in Execution history; the single review's model and verdict go in the sync log. This stops the fix clock **before** the review, ledger updates, commit hooks, PR creation and human merge/review waits. Skipped targets also get a completed attempt, identified as skipped, never as a successful fix.

## Step 7 — Commit and PR

One commit for the whole PR, made after every target is verified and the Step 6 review is done: run the clean analyzer-enabled build and the scoped test project once, then commit (hooks run once). The commit type is `test` when every target used Step 3, otherwise `refactor` (Step 4, dead code). Never `fix` — behaviour-changing defects are skipped, not fixed (see _Never ask_). Commit on a dedicated branch, push it and open the PR with the host's CLI (`gh pr create`, `glab mr create`…) or, without one, print the PR body for the user to paste.

Commit from the working directory and with the toolchain activation the profile prescribes (its _Environment setup_), so the commit hooks find their tools. Stage everything the run touched before committing (some hooks refuse unstaged modifications); a coverage ratchet staging an improved baseline inside the commit is expected. Never amend or rebase once the branch is pushed.

**Update the ledger and the tracker in the same commit (post-compute).** Before staging, record the outcomes of **every** examined target (one ledger row per mutant, including queued, skipped and sibling rows; one Execution-history row per targeted attempt, plus the `plan` row in multi-target runs):

- **Ledger**: `ledger.py add` a row per new mutant, `ledger.py update` a row taken from the queue (`references/ledger.md`):
  status `fixed`, or `resolved` for a sibling on the same removed/changed code, `"pr": "pending"` (never a commit sha:
  the ledger never cites branch-only shas), and a one-line note. Then `ledger.py validate`.
- One new **Sync log** entry (newest first): baseline used, what Step 1's staleness check found (if
  anything was skipped as already-resolved), which mutant was selected and why, path taken, and the
  ledger delta.
- If Step 1 found a `regressed` mutant, record that here too regardless of whether this run
  attempts to re-fix it.
- One **Execution history** row per targeted attempt: baseline/target identity, outcome, UTC start/end,
  human-readable fix duration, observed agent/model and reviewer model, plus PR reference. Leave the
  _Request → PR_ cell as `pending` — the PR does not exist yet; it is filled in below. Include
  retries/waits in elapsed time; record model switches and blockers in the sync log. Do not estimate
  missing historical values, divide time among incidental siblings, or compare skipped/moved/deleted
  outcomes directly to test fixes as if they were equivalent work. Multi-mutant runs add a `plan` row and
  follow `references/decision-rules.md` → _Measurement_ (end time the moment the verdict arrives).

The `.fix-mutants/` folder (tracker and ledger) is allowlisted by the test-only gate alongside the test projects, so staging it together with a Step 3 test-only fix still passes — a documented exception (tracking data, not production or test code), not a loophole.

**Request → PR duration (post-compute).** The moment the PR URL is known, run `date -u +%Y-%m-%dT%H:%M:%SZ` (the **PR UTC**) — before any follow-up edit — and compute `mutant_checks.py duration --start <request UTC> --end <PR UTC>`. Write the result with the PR link wherever the PR link is filled in (`ledger.py fill-pr <number>`, Execution-history `pending` cells, PR description), by editing the PR body (`gh pr edit --body-file` or the host's equivalent) and making **one** follow-up commit touching only the `.fix-mutants/` tracker and ledger (`docs(<scope>): record PR link`), pushed by hand. Never amend. That follow-up's own time is not counted. One PR per mutant in a single request: the clock of PR N+1 starts when PR N was created (PR 1 starts at the request UTC) — say so in the sync log. A bundled PR has one request → PR duration and one fix duration per target. The final message to the user gives the PR description's totals and one-sentence summaries (per-target kill type and fix duration, then request → PR).

PR description follows `references/pr-template.md` and nothing more, in this order (essentials first): Why, Totals, Review focus, Decisions needed (only when something is skipped: situation, concrete example, options, recommendation, so a human can decide), how each mutant was killed — no Recap table, Approach, Testing, Next steps, review-verdict or checklist sections (mutation-tool command, working directory, report timestamp and fingerprint, validation results, the Step 6 verdict, skipped mutants and leftover cleanup go in the tracker sync log). Mutants are grouped by kill type (🧪, ⚠️✏️, ⚠️🗑️, ⚠️📦, ⏭️), each mutant being one collapsed `<details>` block whose summary line has a number `n°n` (never `#n`, which the code host turns into an issue link; 1…N across the PR, in displayed order, quoted by Review focus) (never the report's id or idx — those stay in the tracking sync log), then one plain sentence of 14 words at most (what was missed, or what was deleted — no title prefix) the number of mutants it covers and the time; the source link and class go on the first line inside the block. Each block holds: clickable source link, class/method, explicit kill type with its emoji (`🧪 New test added`/`⚠️✏️ Existing test edited` (the recorded exception to the no-edit rule; commit type `test`)/`⚠️🗑️ Dead code deleted`/`⚠️📦 Code moved to another project`/`⏭️ Skipped (not fixed)`; an edited test, deleted or moved code also gets a ⚠️ quoted warning, since no fresh test proves it), a one-sentence plain-language summary, the **code before the change** and the **code with the mutation applied** and **how it was killed** (why existing tests missed it; the new test with name + link, or the removed/moved code with the Step 4 evidence; whether production code was touched). Totals as a subtraction table: the baseline's remaining count, one `−` row per kill type (new test, edited test, deleted, moved; skipped ones are not subtracted and go in the line under the table), and the remaining after this PR as the last row, total fix duration (sum of the per-target durations, by script), `Request → PR: 52m 10s` and, under the totals, the progress chart (the tracker Progress curve points plus a last `after this PR` point = remaining mutants); the final message to the user repeats the totals and the one-sentence summaries. The request → PR duration only exists once the PR does, so write `pending` in the description passed to `create-pr` and fill it in with the PR link (see above). Keep commit subjects ≤ 72 and the PR title ≤ 63 characters, and never cite branch-only SHAs (squash merge) — see `references/decision-rules.md` → _Commit and PR hygiene_.

## Multiple mutants

Process sequentially, one loop of Steps 2–5 per mutant, staging each verified target (`git add -A <paths>`) without committing; then Step 6 once on the whole staged diff and Step 7 once. Default to one PR per mutant (small
batches, easier review, and one clean ledger entry per PR) unless the user asks to bundle — decide,
don't ask (see Step 0). When bundling, follow the plan/count/cut rules in
`references/decision-rules.md`, and put skipped targets' ledger rows in the same commit. After the PR, leave the worktree/branch in place.
