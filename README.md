# fix-mutants

**An agent skill that kills surviving mutants — on any stack, in your project's own conventions, with the result checked by a script instead of taken on trust.**

Mutation testing tells you which lines of code your tests don't really check. Fixing those findings is slow, repetitive
and easy to get subtly wrong: a test written at the wrong layer, an existing assertion quietly loosened, a "Killed" status
that came from an unrelated test. `fix-mutants` gives your coding agent (Claude Code, or any agent that reads `SKILL.md`)
a strict procedure for it, plus small scripts that verify each claim mechanically.

```
mutation report ──► baseline ──► pick first alive mutant ──► find the right layer ──► one new test
                                                                                         │
 PR for a human ◄── independent review ◄── gate: test-only ◄── verify: killed by THAT test ◄┘
```

- **Tests first, production code as a last resort.** A new test per mutant, driven through the public entry point that
  really owns the code. Production code changes only when the code is provably dead or misplaced.
- **Never edits an existing test, assertion or fixture.** Enforced by a gate on the staged diff.
- **Verified outcomes.** `verify` matches the mutant by file + location + mutator + replacement and requires the report to
  say `Killed` **by the new test**. A deleted file must be gone, not empty.
- **Independent review.** A fresh sub-agent with no context reviews every change before it is committed.
- **One increment per mutant**, one PR for a human to approve. The skill never merges.
- **Adapts to your project** with a generated profile (`.fix-mutants/`): scope, mutation command, layers, conventions.

Origin: extracted from a skill used in batches on a production .NET codebase, then made stack-agnostic. Validated
here on **Stryker.NET (.NET 9)** and **StrykerJS (Jest)**; see [Supported stacks](#supported-stacks).

## Quickstart

Requirements: `git`, Python ≥ 3.9 (standard library only), your mutation tool, and an agent that supports skills.

```bash
git clone https://github.com/Amirault/fix-mutants.git
cd fix-mutants

./install.sh ~/code/my-project          # copies the skill, detects your stack, writes .fix-mutants/
```

Then:

1. Open `my-project/.fix-mutants/PROFILE.md` and name your layers (the only thing the installer cannot guess).
2. Produce a baseline report once — the generated `.fix-mutants/report-fetch.md` has the exact commands.
3. In your agent: `/fix-mutants` — or "fix the first surviving mutant".

The agent selects the first alive mutant, writes the test, runs the scoped mutation tool, verifies, reviews, commits on a
branch and opens a PR.

```bash
./install.sh <project-dir> --stack generic                       # any other tool: profile with TODOs
./install.sh <monorepo>/services/shop --production src/Shop --tests tests/Shop.Tests   # pick a project explicitly
./install.sh <project-dir> --target both                         # install under .claude/skills and .agents/skills
```

## Try it on a sandbox first

Two tiny projects with deliberately weak tests live in [`examples/`](examples). Each ships with its generated profile.

| Sandbox                              | Stack                     | Alive mutants |
| ------------------------------------ | ------------------------- | ------------- |
| [`examples/dotnet`](examples/dotnet) | .NET 9, NUnit, Stryker.NET 4.8 | 5        |
| [`examples/js`](examples/js)         | Node, Jest, StrykerJS 8   | 3             |

```bash
examples/check-sandbox.sh dotnet     # mutation run -> baseline -> list, fails if the count drifts
examples/check-sandbox.sh js
```

The CI workflow runs both, plus an install into a fresh copy of the sandbox that executes the generated commands verbatim (the same steps were run locally before publishing).

### What a run looks like (real output, .NET sandbox)

```text
$ mutant_checks.py baseline --repo . --report '…/StrykerOutput/*/reports/mutation-report.json' --out baseline.json
{"remaining": 6, "report_sha256": "1a5511ca…"}

$ mutant_checks.py list --repo . --baseline baseline.json --limit 1
{"index": 0, "where": "examples/dotnet/src/Shop/LoyaltyDiscount.cs:7", "mutator": "Equality mutation",
 "original": "yearsAsCustomer >= 5", "mutated": "yearsAsCustomer > 5"}
```

Nothing tests a customer with *exactly* five years, so `>=` → `>` survives. One new test:

```csharp
[Test]
public void Given_customer_with_exactly_five_years_When_applying_Should_give_ten_percent()
{
    Assert.That(LoyaltyDiscount.Apply(100m, 5), Is.EqualTo(90m));
}
```

Scoped mutation run, then the mechanical checks:

```text
$ dotnet stryker --project Shop.csproj --test-project Shop.Tests.csproj --mutate "**/LoyaltyDiscount.cs" --reporter json
$ mutant_checks.py verify … --mutant-id 2 --outcome test --new-test Given_customer_with_exactly_five_years_…
                                                                       # exit 0: Killed, by that test
$ mutant_checks.py gate --repo .
{"test_only": true, "staged": ["examples/dotnet/tests/Shop.Tests/LoyaltyDiscountTests.cs"]}
```

The ledger row and sync log of that run are in
[`examples/dotnet/.fix-mutants/MUTATION-TRACKING.md`](examples/dotnet/.fix-mutants/MUTATION-TRACKING.md), the commit in
`git log -- examples/dotnet/tests`. The JS sandbox has the same walkthrough (`calculateShipping(0, 1)` kills
`orderTotal < 0` → `<= 0`).

## How it works

| Step | What happens | Checked by |
| ---- | ------------ | ---------- |
| 0 | Scope the request (which mutants, which profile) | — |
| 1 | Fetch the report, verify its checksum, sync the ledger (skip what is already dealt with) | `baseline`, `list` |
| 2–3 | Read the mutant, trace the code up to the nearest public entry point, write **one** test there | `verify` (Killed **by the new test**) |
| 4 | Last resort: delete dead code / move misplaced code, with grep + `git log` evidence | `check` (file really gone, span really absent) |
| 5 | Scoped mutation re-run; every mutant outside the target file must be `Ignored` | `verify` |
| 6 | Independent sub-agent review, cold, from a checklist | the reviewer |
| 7 | One commit, tracker updated, PR from a template | `gate` (test-only diff) |

Rules the skill never bends are in [`skills/fix-mutants/SKILL.md`](skills/fix-mutants/SKILL.md) (non-negotiable rules) and
[`references/decision-rules.md`](skills/fix-mutants/references/decision-rules.md) (uncapped caller search, skip categories,
non-unique spans, measurement). A mutant whose fix would change runtime behaviour is **skipped with a reason**, never
"fixed" silently.

### The scripts (`skills/fix-mutants/scripts/mutant_checks.py`)

| Command    | Purpose |
| ---------- | ------- |
| `baseline` | Raw mutation-testing-elements report → alive mutants only, repo-relative paths, sha256 |
| `list`     | Alive mutants in report order, with original and mutated code |
| `check`    | After staging a removal/move: file physically absent and deletion staged; code span really gone |
| `verify`   | After the scoped run: target `Killed` by the named test, nothing outside scope active, no foreign test project |
| `gate`     | Fails unless the staged diff touches only test roots, `.fix-mutants/` and `gate_allow` |
| `duration` | Human-readable elapsed time between two UTC timestamps (`38m 29s`) |

`init_profile.py` detects the stack and writes the profile. All of it is plain Python, covered by
[36 unit tests](skills/fix-mutants/scripts/tests).

## Adapting it to your project

`./install.sh` does it automatically; this is what it generates and how to tune it.

```
your-project/
├── .claude/skills/fix-mutants/      # the skill (update it by re-running install.sh)
└── .fix-mutants/                    # YOURS, versioned with your code
    ├── profile.json                 # production_root, test_roots, report_schema_version, declaration_pattern, gate_allow
    ├── PROFILE.md                   # environment, scoped mutation command, layers, caller search, conventions
    ├── report-fetch.md              # how the report is obtained and verified
    └── MUTATION-TRACKING.md         # ledger, score trend, sync log, execution history
```

Things worth editing by hand: the **layers** section of `PROFILE.md`; `report-fetch.md` if CI already publishes a report
(replace the local run with your fetch + checksum); `gate_allow` if tests legitimately update coverage baselines or
snapshots. Format reference: [`references/profile.md`](skills/fix-mutants/references/profile.md).

### Supported stacks

| Tool | Status | Notes |
| ---- | ------ | ----- |
| Stryker.NET (C#) | ✅ validated end to end (4.8.1, .NET 9) | run from the test project folder; a solution file above it switches Stryker to solution mode |
| StrykerJS (JS/TS) | ✅ validated end to end (8.x, Jest) | add `ignorePatterns` for `.claude`, `.agents`, `.fix-mutants`, `reports` (generated profile says so) |
| Stryker4s, Pitest (elements reporter) | ⚠️ should work, not tested | `--stack generic`, fill the TODOs, check one round trip |
| mutmut, cosmic-ray, others | ❌ needs a converter | the verifier reads the [mutation-testing-elements](https://github.com/stryker-mutator/mutation-testing-elements) JSON schema |

## Limitations

- It reasons about code with an LLM: semantic checks (is this really dead? is this the right layer?) are guarded by the
  independent review and your PR review, not proven. The scripts prove the *mechanical* claims only.
- `check` verifies whole-file moves and unique removed spans; member moves out of a file that stays are skipped.
- Fully tested only with Claude Code; the procedure itself is plain markdown and works with any agent that follows `SKILL.md`.

## Repository layout

```
skills/fix-mutants/     the portable skill (SKILL.md, references/, scripts/)
install.sh              copy the skill into a project and generate its profile
examples/dotnet|js      sandboxes with a generated profile and one mutant already fixed
.github/workflows/      unit tests, both sandboxes, fresh-install run
```

## License

[MIT](LICENSE)
