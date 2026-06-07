"""Windows launcher for pxl.exe.

The executable built from this file stays intentionally small. It delegates
dependency resolution and application startup to uv, while preserving argv so
file association launches behave the same as direct command-line launches.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_NAME = "pxl"
CREATE_NO_WINDOW = 0x08000000


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)


def main() -> int:
    app_dir = application_dir()
    script_path = app_dir / "pxl.py"
    if not script_path.exists():
        show_error(f"Could not find pxl.py next to pxl.exe:\n\n{script_path}")
        return 1

    uv_path = shutil.which("uv")
    if uv_path is None:
        show_error(
            "uv was not found on PATH.\n\n"
            "Install uv or add it to PATH, then start pxl.exe again."
        )
        return 1

    command = [
        uv_path,
        "run",
        "--gui-script",
        str(script_path),
        *sys.argv[1:],
    ]
    log_path = Path(tempfile.gettempdir()) / "pxl-launcher.log"
    try:
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command,
                check=False,
                creationflags=CREATE_NO_WINDOW,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
    except OSError as exc:
        show_error(f"Could not start pxl through uv:\n\n{exc}")
        return 1

    if completed.returncode != 0:
        show_error(
            f"pxl exited with code {completed.returncode}.\n\n"
            f"Details were written to:\n{log_path}"
        )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
