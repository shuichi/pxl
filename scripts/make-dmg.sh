#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${APP_NAME:-Pxl}"
VERSION="${VERSION:-0.1.0}"
BUILD_APP="${BUILD_APP:-1}"
DMG_NAME="${DMG_NAME:-$APP_NAME-$VERSION-macos.dmg}"
VOLUME_NAME="${VOLUME_NAME:-$APP_NAME $VERSION}"
DMG_CODESIGN_IDENTITY="${DMG_CODESIGN_IDENTITY:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
APP_DIR="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/$DMG_NAME"
STAGING_DIR="$DIST_DIR/dmg-stage"

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 was not found on PATH."
}

require_app() {
  [[ -d "$APP_DIR" ]] || fail "required app bundle not found: $APP_DIR"
}

cleanup() {
  rm -rf "$STAGING_DIR"
}
trap cleanup EXIT

require_command hdiutil
require_command ditto
require_command codesign
require_command shasum

mkdir -p "$DIST_DIR"

if [[ "$BUILD_APP" != "0" ]]; then
  "$SCRIPT_DIR/build-macos.sh"
fi

require_app
codesign --verify --deep --strict --verbose=2 "$APP_DIR"

rm -rf "$STAGING_DIR" "$DMG_PATH" "$DMG_PATH.sha256"
mkdir -p "$STAGING_DIR"

ditto "$APP_DIR" "$STAGING_DIR/$APP_NAME.app"
ln -s /Applications "$STAGING_DIR/Applications"

hdiutil create \
  -volname "$VOLUME_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  -imagekey zlib-level=9 \
  "$DMG_PATH"

if [[ -n "$DMG_CODESIGN_IDENTITY" ]]; then
  codesign --force --sign "$DMG_CODESIGN_IDENTITY" "$DMG_PATH"
fi

hdiutil verify "$DMG_PATH"
shasum -a 256 "$DMG_PATH" > "$DMG_PATH.sha256"

printf 'Built %s\n' "$DMG_PATH"
printf 'Wrote %s.sha256\n' "$DMG_PATH"
