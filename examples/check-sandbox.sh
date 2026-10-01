#!/usr/bin/env bash
# Full round trip on a sandbox: mutation run -> baseline -> list. Fails if the alive count drifts.
#   examples/check-sandbox.sh dotnet   # expects 5 alive mutants
#   examples/check-sandbox.sh js       # expects 3 alive mutants
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tool="${root}/skills/fix-mutants/scripts/mutant_checks.py"
sandbox="${1:?usage: check-sandbox.sh dotnet|js}"
out="$(mktemp -d)"

case "${sandbox}" in
  dotnet)
    expected=5
    (cd "${root}/examples/dotnet" && dotnet tool restore >/dev/null)
    (cd "${root}/examples/dotnet/tests/Shop.Tests" && rm -rf StrykerOutput && \
      dotnet stryker --project Shop.csproj --test-project Shop.Tests.csproj \
        --reporter json --break-at 0 >/dev/null)
    report="${root}/examples/dotnet/tests/Shop.Tests/StrykerOutput/*/reports/mutation-report.json"
    ;;
  js)
    expected=3
    (cd "${root}/examples/js" && npm ci --no-audit --no-fund >/dev/null && rm -rf reports && \
      npx stryker run --reporters json >/dev/null)
    report="${root}/examples/js/reports/mutation/mutation.json"
    ;;
  *) echo "unknown sandbox: ${sandbox}" >&2; exit 2 ;;
esac

cd "${root}"
python3 "${tool}" --profile "examples/${sandbox}/.fix-mutants/profile.json" baseline \
  --repo . --report "${report}" --out "${out}/baseline.json" | tee "${out}/summary.json"
python3 "${tool}" list --repo . --baseline "${out}/baseline.json"
actual="$(python3 -c "import json;print(json.load(open('${out}/baseline.json'))['counts']['remaining'])")"
if [[ "${actual}" != "${expected}" ]]; then
  echo "FAIL: ${actual} alive mutants, expected ${expected}" >&2
  exit 1
fi
echo "OK: ${sandbox} sandbox has ${actual} alive mutants, as expected"
