#!/bin/sh
# Runs exactly what the GitHub Action runs: the tests, then the site build into ./dist.
#   ./ci.sh            build
#   ./ci.sh --serve    build, then preview at http://127.0.0.1:8000
#   ./ci.sh --limit 50 only convert the first 50 icons (quick)
# Output goes to ./dist, or to $OUT (on iCloud Desktop use OUT=dist.nosync so it is not synced).
set -eu
cd "$(dirname "$0")"
if ! command -v swiftdraw >/dev/null 2>&1; then
  echo "swiftdraw is not installed. Install it with: brew install swiftdraw" >&2
  exit 1
fi
python3 -m unittest discover -s tests -t .
python3 -m symbolmaker.sitebuild --out "${OUT:-dist}" "$@"
