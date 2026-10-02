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
# The pinned upstream manifest uses iOS 15/macOS 12 constants but declares
# PackageDescription 5.3. Those constants require the 5.5 manifest API.
python3 - <<'PY'
from pathlib import Path
manifest = Path('vendor/wireguard-apple/Package.swift')
source = manifest.read_text()
if not source.startswith(('// swift-tools-version:5.3\n', '// swift-tools-version:5.5\n')):
    raise SystemExit('Unexpected WireGuard package manifest; review the pinned dependency')
manifest.write_text(source.replace('// swift-tools-version:5.3\n', '// swift-tools-version:5.5\n', 1))
# Xcode 16's module checks require the header to import its BSD integer types.
header = Path('vendor/wireguard-apple/Sources/WireGuardKitC/WireGuardKitC.h')
source = header.read_text()
if '#include <sys/types.h>' not in source:
    if '#include "key.h"' not in source:
        raise SystemExit('Unexpected WireGuard C header; review the pinned dependency')
    header.write_text(source.replace('#include "key.h"', '#include <sys/types.h>\n#include "key.h"', 1))
PY
xcodegen generate
printf 'Open WireGuardNexus.xcodeproj, set your team and bundle IDs, then build for a real iPhone.\n'
