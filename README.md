# pxl

`pxl` is a small, modern, cross-platform image viewer built with PySide6 and
Pillow. It opens Pillow-readable image files and directories, supports thumbnail
browsing, zooming, transparency preview, and full-screen slideshows.

The app is distributed as a single Python script with PEP 723 inline dependency
metadata, so `uv` can install and run everything it needs. On Windows, the
project can build a small native `pxl.exe` launcher that delegates startup to a
bundled `uv.exe`.

## Features

- Open an image file or a directory of images.
- Browse all supported images in the current folder.
- View a responsive thumbnail grid.
- Run a full-screen slideshow with a configurable interval.
- Zoom in, zoom out, fit to window, or inspect at actual size.
- Preview transparent images over a checkerboard background.
- Display image details, including dimensions, format, source mode, zoom level,
  and folder position.
- Detect supported image formats from Pillow at runtime.

## Requirements

- Python 3.10 or newer.
- [`uv`](https://docs.astral.sh/uv/) for script execution and dependency
  management.

Runtime dependencies are declared inside `pxl.py`:

- Pillow 10.0.0 or newer.
- PySide6 6.7.0 or newer.

## Usage

Build the macOS app bundle:

```sh
./scripts/build-macos.sh
```

This creates `dist/Pxl.app`. The bundle contains the small Swift/AppKit
launcher, `pxl.py`, the app icon, and a pinned `uv` binary downloaded from the
`astral-sh/uv` GitHub release configured in `scripts/build-macos.sh`.

Build the distributable macOS disk image:

```sh
./scripts/make-dmg.sh
```

This creates `dist/Pxl-0.1.0-macos.dmg` with `Pxl.app` and an `/Applications`
symlink, plus a matching `.sha256` checksum file. Set `BUILD_APP=0` to package
an existing `dist/Pxl.app` without rebuilding it.

Run the macOS app normally:

```sh
open dist/Pxl.app
```

Open an image or directory with the macOS app:

```sh
open -a "$PWD/dist/Pxl.app" "/path/with spaces/image.png"
```

The Swift launcher is intentionally thin and runs as an `LSUIElement` helper so
the launcher itself does not appear as a second Dock app. It receives Finder
`openFiles` events, waits briefly on normal launch so double-click file opens do
not also run an empty invocation, redirects output to a log, then replaces
itself with:

```sh
Contents/Resources/uv run --gui-script Contents/Resources/pxl.py [image-or-directory]
```

Launcher output is written to `~/Library/Caches/pxl/pxl-launcher.log`. Startup
errors before `exec` still show an `NSAlert`; after a successful `exec`, the
Swift process no longer exists, so runtime failures should be checked in the
log. No `.xcodeproj` is generated or managed because Swift Package Manager is
enough for this minimal AppKit executable.

Useful macOS bundle checks:

```sh
plutil -lint dist/Pxl.app/Contents/Info.plist
codesign --verify --deep --strict --verbose=2 dist/Pxl.app
dist/Pxl.app/Contents/Resources/uv --version
```

Build the Windows launcher:

```powershell
.\scripts\build-windows.ps1
```

This creates `dist\pxl\pxl.exe`, copies `pxl.py`, and downloads a matching
`uv.exe` from the configured `astral-sh/uv` GitHub release. The native launcher
is built from `src\windows\launcher.c` with `cl.exe` or `clang-cl.exe`, so run
this from a Visual Studio Developer PowerShell or another shell with a Windows C
toolchain and resource compiler on `PATH`.

You can also call the native build script directly:

```powershell
.\scripts\build-windows-native.ps1
```

Run the viewer on Windows with:

```powershell
.\dist\pxl\pxl.exe [image-or-directory]
```

To also register `pxl.exe` for image files for the current Windows user:

```powershell
.\scripts\register-windows.ps1
```

You can build and register in one step:

```powershell
.\scripts\build-windows.ps1 -Register
```

The registration uses `HKCU` and does not require administrator rights. Windows
may still ask you to choose `pxl` once from "Open with" or Default apps before
it becomes the default image app.

Windows launcher output is written to
`%LOCALAPPDATA%\pxl\pxl-launcher.log`. If `pxl.py` exits with a non-zero status,
the launcher shows a `MessageBoxW` with the log path.

Run from source on any platform with:

```sh
uv run --script pxl.py [image-or-directory]
```

Open a directory in thumbnail mode:

```sh
uv run --script pxl.py --mode thumbnails path/to/images
```

Start a slideshow with a five-second interval:

```sh
uv run --script pxl.py --mode slideshow --interval 5 path/to/images
```

If no target is provided, `pxl` opens a file picker.

## Options

```text
target                  Optional image file or directory to open.
--mode image            Start in the normal image viewer.
--mode thumbnails       Start in the thumbnail grid.
--mode slideshow        Start in full-screen slideshow mode.
--interval SECONDS      Set the slideshow interval. Defaults to 3 seconds.
```

## Controls

| Action | Shortcut |
| --- | --- |
| Open file | Ctrl+O / Cmd+O |
| Open directory | Ctrl+D |
| Previous image | Left Arrow |
| Next image | Right Arrow |
| Thumbnail grid | T |
| Slideshow | F11 |
| Pause or resume slideshow | Space |
| Zoom in | Ctrl++ / Ctrl+= |
| Zoom out | Ctrl+- |
| Actual size | Ctrl+1 |
| Fit to window | Ctrl+0 |
| Return from thumbnails or slideshow | Esc |
| Quit from image view | Esc |
| Reload image | F5 |

You can also hold Ctrl and use the mouse wheel to zoom.

## Project Structure

```text
.
|-- assets/
|   |-- AppIcon.icns               # macOS app icon
|   `-- pxl.ico                    # Windows executable and app icon
|-- config/
|   `-- Info.plist                 # macOS bundle metadata and file associations
|-- Sources/
|   `-- Pxl/
|       `-- main.swift             # Minimal Swift/AppKit launcher
|-- scripts/
|   |-- build-macos.sh             # Builds dist/Pxl.app
|   |-- build-windows-native.ps1   # Builds native dist\pxl\pxl.exe and bundles uv.exe
|   |-- build-windows.ps1          # Builds dist\pxl\pxl.exe
|   |-- create-macos-icon.sh       # Regenerates assets/AppIcon.icns
|   |-- create-macos-icon.swift    # Draws and packs the macOS icon
|   |-- make-dmg.sh                # Builds dist/Pxl-<version>-macos.dmg
|   |-- create-windows-icon.ps1    # Regenerates assets\pxl.ico
|   `-- register-windows.ps1       # Registers image file associations
|-- src/
|   `-- windows/
|       `-- launcher.c             # Minimal native Windows launcher
|-- Package.swift                  # SwiftPM package for the macOS launcher
|-- pxl.py                         # Application source and inline dependency metadata
`-- README.md                      # Project documentation
```

## Development

Run the script during development with:

```sh
uv run --script pxl.py
```

The code is intentionally contained in one file. The main pieces are:

- `PxlViewer`, the main window and application controller.
- `ImageView`, the zoomable image canvas.
- `ThumbnailGrid`, the directory thumbnail browser.
- Pillow helper functions for loading, validating, and rendering images.
