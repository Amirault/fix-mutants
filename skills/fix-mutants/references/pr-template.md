# PR template — mutation-testing fix

Body of every `fix-mutants` PR. Goal: a reviewer understands each kill and decides in one read. Nothing else belongs in the
description (tool command, report fingerprint, validation results, review verdict go in the tracker's sync log).

## How to fill it

1. Number the mutants 1…N in **displayed order** (group by group, groups in the order of the kill-type table below).
2. For each mutant, fill one block (the template has one complete block per kill type: copy it, replace every `{{placeholder}}`).
3. Fill Totals from the per-mutant results, then Review focus, then Why.
4. Check every link (`git cat-file -e <ref>:<path>`), then open the PR with `Request → PR` set to `pending`.
5. After the PR is opened, replace `pending` with the duration (`gh pr edit --body-file`) — see `SKILL.md` Step 7.
6. Delete the sections and blocks that do not apply (a kill type with no mutant has no block and no section). Never leave
   `none` or an empty placeholder.

## Where each value comes from

| Placeholder                                                                                                | Source                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `{{baseline_date}}`                                                                                        | report `generated_at`, date only                                                                                                                                                                                                                                                                                                                                             |
| `{{baseline_sha}}`                                                                                         | report `source.sha`, first 10 characters                                                                                                                                                                                                                                                                                                                                     |
| `{{pipeline_name}}`, `{{workflow_url}}`                                                                    | the pipeline that publishes the baseline, as the profile's _Report source_ gives it (PricingApi: `Pricing/PricingApi Mutation Baseline`)                                                                                                                                                                                                                                                               |
| `{{targets}}`                                                                                              | number of dedicated targets selected in Step 0 (incidental siblings are not counted here, only in the kill-type counts)                                                                                                                                                                                                                                                      |
| `{{remaining_before}}`                                                                                     | `remaining` of this baseline in the tracker's Score trend                                                                                                                                                                                                                                                                                                       |
| `{{count_new_test}}`, `{{count_edited_test}}`, `{{count_deleted}}`, `{{count_moved}}`, `{{count_skipped}}` | mutants of that kill type, **including incidental siblings** killed or removed by the same change                                                                                                                                                                                                                                                                            |
| `{{remaining_after}}`                                                                                      | `{{remaining_before}}` − new test − edited test − deleted − moved (skipped are not subtracted)                                                                                                                                                                                                                                                                               |
| `{{total_time}}`                                                                                           | sum of the **known** per-mutant fix durations, computed by script (`mutant_checks.py duration`), never by hand; a mutant with an `unknown` time adds nothing                                                                                                                                                                                                                 |
| `{{n}}`                                                                                                    | the mutant's number, 1…N                                                                                                                                                                                                                                                                                                                                                     |
| `{{sentence}}`                                                                                             | your own words, 14 words at most: what was missed (🧪, ⚠️✏️), what was removed or moved (⚠️🗑️, ⚠️📦), or why nothing was done (⏭️)                                                                                                                                                                                                                                           |
| `{{mutants}}`                                                                                              | number of report mutants this block covers (`1 mutant`, `6 mutants`)                                                                                                                                                                                                                                                                                                         |
| `{{time}}`                                                                                                 | that target's fix duration, human readable (`38m 29s`), or `unknown`                                                                                                                                                                                                                                                                                                         |
| `{{source_url}}`                                                                                           | mutated or deleted code: `blob/{{baseline_sha}}/<repo path>#L<line>`                                                                                                                                                                                                                                                                                                         |
| `{{test_url}}`                                                                                             | new/edited test or moved code: `blob/<sha of the commit that adds it>/<repo path>#L<line>` (line of the test method); filled **after the commit and before `create-pr`**, never a branch name                                                                                                                                                                                |
| `{{code_before}}` / `{{code_mutated}}`                                                                     | `code_before`: original lines from the baseline commit. `code_mutated`: the published report has **no replacement text** (only location and mutator name), so rebuild it from the original and the mutator, or read `replacement` in the raw JSON of your scoped run; for a statement removal rewrite the surrounding lines. One variant per sibling mutant when they differ |
| `{{chart_points}}`                                                                                         | the Progress curve points of the tracker (x labels = the report's `generated_at` date, `MM-DD`), then `{{remaining_after}}` as the last point (label `after this PR`)                                                                                                                                                                                             |
| `{{axis_min}}`, `{{axis_max}}`                                                                             | chart y-axis bounds: round down/up so every point fits (for example 700 and 1300)                                                                                                                                                                                                                                                                                            |
| `{{File:line}}`, `{{Class.Method}}`, `{{TestFile}}`, `{{NewFile}}`                                | file with the line of the mutated code, class and method, test file, new location of moved code                                                                                                                                                                                                                                                                              |

## Rules

- **Plain words**: no acronyms, no tool jargon. Never write the tool's raw labels (`Killed`, `Survived`,
  `Conditional (true) mutation`) without their plain meaning. Mutants have a number, never a title and never the report's
  id or index (`idx 223` belongs in the sync log).
- **Numbers**: write `n°8`, never `#8` (the code host turns `#8` into a link to issue 8).
- **Short**: summary line = number + one sentence + mutant count + time, nothing else. "How it was killed" = one or two
  sentences. Review focus = at most 3 lines, mutants cited by number only.
- **HTML in `<summary>`**: use `<b>`, `<code>`, `<a href>` (Markdown is not rendered there). Keep a blank line after
  `<summary>` and before `</details>` so code blocks render.
- **Decisions needed**: written for someone who has not read the code. Always a concrete example with real values, never
  an abstract description. One entry per skipped mutant whose outcome depends on a business choice (real defect); an
  equivalent, unclaimable or unobservable mutant needs no example, one line in its block is enough. The section is absent
  when nothing is skipped.
- **Warnings**: every kill type except 🧪 and ⏭️ carries a quoted ⚠️ line, because no fresh test proves the fix.
- **Review focus**, riskiest first: deleted or moved code, edited tests, points where the independent review disagreed,
  mutants left alive as harmless or equivalent (for example "n°2 — equivalent mutant left alive: agree?"). "Nothing unusual" if none.
- **Totals** read as a subtraction from the baseline; the chart repeats it as a curve.
- **Same recap for the user**: the final message repeats Totals and the one-sentence summaries.
- **Title**: `<type>(<scope per the profile>): <description>`, at most 63 characters; type `test` or `refactor`, never `fix`.
- Never reference branch-only commit shas in text; links to tests use the adding commit's sha (a PR's commits stay reachable).

## Kill types (in displayed order)

| Kill type                              | Meaning                                                                                                                                                                                             | Commit type |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| 🧪 **New test added**                  | A new test fails when the change is applied and passes on the real code.                                                                                                                            | `test`      |
| ⚠️✏️ **Existing test edited**          | An existing test, assertion or fixture was changed so the mutant now fails it. Forbidden by default; recorded exceptions: a test adapted after dead code was deleted (commit type `refactor` then). | `test`      |
| ⚠️🗑️ **Dead code deleted**             | The code can never run, so it was removed instead of tested, with the tests that existed only for it. **Production code changed.**                                                                  | `refactor`  |
| ⚠️📦 **Code moved to another project** | The code belongs outside the mutation scope; moved as-is. Not killed. **Production code changed.**                                                                                                  | `refactor`  |
| ⏭️ **Skipped (not fixed)**             | Not fixable, or equivalent: fixing would change runtime behaviour, or the change does not alter observable behaviour so no test can fail (**equivalent mutant**). Left for a human decision.        | —           |

## Template

````markdown
## Why

A scheduled pipeline (it runs every day), [{{pipeline_name}}]({{workflow_url}}), computes a **baseline report** asynchronously: it applies small deliberate changes ("mutants") to the production code and records which ones no test notices. This PR does not compute anything itself: it **works from that published report** (generated {{baseline_date}}, on commit `{{baseline_sha}}`) and acts on the next {{targets}} mutants it lists that no earlier PR has dealt with.

_A mutant is **killed** when a test fails because of the change; an **alive** mutant means that code is not really checked._

## Totals

|                                      |                 Mutants |
| ------------------------------------ | ----------------------: |
| Remaining in the baseline            |    {{remaining_before}} |
| − 🧪 New test added                  |     −{{count_new_test}} |
| − ⚠️✏️ Existing test edited          |  −{{count_edited_test}} |
| − ⚠️🗑️ Dead code deleted             |      −{{count_deleted}} |
| − ⚠️📦 Code moved to another project |        −{{count_moved}} |
| **= Remaining after this PR**        | **{{remaining_after}}** |

⏭️ Skipped (not fixed): {{count_skipped}} (not subtracted) · ⏱ {{total_time}} total time on mutants · request → PR: pending

<details>
<summary>Progress chart</summary>

```mermaid
xychart-beta
    title "Mutants remaining, per baseline"
    x-axis ["MM-DD", "MM-DD", "after this PR"]
    y-axis "Remaining mutants" {{axis_min}} --> {{axis_max}}
    line [{{chart_points}}]
```

</details>

## Review focus

1. **n°{{n}}**, **n°{{n}}** — {{one short question}} (skipped mutants: "see Decisions needed")

## Decisions needed

<!-- Only when the PR has ⏭️ skipped mutants. One entry per skipped mutant (or group), numbered like its block below. -->

**n°{{n}}** — {{the question to settle, in one sentence}}

- **Situation**: {{what the code does today and what the missed test would have to assume, in plain words}}
- **Example**: {{a concrete input}} → today: {{current result}}; the alternative: {{result if behaviour changed}}
- **Options**: (a) leave as is — {{consequence}} · (b) pin today's behaviour with a test — {{consequence}} · (c) change the behaviour in a dedicated PR — {{consequence}}
- **Recommendation**: {{one option and why}}

## How each mutant was killed

### 🧪 New test added ({{count_new_test}} mutants)

<details>
<summary><b>n°{{n}}</b> · {{sentence}} · <b>{{mutants}}</b> · ⏱ <code>{{time}}</code></summary>

**Source**: [`{{File:line}}`]({{source_url}}) · `{{Class.Method}}`

**Code before the change**

```csharp
{{code_before}}
```

**Code with the mutation applied** ({{plain meaning of the change}})

```csharp
{{code_mutated}}
```

<!-- Siblings with a different mutation: add one more labelled block per variant. -->

**How it was killed**: {{why no test noticed}}. [`{{TestFile}}`]({{test_url}}) now {{what the test does and expects}}.

</details>

### ⚠️✏️ Existing test edited ({{count_edited_test}} mutants)

<details>
<summary><b>n°{{n}}</b> · {{sentence}} · <b>{{mutants}}</b> · ⏱ <code>{{time}}</code></summary>

> ⚠️ **An existing test was changed** — check the edit keeps the test's original intent.

**Source**: [`{{File:line}}`]({{source_url}}) · `{{Class.Method}}`

**Code before the change**

```csharp
{{code_before}}
```

**Code with the mutation applied** ({{plain meaning of the change}})

```csharp
{{code_mutated}}
```

**How it was killed**: {{what the test checked before and missed}}. [`{{TestFile}}`]({{test_url}}) now {{what it expects}}.

</details>

### ⚠️🗑️ Dead code deleted ({{count_deleted}} mutants)

<details>
<summary><b>n°{{n}}</b> · {{sentence}} · <b>{{mutants}}</b> · ⏱ <code>{{time}}</code></summary>

> ⚠️ **Production code changed, not proven by a test** — check nothing reaches it (reflection, dependency injection).

**Source**: [`{{File:line}}`]({{source_url}}) · `{{Class.Method}}`

**Code before the change**

```csharp
{{code_before}}
```

**Code with the mutation applied** ({{plain meaning of the change}})

```csharp
{{code_mutated}}
```

**How it was killed**: {{evidence in one or two sentences: no caller in any layer, not registered, change history}}. Deleted.

</details>

### ⚠️📦 Code moved to another project ({{count_moved}} mutants)

<details>
<summary><b>n°{{n}}</b> · {{sentence}} · <b>{{mutants}}</b> · ⏱ <code>{{time}}</code></summary>

> ⚠️ **Production code moved, not proven by a test** — check the move is as-is and the new location is right.

**Source**: [`{{File:line}}`]({{source_url}}) · `{{Class.Method}}`

**Code before the change**

```csharp
{{code_before}}
```

**How it was killed**: not killed, out of the mutation scope. {{why the code belongs elsewhere}}; now in [`{{NewFile}}`]({{test_url}}).

</details>

### ⏭️ Skipped (not fixed) ({{count_skipped}} mutants)

<details>
<summary><b>n°{{n}}</b> · {{sentence}} · <b>{{mutants}}</b> · ⏱ <code>{{time}}</code></summary>

**Source**: [`{{File:line}}`]({{source_url}}) · `{{Class.Method}}`

**Code before the change**

```csharp
{{code_before}}
```

**How it was killed**: not fixed. See _Decisions needed_ n°{{n}}.

</details>
````
