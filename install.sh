#!/usr/bin/env bash
# Install the fix-mutants skill into a project and generate its profile.
#
#   ./install.sh <project-dir> [--target claude|agents|both] [init_profile.py options]
#
# Examples:
#   ./install.sh ~/code/my-api
#   ./install.sh ~/code/monorepo/services/shop --production src/Shop --tests tests/Shop.Tests
#   ./install.sh ~/code/my-lib --stack generic
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill="${here}/skills/fix-mutants"

if [[ $# -lt 1 || "$1" == -h || "$1" == --help ]]; then
  sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi

project="$(cd "$1" && pwd)"
shift

target="claude"
passthrough=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) target="$2"; shift 2 ;;
    *) passthrough+=("$1"); shift ;;
  esac
done

git_root="$(git -C "${project}" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${git_root}" ]]; then
  echo "install: ${project} is not inside a git repository (the skill relies on git)" >&2
  exit 1
fi

install_into() {
  local destination="${git_root}/$1/fix-mutants"
  mkdir -p "$(dirname "${destination}")"
  rm -rf "${destination}"
  cp -R "${skill}" "${destination}"
  find "${destination}" -name __pycache__ -type d -prune -exec rm -rf {} +
  echo "installed: ${destination}"
}

case "${target}" in
  claude) install_into ".claude/skills" ;;
  agents) install_into ".agents/skills" ;;
  both) install_into ".claude/skills"; install_into ".agents/skills" ;;
  *) echo "install: --target must be claude, agents or both" >&2; exit 1 ;;
esac

installed="${git_root}/.claude/skills/fix-mutants"
[[ "${target}" == agents ]] && installed="${git_root}/.agents/skills/fix-mutants"

python3 "${installed}/scripts/init_profile.py" --repo "${project}" ${passthrough[@]+"${passthrough[@]}"}

cat <<NEXT

Next:
  1. Review ${project}/.fix-mutants/PROFILE.md (name your layers, check the mutation command).
  2. Run the mutation tool once to get a report (see .fix-mutants/report-fetch.md).
  3. In your agent: /fix-mutants   (it picks the first alive mutant, kills it, verifies, opens a PR)
NEXT
