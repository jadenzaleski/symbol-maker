#!/bin/sh
# Runs exactly what the GitHub Actions run: the code checks (ruff, ty), the tests, then the site build into ./dist.nosync.
#   ./ci.sh            build
#   ./ci.sh --serve    build, then preview at http://127.0.0.1:8000
#   ./ci.sh --limit 50 only convert the first 50 icons of each set (quick)
#   ./ci.sh --only tabler,iconoir   only build some sets
# Output goes to ./dist.nosync (the .nosync name keeps iCloud from syncing it), or to $OUT.
# Conversions are cached in ./build-cache.nosync (or $CACHE): icons that have not changed are not converted again.
# Python and the dev tools come from uv and uv.lock: `uv run --locked` refuses to run if the lock file is out of date.
set -eu
cd "$(dirname "$0")"
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is not installed. Install it with: $2" >&2
    exit 1
  fi
}
need uv "brew install uv"
need swiftdraw "scripts/install-swiftdraw.sh, then put .swiftdraw.nosync first on your PATH (the pinned version)"

log=$(mktemp)
trap 'rm -f "$log"' EXIT

# Checks: nothing is printed unless one fails, and then nothing is built.
check() {
  name=$1
  hint=$2
  shift 2
  if ! "$@" >"$log" 2>&1; then
    cat "$log" >&2
    echo "$name failed, so nothing was built.${hint:+ To fix: $hint}" >&2
    exit 1
  fi
}
check "ruff check" "uv run ruff check --fix ." uv run --locked ruff check .
check "ruff format" "uv run ruff format ." uv run --locked ruff format --check .
check "ty" "" uv run --locked ty check
echo "Checks: ruff, ruff format and ty passed"

# Tests: a one-line result, or the whole output when something fails.
if uv run --locked python -m unittest discover -s tests -t . >"$log" 2>&1; then
  awk '/^Ran /{n=$2; t=$5} /^OK/{extra=$0; sub(/^OK ?/,"",extra)} END{printf "Tests: %s passed in %s %s\n\n", n, t, extra}' "$log"
else
  cat "$log" >&2
  echo "Tests failed, so nothing was built." >&2
  exit 1
fi

uv run --locked python -m symbolmaker.sitebuild --out "${OUT:-dist.nosync}" --cache "${CACHE:-build-cache.nosync}" "$@"
