#!/usr/bin/env bash
# Build the React artifact and bind it to the exact clean source commit.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -z "$(git -C "$REPO" status --porcelain --untracked-files=normal)" ] || {
  echo "FAIL: release worktree is dirty" >&2
  exit 1
}
SHA="$(git -C "$REPO" rev-parse HEAD)"
( cd "$REPO/web-react" && npm run build )
[ -d "$REPO/web-react/build/static" ] || { echo "FAIL: React build output missing" >&2; exit 1; }
printf '%s\n' "$SHA" >"$REPO/web-react/build/.tradewave-source-sha"
echo "React release built for $SHA"
