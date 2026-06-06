# pxl

`pxl` is a small, modern, cross-platform image viewer built with PySide6 and
Pillow. It opens Pillow-readable image files and directories, supports thumbnail
browsing, zooming, transparency preview, and full-screen slideshows.

The app is distributed as a single Python script with PEP 723 inline dependency
metadata, so `uv` can install and run everything it needs.

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

Run the viewer directly on Unix-like systems:

```sh
./pxl.py [image-or-directory]
```

On Windows PowerShell, use the bundled command wrapper:

```powershell
.\pxl.cmd [image-or-directory]
```

If the project directory is on `PATH`, you can run it as `pxl`:

```powershell
pxl [image-or-directory]
```

Or run it through `uv`:

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
|-- pxl.py      # Application source and inline dependency metadata
|-- pxl.cmd     # Windows command wrapper for PowerShell and cmd.exe
`-- README.md   # Project documentation
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
