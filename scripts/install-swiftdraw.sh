#!/bin/sh
# Builds the SwiftDraw version pinned in .swiftdraw-version from its source and installs it as DIR/swiftdraw
# (default: ./.swiftdraw.nosync). Homebrew only has the newest SwiftDraw, so this is how every build gets the same one.
#   scripts/install-swiftdraw.sh                 # then: export PATH="$PWD/.swiftdraw.nosync:$PATH"
#   scripts/install-swiftdraw.sh /some/folder
# Does nothing if that folder already holds the pinned version. Needs git and Swift (Xcode's command line tools).
set -eu
cd "$(dirname "$0")/.."
. ./.swiftdraw-version
dest=${1:-"$PWD/.swiftdraw.nosync"}

if [ -x "$dest/swiftdraw" ] && "$dest/swiftdraw" --help 2>&1 | grep -q "version $version\$"; then
  echo "SwiftDraw $version is already in $dest"
  exit 0
fi

src=$(mktemp -d)
trap 'rm -rf "$src"' EXIT
echo "Fetching SwiftDraw $version"
git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$version" https://github.com/swhitty/SwiftDraw.git "$src"
got=$(git -C "$src" rev-parse HEAD)
if [ "$got" != "$commit" ]; then
  echo "The SwiftDraw tag $version points at $got, not at the pinned $commit. Not building it." >&2
  exit 1
fi
echo "Building SwiftDraw $version"
(cd "$src" && swift build --configuration release --product swiftdrawcli --disable-sandbox 2>&1 | tail -n 3)
mkdir -p "$dest"
cp "$src/.build/release/swiftdrawcli" "$dest/swiftdraw"
echo "Installed SwiftDraw $version in $dest"
