# Mutation Testing — Progress Tracker

Ledger of every mutant dealt with: `🟢 Fixed`, `⚪ Resolved-incidentally`, `🟡 Skipped`, `🔴 Regressed`.
Not a mirror of the alive list (that lives in the baseline report). Updated in the same commit as each fix.

## Latest known baseline

- `generated_at`: 2026-10-01
- `source.sha`: first commit of this repository
- `report_sha256`: 1a5511ca703f49b9d431b47eba2e8cbef9d027300963ca5c6fc6e495e202f5c4
- counts: Killed 12 · Survived 5 · NoCoverage 1 · Ignored 8 · **remaining 6**

## Score trend

| Synced (UTC) | Baseline `generated_at` | remaining | Killed | Survived | NoCoverage | Note |
| ------------ | ----------------------- | --------- | ------ | -------- | ---------- | ---- |

## Ledger

| File | Line (at baseline) | Mutator | Status | PR / commit | Note |
| ---- | ------------------ | ------- | ------ | ----------- | ---- |
| `LoyaltyDiscount.cs` | 7 | Equality mutation (`>= 5` → `> 5`) | 🟢 Fixed | walkthrough commit | boundary: exactly five years had no test |

## Execution history

| Baseline / target | Outcome | UTC start | UTC end | Fix duration | Agent / model | Reviewer model | PR | Request → PR |
| ----------------- | ------- | --------- | ------- | ------------ | ------------- | -------------- | -- | ------------ |

## Sync log

Newest first: baseline used, what the staleness check skipped, target selected and why, path taken, ledger delta.

- **Walkthrough run** — baseline above; selected report index 0 (first alive); path: new test
  `Given_customer_with_exactly_five_years_When_applying_Should_give_ten_percent`; scoped run killed it
  (`killedBy` contains the new test), `verify` exit 0, `gate` passed. Ledger delta: +1 fixed, remaining 6 → 5.
  The sibling `>= 5` → `< 5` shares the location and mutator; `verify` tells them apart by replacement text.
