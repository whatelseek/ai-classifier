#!/usr/bin/env bash
# Push branch and open PR via GitHub CLI (requires: gh auth login).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="${BRANCH:-cursor/k8s-joey-deploy-594f}"
BASE="${BASE:-main}"

cd "$ROOT"
gh auth status >/dev/null

git push -u origin "$BRANCH"

gh pr create \
  --base "$BASE" \
  --head "$BRANCH" \
  --title "Deploy IT ticket classifier on K8s with Spark Joey and remote Docling" \
  --body-file "$ROOT/scripts/pr-body.md"

echo "PR created:"
gh pr view --web 2>/dev/null || gh pr view --json url -q .url