# Mutation Testing — Progress Tracker

Progress of the `fix-mutants` skill on this project: baselines, score trend, attempts and one sync-log entry per run.
The alive-mutant list lives in the baseline report; every examined mutant has a row in `ledger.jsonl`.
This file and `ledger.jsonl` change in the PR's single code commit (Step 7).

## Latest known baseline

- `generated_at`: —
- `source.sha`: —
- `report_sha256`: —
- counts: —

## Score trend

| Synced (UTC) | Baseline `generated_at` | remaining | Killed | Survived | NoCoverage | Note |
| ------------ | ----------------------- | --------- | ------ | -------- | ---------- | ---- |

## Ledger

`ledger.jsonl` (one JSON row per examined mutant), read and written only with `scripts/ledger.py` (`references/ledger.md`).

## Execution history

| Baseline / target | Outcome | UTC start | UTC end | Fix duration | Agent / model | Reviewer model | PR | Request → PR |
| ----------------- | ------- | --------- | ------- | ------------ | ------------- | -------------- | -- | ------------ |

## Sync log

Newest first: baseline used, what the staleness check skipped, target selected and why, path taken, ledger delta.
