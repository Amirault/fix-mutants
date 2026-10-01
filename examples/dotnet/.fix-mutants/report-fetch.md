# Report source — local run

This project has no published baseline: the report comes from a local, full mutation run on a clean checkout of the base
branch.

```bash
cd examples/dotnet/tests/Shop.Tests
dotnet stryker \
  --project Shop.csproj \
  --test-project Shop.Tests.csproj \
  --mutate "**/<relative/path/to/File>.cs" \
  --reporter cleartext --reporter json \
  --break-at 0
```

Then normalise it into a baseline (alive mutants only, repo-relative paths, sha256 of the raw report):

```bash
python3 examples/dotnet/.claude/skills/fix-mutants/scripts/mutant_checks.py baseline --repo . \
  --report 'examples/dotnet/tests/Shop.Tests'/StrykerOutput/*/reports/mutation-report.json --out /tmp/verified-baseline.json
python3 examples/dotnet/.claude/skills/fix-mutants/scripts/mutant_checks.py list --repo . --baseline /tmp/verified-baseline.json --limit 20
```

Rules: the `baseline` output's `report_sha256` is the integrity check — record it in the tracker. The array order of
`mutants` is the "reported alive" order; "the first one" means index order. If a CI job already publishes the report
somewhere (artifact, release asset, branch), replace this file with the fetch + checksum steps for that source.
