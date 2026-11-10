#!/bin/bash
# Build and install "Claude Link Router.app" into ~/Applications. Does not change the default browser.
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
app="$HOME/Applications/Claude Link Router.app"
mkdir -p "$app/Contents/MacOS"
cp "$src/Info.plist" "$app/Contents/Info.plist"
# Name the target: left to itself, swiftc here stamped a minimum macOS newer than the one running,
# and Launch Services then refuses to start the app (error -10825).
swiftc -O -target "$(uname -m)-apple-macos13.0" -o "$app/Contents/MacOS/ClaudeLinkRouter" "$src/LinkRouter.swift"
codesign --force --sign - "$app"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app"
echo "installed: $app"
