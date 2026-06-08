#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_PATH="${1:-$REPO_ROOT/assets/AppIcon.icns}"
MODULE_CACHE_PATH="$REPO_ROOT/.build/module-cache"

mkdir -p "$(dirname "$OUTPUT_PATH")"
mkdir -p "$MODULE_CACHE_PATH"
/usr/bin/swift -module-cache-path "$MODULE_CACHE_PATH" "$SCRIPT_DIR/create-macos-icon.swift" "$OUTPUT_PATH"
