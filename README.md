# pxl

`pxl` is a small, modern, cross-platform image viewer built with PySide6 and
Pillow. It opens Pillow-readable image files and directories, supports thumbnail
browsing, zooming, transparency preview, and full-screen slideshows.

The app is distributed as a single Python script with PEP 723 inline dependency
metadata, so `uv` can install and run everything it needs. On Windows, the
project can build a small `pxl.exe` launcher that delegates startup to `uv`.

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

Build the Windows launcher:

```powershell
.\scripts\build-windows.ps1
```

This creates `dist\pxl\pxl.exe`. Run the viewer on Windows with:

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
|   `-- pxl.ico                    # Windows executable and app icon
|-- scripts/
|   |-- build-windows.ps1          # Builds dist\pxl\pxl.exe
|   |-- create-windows-icon.ps1    # Regenerates assets\pxl.ico
|   |-- register-windows.ps1       # Registers image file associations
|   `-- windows_launcher.py        # Source for the small pxl.exe launcher
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
