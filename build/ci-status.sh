#!/usr/bin/env bash
# Wait for the GitHub Actions CI run of a commit and print its conclusion.
# Usage: build/ci-status.sh <sha> [timeout_seconds]
# Exit 0 = success, 1 = failure/cancelled, 2 = timed out, 3 = no run appeared.
# Uses `gh api` (authenticated REST) when available, else the public API; polls every 30 s.
set -uo pipefail
sha="$1"; timeout="${2:-1800}"; repo="Stingcompiler/hotel-mg"
deadline=$(( $(date +%s) + timeout )); seen=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if command -v gh >/dev/null; then
    json=$(gh api "repos/$repo/actions/runs?head_sha=$sha" 2>/dev/null || echo '{}')
  else
    json=$(curl -fsS "https://api.github.com/repos/$repo/actions/runs?head_sha=$sha" || echo '{}')
  fi
  line=$(python3 - "$json" <<'PY'
import json, sys
runs = json.loads(sys.argv[1] or "{}").get("workflow_runs", [])
runs = [r for r in runs if r["name"] == "CI"]
if not runs:
    print("none")
else:
    r = runs[0]
    print(r["status"], r["conclusion"] or "-", r["html_url"])
PY
)
  set -- $line
  case "$1" in
    none) seen=$((seen+1)); [ "$seen" -ge 10 ] && { echo "no CI run found for $sha"; exit 3; } ;;
    completed) echo "CI $2 $3"; [ "$2" = success ] && exit 0 || exit 1 ;;
    *) : ;;
  esac
  sleep 30
done
echo "CI timed out for $sha"; exit 2
