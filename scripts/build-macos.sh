#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${APP_NAME:-Pxl}"
SWIFT_PRODUCT_NAME="${SWIFT_PRODUCT_NAME:-Pxl}"
BUNDLE_ID="${BUNDLE_ID:-io.github.shuic.pxl}"
VERSION="${VERSION:-0.1.0}"
MIN_SYSTEM_VERSION="${MIN_SYSTEM_VERSION:-13.0}"
UV_VERSION="${UV_VERSION:-0.11.19}"
UV_TARGET="${UV_TARGET:-}"

IMAGE_EXTENSIONS=(
  apng avif avifs blp bmp bufr bw cur dcx dds dib emf eps fit fits flc fli
  fpx ftc ftu gbr gd gd2 gif grib h5 hdf icb icns ico iim im imt j2c j2k
  jfif jpe jpeg jpg jpc jpf jp2 jpx mic mpeg mpg mpo msp pbm pcd pcx pgm png
  pnm ppm ps psd pxr qoi ras rgb rgba sgi spi tga tif tiff vda vst wal webp
  wmf xbm xpm xv
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$REPO_ROOT/dist/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
PLIST_PATH="$CONTENTS_DIR/Info.plist"
SWIFT_EXECUTABLE="$REPO_ROOT/.build/release/$SWIFT_PRODUCT_NAME"
ICON_PATH="$REPO_ROOT/assets/AppIcon.icns"
MODULE_CACHE_PATH="$REPO_ROOT/.build/module-cache"
UV_ARCHIVE_DIR=""

mkdir -p "$MODULE_CACHE_PATH"
export CLANG_MODULE_CACHE_PATH="$MODULE_CACHE_PATH"

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || fail "required file not found: $path"
}

detect_uv_target() {
  if [[ -n "$UV_TARGET" ]]; then
    printf '%s\n' "$UV_TARGET"
    return
  fi

  case "$(uname -m)" in
    arm64)
      printf 'aarch64-apple-darwin\n'
      ;;
    x86_64)
      printf 'x86_64-apple-darwin\n'
      ;;
    *)
      fail "unsupported macOS architecture: $(uname -m)"
      ;;
  esac
}

download_uv() {
  local target archive url temp_dir extracted_uv
  target="$(detect_uv_target)"
  archive="uv-$target.tar.gz"
  url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$archive"
  temp_dir="$(mktemp -d)"
  UV_ARCHIVE_DIR="$temp_dir"

  printf 'Downloading %s\n' "$url"
  curl --fail --location --retry 3 --output "$temp_dir/$archive" "$url"
  tar -xzf "$temp_dir/$archive" -C "$temp_dir"

  extracted_uv="$(find "$temp_dir" -type f -name uv -perm -111 -print -quit)"
  if [[ -z "$extracted_uv" ]]; then
    extracted_uv="$(find "$temp_dir" -type f -name uv -print -quit)"
  fi
  [[ -n "$extracted_uv" ]] || fail "uv binary was not found in $archive"

  cp "$extracted_uv" "$RESOURCES_DIR/uv"
  chmod 755 "$RESOURCES_DIR/uv"
}

set_plist_value() {
  local key="$1"
  local value="$2"
  /usr/libexec/PlistBuddy -c "Set :$key $value" "$PLIST_PATH"
}

replace_document_extensions() {
  /usr/libexec/PlistBuddy -c "Delete :CFBundleDocumentTypes:0:CFBundleTypeExtensions" "$PLIST_PATH" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :CFBundleDocumentTypes:0:CFBundleTypeExtensions array" "$PLIST_PATH"

  local extension normalized
  for extension in "${IMAGE_EXTENSIONS[@]}"; do
    normalized="${extension#.}"
    /usr/libexec/PlistBuddy -c "Add :CFBundleDocumentTypes:0:CFBundleTypeExtensions: string $normalized" "$PLIST_PATH"
  done
}

cleanup() {
  if [[ -n "$UV_ARCHIVE_DIR" && -d "$UV_ARCHIVE_DIR" ]]; then
    rm -rf "$UV_ARCHIVE_DIR"
  fi
}
trap cleanup EXIT

require_file "$REPO_ROOT/pxl.py"
require_file "$REPO_ROOT/assets/pxl.ico"
require_file "$REPO_ROOT/config/Info.plist"

"$SCRIPT_DIR/create-macos-icon.sh" "$ICON_PATH"

(
  cd "$REPO_ROOT"
  swift build --disable-sandbox -c release
)

require_file "$SWIFT_EXECUTABLE"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$RESOURCES_DIR/assets"

cp "$SWIFT_EXECUTABLE" "$MACOS_DIR/$APP_NAME"
cp "$REPO_ROOT/config/Info.plist" "$PLIST_PATH"
cp "$REPO_ROOT/pxl.py" "$RESOURCES_DIR/pxl.py"
cp "$ICON_PATH" "$RESOURCES_DIR/AppIcon.icns"
cp "$REPO_ROOT/assets/pxl.ico" "$RESOURCES_DIR/assets/pxl.ico"
chmod 755 "$MACOS_DIR/$APP_NAME" "$RESOURCES_DIR/pxl.py"

set_plist_value "CFBundleExecutable" "$APP_NAME"
set_plist_value "CFBundleIdentifier" "$BUNDLE_ID"
set_plist_value "CFBundleName" "$APP_NAME"
set_plist_value "CFBundleDisplayName" "$APP_NAME"
set_plist_value "CFBundleVersion" "$VERSION"
set_plist_value "CFBundleShortVersionString" "$VERSION"
set_plist_value "LSMinimumSystemVersion" "$MIN_SYSTEM_VERSION"
replace_document_extensions

download_uv

codesign --force --deep --sign - "$APP_DIR"

printf 'Built %s\n' "$APP_DIR"
