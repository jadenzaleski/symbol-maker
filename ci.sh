#!/bin/sh
# Runs exactly what the GitHub Action runs: the tests, then the site build into ./dist.
#   ./ci.sh            build
#   ./ci.sh --serve    build, then preview at http://127.0.0.1:8000
#   ./ci.sh --limit 50 only convert the first 50 icons of each set (quick)
#   ./ci.sh --only tabler,iconoir   only build some sets
# Output goes to ./dist, or to $OUT (on iCloud Desktop use OUT=dist.nosync so it is not synced).
# Conversions are cached in ./build-cache.nosync (or $CACHE): icons that have not changed are not converted again.
set -eu
cd "$(dirname "$0")"
if ! command -v swiftdraw >/dev/null 2>&1; then
  echo "swiftdraw is not installed. Install it with: brew install swiftdraw" >&2
  exit 1
fi

# Tests: a one-line result, or the whole output when something fails.
log=$(mktemp)
trap 'rm -f "$log"' EXIT
if python3 -m unittest discover -s tests -t . >"$log" 2>&1; then
  awk '/^Ran /{n=$2; t=$5} /^OK/{extra=$0; sub(/^OK ?/,"",extra)} END{printf "Tests: %s passed in %s %s\n\n", n, t, extra}' "$log"
else
  cat "$log" >&2
  echo "Tests failed, so nothing was built." >&2
  exit 1
fi

python3 -m symbolmaker.sitebuild --out "${OUT:-dist}" --cache "${CACHE:-build-cache.nosync}" "$@"
