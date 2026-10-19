# Step 1 — Sync the ledger and the tracker against the baseline

Do this before picking a target (pre-compute). Ledger commands: `ledger.md`.

1. Compare the fetched `generated_at`/`source.sha` to the "Latest known baseline" header of the tracker.
   - **Unchanged** → skip re-sync, use the ledger as-is.
   - **New baseline** → check every ledger row against the new report (re-locate by `(file, mutator, snippet)`, not `id`
     or line — both drift), then `ledger.py update` it:
     - `fixed`/`resolved` row still alive, gone in an earlier baseline → `regressed`, flagged in the PR's _Review focus_ —
       don't silently re-fix it as if new.
     - `fixed`/`resolved` row still alive, never gone (a harmless sibling marked `resolved`) → mislabelled: `skipped` with
       its category, or `queued`. `fixed`/`resolved` only once the mutant is absent from the report.
     - `queued`/`skipped` row whose mutants are all absent → `resolved`, or `fixed` with the PR that killed them when known.
   - Then append a new Score trend row with the fresh counts, add the matching point (baseline date `MM-DD`, `remaining`)
     to the Progress curve chart under it (its `x-axis` and `line` lists; widen the `y-axis` range if the value falls
     outside it), and update the header block.
2. **Validate** (every run): `ledger.py validate` must pass; a skip whose category was retired fails it until the row is
   `update`d to `queued` with its path in `note`.
3. **Check for mutants already resolved on this branch.** The ledger only knows about mutants from _prior runs_; a mutant a
   _human_ fixed outside this skill, or one this same run's earlier increment touched incidentally, won't be in it yet.
   Before picking a target in Step 2: look the candidate up first (`ledger.py find --file <file>`); if absent, fall back
   to `git log <report.source.sha>..HEAD -- <candidate mutant file(s)>` — if a commit already touched the file, diff its
   content at `report.source.sha` against `HEAD` at the mutant's location (targets of this run are not in `git log`,
   nothing is committed yet: also compare `git diff --cached <base> -- <file>`), and if the mutated code no longer exists
   or was already covered, skip that mutant (note why, and record it in the ledger as part of Step 7) and move to the next
   one in report order.
