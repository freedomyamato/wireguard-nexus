#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v xcodegen >/dev/null || { echo 'Install XcodeGen: brew install xcodegen'; exit 1; }
command -v go >/dev/null || { echo 'Install Go: brew install go'; exit 1; }
mkdir -p vendor
if [[ ! -d vendor/wireguard-apple/.git ]]; then
  git clone https://github.com/WireGuard/wireguard-apple.git vendor/wireguard-apple
fi
git -C vendor/wireguard-apple checkout --detach 2fec12a6e1f6e3460b6ee483aa00ad29cddadab1
xcodegen generate
printf 'Open WireGuardNexus.xcodeproj, set your team and bundle IDs, then build for a real iPhone.\n'
