#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pillow>=10.0.0",
#   "pyside6>=6.7.0",
# ]
# ///
"""A modern cross-platform image viewer.

Run with:
    uv run --script pxl.py [image | directory]
    uv run --script pxl.py --mode thumbnails directory
    uv run --script pxl.py --mode slideshow --interval 5 directory

On Windows, build pxl.exe with:
    ./scripts/build-windows.ps1
"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
import sys
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFontDatabase,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "pxl"
APP_DISPLAY_NAME = "Pxl"
APP_VERSION = "0.1.0"
APP_USER_MODEL_ID = "io.github.shuic.pxl"
DEFAULT_SLIDESHOW_INTERVAL = 3.0
THUMBNAIL_SIZE = 176
THUMBNAIL_ITEM_WIDTH = 220
THUMBNAIL_ITEM_HEIGHT = 238
LOAD_CACHE_SIZE = 5
THUMBNAIL_BATCH_SIZE = 32
THUMBNAIL_PRIORITY_FALLBACK_COUNT = 64
VALID_MODES = ("image", "thumbnails", "slideshow")
Image.init()
SUPPORTED_EXTENSIONS = frozenset(
    ext.lower()
    for ext, format_name in Image.registered_extensions().items()
    if format_name in Image.OPEN
)
IMAGE_OPEN_ERRORS = (
    OSError,
    ValueError,
    SyntaxError,
    Image.DecompressionBombError,
)
ZOOM_STEPS = [
    0.05,
    0.075,
    0.1,
    0.125,
    0.15,
    0.2,
    0.25,
    0.33,
    0.5,
    0.67,
    0.75,
    1.0,
    1.25,
    1.5,
    2.0,
    3.0,
    4.0,
    6.0,
    8.0,
    12.0,
    16.0,
]


@dataclass(frozen=True)
class LoadedImage:
    path: Path
    image: Image.Image
    source_format: str
    source_mode: str
    has_transparency: bool


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Open and inspect Pillow-readable images in a modern PySide6 viewer.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        type=Path,
        help="Image file or directory to open.",
    )
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        default="image",
        help="Initial display mode.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_SLIDESHOW_INTERVAL,
        help="Slideshow interval in seconds.",
    )
    return parser.parse_args(argv)


def has_supported_extension(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def image_dialog_filter() -> str:
    patterns = []
    for extension in sorted(SUPPORTED_EXTENSIONS):
        patterns.append(f"*{extension}")
        patterns.append(f"*{extension.upper()}")
    return f"Images ({' '.join(patterns)});;All files (*)"


def normalized_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resource_path(*parts: str) -> Path:
    return Path(__file__).resolve().parent.joinpath(*parts)


def app_icon() -> QIcon:
    icon_path = resource_path("assets", "pxl.ico")
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


def configure_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        pass


def configure_macos_app_identity() -> None:
    if sys.platform != "darwin":
        return

    display_name = os.environ.get("PXL_MACOS_APP_NAME", APP_DISPLAY_NAME)
    try:
        objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p

        def selector(name: bytes) -> int:
            return objc.sel_registerName(name)

        def objc_class(name: bytes) -> int:
            return objc.objc_getClass(name)

        def send_id(
            receiver: int,
            selector_name: bytes,
            *args: object,
            argtypes: tuple[object, ...] = (),
        ) -> int:
            objc.objc_msgSend.restype = ctypes.c_void_p
            objc.objc_msgSend.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                *argtypes,
            ]
            return objc.objc_msgSend(receiver, selector(selector_name), *args)

        def send_bool(
            receiver: int,
            selector_name: bytes,
            *args: object,
            argtypes: tuple[object, ...] = (),
        ) -> bool:
            objc.objc_msgSend.restype = ctypes.c_bool
            objc.objc_msgSend.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                *argtypes,
            ]
            return bool(objc.objc_msgSend(receiver, selector(selector_name), *args))

        def send_void(
            receiver: int,
            selector_name: bytes,
            *args: object,
            argtypes: tuple[object, ...] = (),
        ) -> None:
            objc.objc_msgSend.restype = None
            objc.objc_msgSend.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                *argtypes,
            ]
            objc.objc_msgSend(receiver, selector(selector_name), *args)

        def nsstring(value: str) -> int:
            return send_id(
                objc_class(b"NSString"),
                b"stringWithUTF8String:",
                value.encode("utf-8"),
                argtypes=(ctypes.c_char_p,),
            )

        ns_display_name = nsstring(display_name)
        process_info = send_id(objc_class(b"NSProcessInfo"), b"processInfo")
        if process_info:
            send_void(
                process_info,
                b"setProcessName:",
                ns_display_name,
                argtypes=(ctypes.c_void_p,),
            )

        main_bundle = send_id(objc_class(b"NSBundle"), b"mainBundle")
        info_dictionary = (
            send_id(main_bundle, b"infoDictionary") if main_bundle else 0
        )
        set_object_selector = selector(b"setObject:forKey:")
        if info_dictionary and send_bool(
            info_dictionary,
            b"respondsToSelector:",
            set_object_selector,
            argtypes=(ctypes.c_void_p,),
        ):
            for key in (
                "CFBundleName",
                "CFBundleDisplayName",
                "CFBundleExecutable",
            ):
                send_void(
                    info_dictionary,
                    b"setObject:forKey:",
                    ns_display_name,
                    nsstring(key),
                    argtypes=(ctypes.c_void_p, ctypes.c_void_p),
                )
    except (AttributeError, ctypes.ArgumentError, OSError, TypeError, ValueError):
        pass


def directory_images(path: Path) -> list[Path]:
    return sorted(
        (
            candidate
            for candidate in path.iterdir()
            if candidate.is_file() and has_supported_extension(candidate)
        ),
        key=lambda candidate: candidate.name.casefold(),
    )


def next_zoom(current: float, direction: int) -> float:
    if direction > 0:
        for value in ZOOM_STEPS:
            if value > current * 1.001:
                return value
        return ZOOM_STEPS[-1]

    for value in reversed(ZOOM_STEPS):
        if value < current / 1.001:
            return value
    return ZOOM_STEPS[0]


def load_image(path: Path) -> LoadedImage:
    path = normalized_path(path)
    with Image.open(path) as image:
        image.load()
        source_format = image.format or path.suffix.lstrip(".").upper()
        source_mode = image.mode
        loaded = image.convert("RGBA")
    return LoadedImage(
        path=path,
        image=loaded,
        source_format=source_format,
        source_mode=source_mode,
        has_transparency=has_transparency(loaded),
    )


def has_transparency(image: Image.Image) -> bool:
    if image.mode != "RGBA":
        return False
    alpha = image.getchannel("A")
    return alpha.getextrema()[0] < 255


def checkerboard(size: tuple[int, int], tile: int = 12) -> Image.Image:
    width, height = size
    light = (232, 232, 232, 255)
    dark = (184, 184, 184, 255)
    pattern = Image.new("RGBA", (tile * 2, tile * 2), light)
    dark_tile = Image.new("RGBA", (tile, tile), dark)
    pattern.paste(dark_tile, (tile, 0))
    pattern.paste(dark_tile, (0, tile))

    image = Image.new("RGBA", size, light)
    for y in range(0, height, pattern.height):
        for x in range(0, width, pattern.width):
            image.paste(pattern, (x, y))
    return image


def display_image(image: Image.Image, checkerboard_enabled: bool) -> Image.Image:
    rgba = image.convert("RGBA")
    if checkerboard_enabled and has_transparency(rgba):
        background = checkerboard(rgba.size)
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return rgba


def thumbnail_image(path: Path, checkerboard_enabled: bool) -> Image.Image:
    background = Image.new("RGBA", (THUMBNAIL_SIZE, THUMBNAIL_SIZE), "#171b22")
    try:
        with Image.open(path) as image:
            image.load()
            thumbnail = image.convert("RGBA")
            thumbnail.thumbnail(
                (THUMBNAIL_SIZE, THUMBNAIL_SIZE),
                Image.Resampling.LANCZOS,
            )
    except IMAGE_OPEN_ERRORS:
        return Image.new("RGB", (THUMBNAIL_SIZE, THUMBNAIL_SIZE), "#4a2525")

    if checkerboard_enabled and has_transparency(thumbnail):
        background = checkerboard((THUMBNAIL_SIZE, THUMBNAIL_SIZE), tile=10)

    x = (THUMBNAIL_SIZE - thumbnail.width) // 2
    y = (THUMBNAIL_SIZE - thumbnail.height) // 2
    background.alpha_composite(thumbnail, (x, y))
    return background.convert("RGB")


def pil_to_qimage(image: Image.Image) -> QImage:
    if image.mode == "RGB":
        rgb = image.convert("RGB")
        data = rgb.tobytes("raw", "RGB")
        qimage = QImage(
            data,
            rgb.width,
            rgb.height,
            rgb.width * 3,
            QImage.Format.Format_RGB888,
        )
        return qimage.copy()

    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return qimage.copy()


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(image))


class ImageLoadSignals(QObject):
    loaded = Signal(object, object)
    failed = Signal(object, object)


class ImageLoadWorker(QRunnable):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.signals = ImageLoadSignals()

    def run(self) -> None:
        try:
            loaded = load_image(self.path)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.path, exc)
            return
        self.signals.loaded.emit(loaded.path, loaded)


class ThumbnailSignals(QObject):
    loaded = Signal(int, object, object)
    failed = Signal(int, object, object)


class ThumbnailWorker(QRunnable):
    def __init__(
        self,
        generation: int,
        path: Path,
        checkerboard_enabled: bool,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.path = path
        self.checkerboard_enabled = checkerboard_enabled
        self.signals = ThumbnailSignals()

    def run(self) -> None:
        try:
            image = thumbnail_image(self.path, self.checkerboard_enabled)
            qimage = pil_to_qimage(image)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.generation, self.path, exc)
            return
        self.signals.loaded.emit(self.generation, self.path, qimage)


class ImageView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item: QGraphicsPixmapItem | None = None
        self.pixmap = QPixmap()
        self.fit_to_window = True
        self.zoom = 1.0

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(QColor("#0c0f14"))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def set_presentation_mode(self, enabled: bool) -> None:
        if enabled:
            self.setBackgroundBrush(QColor("#000000"))
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.fit_to_window = True
            self.fit_image()
            return

        self.setBackgroundBrush(QColor("#0c0f14"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.scene.clear()
        self.pixmap = pixmap
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.resetTransform()
        self.zoom = 1.0
        if self.fit_to_window:
            self.fit_image()
        else:
            self.actual_size()

    def clear_image(self) -> None:
        self.scene.clear()
        self.pixmap = QPixmap()
        self.pixmap_item = None
        self.zoom = 1.0

    def fit_image(self) -> None:
        if self.pixmap.isNull() or self.pixmap_item is None:
            return
        self.fit_to_window = True
        self.resetTransform()
        self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom = max(0.01, self.transform().m11())

    def actual_size(self) -> None:
        if self.pixmap.isNull():
            return
        self.fit_to_window = False
        self.resetTransform()
        self.zoom = 1.0

    def set_zoom(self, zoom: float) -> None:
        if self.pixmap.isNull():
            return
        self.fit_to_window = False
        self.resetTransform()
        self.scale(zoom, zoom)
        self.zoom = zoom

    def zoom_by(self, direction: int) -> None:
        self.set_zoom(next_zoom(self.zoom, direction))

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        if self.fit_to_window:
            self.fit_image()

    def wheelEvent(self, event) -> None:  # noqa: ANN001
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            direction = 1 if event.angleDelta().y() > 0 else -1
            self.zoom_by(direction)
            event.accept()
            return
        super().wheelEvent(event)


class ThumbnailGrid(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.path_items: dict[str, QListWidgetItem] = {}
        self.placeholder_icon = self._solid_icon("#171d26")
        self.error_icon = self._solid_icon("#4a2525")

        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.setGridSize(QSize(THUMBNAIL_ITEM_WIDTH, THUMBNAIL_ITEM_HEIGHT))
        self.setSpacing(14)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrap(True)

    def _solid_icon(self, color: str) -> QIcon:
        pixmap = QPixmap(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        pixmap.fill(QColor(color))
        return QIcon(pixmap)

    def set_images(
        self,
        paths: list[Path],
        current_path: Path | None,
    ) -> None:
        self.clear()
        self.path_items.clear()
        for path in paths:
            path_key = str(path)
            item = QListWidgetItem(self.placeholder_icon, path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            item.setSizeHint(QSize(THUMBNAIL_ITEM_WIDTH, THUMBNAIL_ITEM_HEIGHT))
            self.addItem(item)
            self.path_items[path_key] = item
            if current_path == path:
                item.setSelected(True)
                self.setCurrentItem(item)

    def set_thumbnail(self, path: Path, qimage: QImage) -> None:
        item = self.path_items.get(str(path))
        if item is None:
            return
        item.setIcon(QIcon(QPixmap.fromImage(qimage)))

    def set_thumbnail_error(self, path: Path) -> None:
        item = self.path_items.get(str(path))
        if item is None:
            return
        item.setIcon(self.error_icon)

    def visible_paths(self) -> list[Path]:
        viewport_rect = self.viewport().rect()
        paths: list[Path] = []
        for index in range(self.count()):
            item = self.item(index)
            if not self.visualItemRect(item).intersects(viewport_rect):
                continue
            value = item.data(Qt.ItemDataRole.UserRole)
            if value:
                paths.append(Path(value))
        return paths

    def first_paths(self, limit: int) -> list[Path]:
        paths: list[Path] = []
        for index in range(min(limit, self.count())):
            value = self.item(index).data(Qt.ItemDataRole.UserRole)
            if value:
                paths.append(Path(value))
        return paths


class PxlViewer(QMainWindow):
    def __init__(
        self,
        initial_target: Path | None = None,
        initial_mode: str = "image",
        slideshow_interval: float = DEFAULT_SLIDESHOW_INTERVAL,
    ) -> None:
        super().__init__()
        self.mode = "image"
        self.initial_mode = initial_mode
        self.current_path: Path | None = None
        self.image_folder: Path | None = None
        self.image_paths: list[Path] = []
        self.loaded: LoadedImage | None = None
        self.loaded_cache: OrderedDict[Path, LoadedImage] = OrderedDict()
        self.prefetching_paths: set[Path] = set()
        self.thumbnail_generation = 0
        self.thumbnail_queue: deque[Path] = deque()
        self.checkerboard_enabled = True
        self.slideshow_paused = False
        self.presentation_chrome_enabled = False
        self.presentation_cursor_hidden = False
        self.fullscreen_return_mode: str | None = None

        self.prefetch_pool = QThreadPool()
        self.prefetch_pool.setMaxThreadCount(2)
        self.thumbnail_pool = QThreadPool()
        self.thumbnail_pool.setMaxThreadCount(
            max(2, min(4, QThreadPool.globalInstance().maxThreadCount()))
        )

        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.setInterval(max(500, int(slideshow_interval * 1000)))
        self.slideshow_timer.timeout.connect(self.advance_slideshow)

        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setInterval(0)
        self.thumbnail_timer.timeout.connect(self.enqueue_thumbnail_batch)

        self.setWindowTitle(APP_NAME)
        self.resize(1120, 780)
        self.setMinimumSize(720, 480)
        self._build_ui()
        self._bind_actions()
        self._build_menu_bar()

        if initial_target:
            QTimer.singleShot(0, lambda: self.open_startup_target(initial_target))
        else:
            QTimer.singleShot(0, self.open_file_dialog)

    def _build_ui(self) -> None:
        self.toolbar = QToolBar("Main", self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.open_action = self._add_action(
            "Open",
            self.open_file_dialog,
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
        )
        self.dir_action = self._add_action(
            "Dir",
            self.open_directory_dialog,
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        self.toolbar.addSeparator()
        self.prev_action = self._add_action(
            "Prev",
            lambda: self.open_neighbor(-1),
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
        )
        self.next_action = self._add_action(
            "Next",
            lambda: self.open_neighbor(1),
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
        )
        self.toolbar.addSeparator()
        self.thumbs_action = self._add_action(
            "Thumbs",
            self.show_thumbnails,
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        self.slide_action = self._add_action(
            "Slide",
            self.start_slideshow,
            self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        self.toolbar.addSeparator()
        self.zoom_out_action = self._add_action(
            "Zoom Out",
            lambda: self.zoom_image(-1),
            self._zoom_icon("-"),
        )
        self.zoom_label = QLabel("Fit")
        self.zoom_label.setObjectName("ZoomLabel")
        self.toolbar.addWidget(self.zoom_label)
        self.zoom_in_action = self._add_action(
            "Zoom In",
            lambda: self.zoom_image(1),
            self._zoom_icon("+"),
        )
        self.actual_action = self._add_action("1:1", self.actual_size)
        self.fit_action = self._add_action("Fit", self.fit_image)

        self.title_label = QLabel("Open an image or directory")
        self.title_label.setObjectName("TitleLabel")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("DetailLabel")
        self.detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        header = QWidget()
        header.setObjectName("Header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 14)
        header_layout.setSpacing(4)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.detail_label)

        self.image_view = ImageView()
        self.thumbnail_grid = ThumbnailGrid()
        self.thumbnail_grid.itemClicked.connect(self.open_thumbnail_item)
        self.thumbnail_grid.itemActivated.connect(self.open_thumbnail_item)
        self.thumbnail_grid.verticalScrollBar().valueChanged.connect(
            self.prioritize_visible_thumbnails
        )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.image_view)
        self.stack.addWidget(self.thumbnail_grid)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.header = header

        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    def _bind_actions(self) -> None:
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.dir_action.setShortcut(QKeySequence("Ctrl+D"))
        self.prev_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        self.next_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        self.thumbs_action.setShortcut(QKeySequence("T"))
        self.slide_action.setShortcut(QKeySequence(Qt.Key.Key_F11))
        self.zoom_in_action.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
        self.zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self.actual_action.setShortcut(QKeySequence("Ctrl+1"))
        self.fit_action.setShortcut(QKeySequence("Ctrl+0"))

        QShortcut(QKeySequence("V"), self, activated=self.show_image_view)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.handle_escape)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self.toggle_slideshow_pause)

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(True)

        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.dir_action)
        file_menu.addSeparator()

        self.reload_action = QAction("&Reload", self)
        self.reload_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        self.reload_action.triggered.connect(self.reload_image)
        file_menu.addAction(self.reload_action)

        file_menu.addSeparator()
        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.quit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(self.quit_action)

        view_menu = menu_bar.addMenu("&View")
        view_menu.addAction(self.prev_action)
        view_menu.addAction(self.next_action)
        view_menu.addSeparator()
        view_menu.addAction(self.thumbs_action)
        view_menu.addAction(self.slide_action)
        view_menu.addSeparator()
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.actual_action)
        view_menu.addAction(self.fit_action)

        help_menu = menu_bar.addMenu("&Help")
        self.about_action = QAction(f"&About {APP_NAME}", self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(self.about_action)

    def _add_action(
        self,
        text: str,
        callback,
        icon: QIcon | None = None,
    ) -> QAction:
        action = QAction(icon or QIcon(), text, self)
        action.setToolTip(text)
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        return action

    def _zoom_icon(self, symbol: str) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(
                QColor("#f4f7fb"),
                6,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawEllipse(QRectF(12, 10, 31, 31))
        painter.drawLine(38, 38, 53, 53)

        painter.setPen(
            QPen(
                QColor("#66a8e8"),
                5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawLine(21, 26, 34, 26)
        if symbol == "+":
            painter.drawLine(28, 19, 28, 32)
        painter.end()
        return QIcon(pixmap)

    def cached_directory_images(self, folder: Path, force: bool = False) -> list[Path]:
        folder = normalized_path(folder)
        if force or self.image_folder != folder:
            self.image_paths = directory_images(folder)
            self.image_folder = folder
        return self.image_paths

    def update_image_list_for_path(self, path: Path, force: bool = False) -> None:
        folder = path.parent
        if not folder.exists():
            self.image_folder = folder
            self.image_paths = [path]
            return

        try:
            images = self.cached_directory_images(folder, force=force)
        except OSError:
            self.image_folder = folder
            self.image_paths = [path]
            return

        if path not in images:
            self.image_paths = [*images, path]

    def cached_loaded_image(self, path: Path, force: bool = False) -> LoadedImage:
        path = normalized_path(path)
        if not force and path in self.loaded_cache:
            loaded = self.loaded_cache.pop(path)
            self.loaded_cache[path] = loaded
            return loaded

        loaded = load_image(path)
        self.cache_loaded_image(loaded)
        return loaded

    def cache_loaded_image(self, loaded: LoadedImage) -> None:
        path = loaded.path
        if path in self.loaded_cache:
            self.loaded_cache.pop(path)
        self.loaded_cache[path] = loaded
        while len(self.loaded_cache) > LOAD_CACHE_SIZE:
            self.loaded_cache.popitem(last=False)

    def prefetch_neighbors(self) -> None:
        if not self.current_path or len(self.image_paths) < 2:
            return
        try:
            current_index = self.image_paths.index(self.current_path)
        except ValueError:
            return

        candidate_indexes = {
            (current_index - 1) % len(self.image_paths),
            (current_index + 1) % len(self.image_paths),
        }
        for index in candidate_indexes:
            path = self.image_paths[index]
            if path == self.current_path:
                continue
            if path in self.loaded_cache or path in self.prefetching_paths:
                continue
            self.prefetching_paths.add(path)
            worker = ImageLoadWorker(path)
            worker.signals.loaded.connect(self.handle_prefetched_image)
            worker.signals.failed.connect(self.handle_prefetch_failed)
            self.prefetch_pool.start(worker)

    def handle_prefetched_image(self, path: Path, loaded: LoadedImage) -> None:
        self.prefetching_paths.discard(path)
        self.cache_loaded_image(loaded)

    def handle_prefetch_failed(self, path: Path, _exc: Exception) -> None:
        self.prefetching_paths.discard(path)

    def ordered_thumbnail_paths(self) -> list[Path]:
        visible_paths = self.thumbnail_grid.visible_paths()
        if not visible_paths:
            visible_paths = self.thumbnail_grid.first_paths(
                THUMBNAIL_PRIORITY_FALLBACK_COUNT
            )
        visible_set = set(visible_paths)
        return [
            *visible_paths,
            *(path for path in self.image_paths if path not in visible_set),
        ]

    def start_thumbnail_generation(self, generation: int) -> None:
        if generation != self.thumbnail_generation:
            return
        self.thumbnail_pool.clear()
        self.thumbnail_queue = deque(self.ordered_thumbnail_paths())
        self.enqueue_thumbnail_batch()
        if self.thumbnail_queue:
            self.thumbnail_timer.start()

    def enqueue_thumbnail_batch(self) -> None:
        if not self.thumbnail_queue:
            self.thumbnail_timer.stop()
            return

        generation = self.thumbnail_generation
        for _ in range(min(THUMBNAIL_BATCH_SIZE, len(self.thumbnail_queue))):
            path = self.thumbnail_queue.popleft()
            worker = ThumbnailWorker(generation, path, self.checkerboard_enabled)
            worker.signals.loaded.connect(self.handle_thumbnail_loaded)
            worker.signals.failed.connect(self.handle_thumbnail_failed)
            self.thumbnail_pool.start(worker)

        if not self.thumbnail_queue:
            self.thumbnail_timer.stop()

    def prioritize_visible_thumbnails(self) -> None:
        if not self.thumbnail_queue:
            return
        visible_paths = self.thumbnail_grid.visible_paths()
        if not visible_paths:
            return

        queued = set(self.thumbnail_queue)
        priority_paths = [path for path in visible_paths if path in queued]
        if not priority_paths:
            return

        priority_set = set(priority_paths)
        remaining_paths = [
            path for path in self.thumbnail_queue if path not in priority_set
        ]
        self.thumbnail_queue = deque([*priority_paths, *remaining_paths])

    def handle_thumbnail_loaded(
        self,
        generation: int,
        path: Path,
        qimage: QImage,
    ) -> None:
        if generation != self.thumbnail_generation:
            return
        self.thumbnail_grid.set_thumbnail(path, qimage)

    def handle_thumbnail_failed(
        self,
        generation: int,
        path: Path,
        _exc: Exception,
    ) -> None:
        if generation != self.thumbnail_generation:
            return
        self.thumbnail_grid.set_thumbnail_error(path)

    def open_file_dialog(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Open image",
            str(Path.cwd()),
            image_dialog_filter(),
        )
        if selected:
            self.open_target(Path(selected))

    def open_directory_dialog(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Open image directory",
            str(Path.cwd()),
        )
        if selected:
            self.open_target(Path(selected))

    def open_startup_target(self, path: Path) -> None:
        self.open_target(path)
        if self.loaded is None:
            return
        if self.initial_mode == "thumbnails":
            self.show_thumbnails()
        elif self.initial_mode == "slideshow":
            self.start_slideshow()

    def open_target(self, path: Path) -> None:
        path = normalized_path(path)
        if path.is_dir():
            self.open_directory(path)
            return
        self.open_path(path, refresh_folder=True)

    def open_directory(self, path: Path) -> None:
        try:
            images = self.cached_directory_images(path, force=True)
        except OSError as exc:
            self.report_error("Open failed", f"Could not read directory:\n{path}\n\n{exc}")
            return

        if not images:
            self.report_error(
                "No images",
                f"No supported image files found in:\n{path}",
            )
            return

        for image_path in images:
            if self.open_path(image_path, show_errors=False):
                return

        self.report_error(
            "No images",
            f"No readable image files found in:\n{path}",
        )

    def open_path(
        self,
        path: Path,
        *,
        refresh_folder: bool = False,
        force_load: bool = False,
        show_errors: bool = True,
    ) -> bool:
        path = normalized_path(path)
        try:
            loaded = self.cached_loaded_image(path, force=force_load)
        except FileNotFoundError:
            if show_errors:
                self.report_error("File not found", f"Could not find:\n{path}")
            return False
        except UnidentifiedImageError:
            if show_errors:
                self.report_error(
                    "Unsupported image",
                    f"Could not open as an image:\n{path}",
                )
            return False
        except IMAGE_OPEN_ERRORS as exc:
            if show_errors:
                self.report_error("Open failed", f"Could not open:\n{path}\n\n{exc}")
            return False

        self.loaded = loaded
        self.current_path = loaded.path
        self.update_image_list_for_path(loaded.path, force=refresh_folder)
        self.setWindowTitle(f"{path.name} - {APP_NAME}")
        if self.mode == "thumbnails":
            self.populate_thumbnails()
            self.update_header()
            self.prefetch_neighbors()
            return True
        self.show_pixmap_for_current()
        self.prefetch_neighbors()
        return True

    def show_pixmap_for_current(self) -> None:
        if self.loaded is None:
            return
        pixmap = pil_to_pixmap(
            display_image(self.loaded.image, self.checkerboard_enabled)
        )
        self.stack.setCurrentWidget(self.image_view)
        self.image_view.set_pixmap(pixmap)
        if self.mode != "slideshow":
            self.mode = "image"
        self.update_header()

    def show_image_view(self) -> None:
        self.stop_slideshow()
        if self.loaded is None:
            return
        self.mode = "image"
        self.header.show()
        self.toolbar.show()
        self.status.show()
        self.showNormal()
        self.show_pixmap_for_current()

    def show_thumbnails(self) -> None:
        self.stop_slideshow()
        if not self.ensure_image_list():
            self.report_error("No images", "Open an image or a directory first.")
            return
        self.mode = "thumbnails"
        self.header.show()
        self.toolbar.show()
        self.status.show()
        self.showNormal()
        self.populate_thumbnails()
        self.stack.setCurrentWidget(self.thumbnail_grid)
        self.update_header()

    def start_slideshow(self) -> None:
        if not self.ensure_image_list():
            self.report_error("No images", "Open an image or a directory first.")
            return
        if self.loaded is None and self.image_paths:
            self.open_path(self.image_paths[0])
        if self.loaded is None:
            return

        self.mode = "slideshow"
        self.slideshow_paused = False
        self.stack.setCurrentWidget(self.image_view)
        self.image_view.fit_to_window = True
        self.showFullScreen()
        self.set_presentation_chrome(True)
        self.show_pixmap_for_current()
        QTimer.singleShot(0, lambda: self.set_presentation_chrome(True))
        self.slideshow_timer.start()

    def stop_slideshow(self) -> None:
        self.slideshow_timer.stop()
        self.slideshow_paused = False
        self.set_presentation_chrome(False)
        if self.isFullScreen():
            self.showNormal()

    def set_presentation_chrome(self, enabled: bool) -> None:
        self.presentation_chrome_enabled = enabled
        if enabled:
            self.menuBar().setVisible(False)
            self.toolbar.setVisible(False)
            self.header.setVisible(False)
            self.status.setVisible(False)
            self.image_view.set_presentation_mode(True)
            if not self.presentation_cursor_hidden:
                QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
                self.presentation_cursor_hidden = True
            return

        self.menuBar().setVisible(True)
        self.toolbar.setVisible(True)
        self.header.setVisible(True)
        self.status.setVisible(True)
        self.image_view.set_presentation_mode(False)
        if self.presentation_cursor_hidden:
            QApplication.restoreOverrideCursor()
            self.presentation_cursor_hidden = False

    def sync_fullscreen_chrome(self) -> None:
        if self.isFullScreen():
            if self.mode != "slideshow" and self.fullscreen_return_mode is None:
                self.fullscreen_return_mode = self.mode
            if self.loaded is not None:
                self.stack.setCurrentWidget(self.image_view)
                self.image_view.fit_to_window = True
                if self.image_view.pixmap.isNull():
                    self.show_pixmap_for_current()
                else:
                    self.image_view.fit_image()
            self.set_presentation_chrome(True)
            return

        if self.presentation_chrome_enabled:
            self.set_presentation_chrome(False)
        if self.fullscreen_return_mode == "thumbnails":
            self.mode = "thumbnails"
            self.populate_thumbnails()
            self.stack.setCurrentWidget(self.thumbnail_grid)
            self.update_header()
        elif self.fullscreen_return_mode == "image":
            self.mode = "image"
            if self.loaded is not None:
                self.show_pixmap_for_current()
        self.fullscreen_return_mode = None

    def changeEvent(self, event) -> None:  # noqa: ANN001
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self.sync_fullscreen_chrome)

    def advance_slideshow(self) -> None:
        if self.mode != "slideshow" or self.slideshow_paused:
            return
        self.open_neighbor(1, restart_slideshow=False)

    def toggle_slideshow_pause(self) -> None:
        if self.mode != "slideshow":
            return
        self.slideshow_paused = not self.slideshow_paused
        if self.slideshow_paused:
            self.slideshow_timer.stop()
            self.status.showMessage("Slideshow paused")
        else:
            self.slideshow_timer.start()

    def open_neighbor(self, direction: int, restart_slideshow: bool = True) -> None:
        if not self.current_path or not self.image_paths:
            return
        try:
            current_index = self.image_paths.index(self.current_path)
        except ValueError:
            current_index = 0
        if self.mode == "slideshow" and restart_slideshow:
            self.slideshow_timer.stop()

        candidate_paths = [
            self.image_paths[(current_index + (direction * offset)) % len(self.image_paths)]
            for offset in range(1, len(self.image_paths) + 1)
        ]
        opened = False
        for next_path in candidate_paths:
            if next_path not in self.image_paths:
                continue
            if self.open_path(next_path, show_errors=False):
                opened = True
                break
            self.loaded_cache.pop(next_path, None)
            self.image_paths.remove(next_path)
            if self.image_folder == next_path.parent and not self.image_paths:
                self.image_folder = None

        if not opened:
            self.report_error("No images", "No readable image files remain.")
            return

        if self.mode == "slideshow" and restart_slideshow and not self.slideshow_paused:
            self.slideshow_timer.start()

    def open_thumbnail_item(self, item: QListWidgetItem) -> None:
        value = item.data(Qt.ItemDataRole.UserRole)
        if not value:
            return
        self.mode = "image"
        self.open_path(Path(value))
        self.stack.setCurrentWidget(self.image_view)

    def populate_thumbnails(self) -> None:
        if not self.image_paths:
            return
        self.thumbnail_generation += 1
        generation = self.thumbnail_generation
        self.thumbnail_timer.stop()
        self.thumbnail_queue.clear()
        self.thumbnail_grid.set_images(
            self.image_paths,
            self.current_path,
        )
        self.stack.setCurrentWidget(self.thumbnail_grid)
        QTimer.singleShot(0, lambda: self.start_thumbnail_generation(generation))

    def ensure_image_list(self) -> bool:
        if self.image_paths:
            return True
        if self.current_path is not None:
            self.update_image_list_for_path(self.current_path)
        return bool(self.image_paths)

    def reload_image(self) -> None:
        if self.current_path is None:
            return
        current_mode = self.mode
        self.loaded_cache.pop(self.current_path, None)
        self.open_path(
            self.current_path,
            refresh_folder=True,
            force_load=True,
        )
        if current_mode == "thumbnails":
            self.show_thumbnails()
        elif current_mode == "slideshow":
            self.mode = "slideshow"
            self.start_slideshow()

    def zoom_image(self, direction: int) -> None:
        if self.loaded is None or self.mode == "slideshow":
            return
        if self.mode == "thumbnails":
            self.show_image_view()
        self.image_view.zoom_by(direction)
        self.update_header()

    def actual_size(self) -> None:
        if self.loaded is None or self.mode == "slideshow":
            return
        if self.mode == "thumbnails":
            self.show_image_view()
        self.image_view.actual_size()
        self.update_header()

    def fit_image(self) -> None:
        if self.loaded is None or self.mode == "slideshow":
            return
        if self.mode == "thumbnails":
            self.show_image_view()
        self.image_view.fit_image()
        self.update_header()

    def current_index_text(self) -> str:
        if not self.current_path or not self.image_paths:
            return ""
        try:
            index = self.image_paths.index(self.current_path) + 1
        except ValueError:
            return ""
        return f"{index}/{len(self.image_paths)}"

    def update_header(self) -> None:
        if self.loaded is None:
            self.title_label.setText("Open an image or directory")
            self.detail_label.setText("")
            self.status.showMessage("Ready")
            return

        image = self.loaded.image
        index_text = self.current_index_text()
        zoom_text = "Fit" if self.image_view.fit_to_window else f"{self.image_view.zoom * 100:.0f}%"
        mode_text = {
            "image": "Image",
            "thumbnails": "Thumbnails",
            "slideshow": "Slideshow",
        }[self.mode]
        details = (
            f"{image.width}x{image.height} px  |  "
            f"{self.loaded.source_format} {self.loaded.source_mode}  |  "
            f"{zoom_text}"
        )
        if index_text:
            details = f"{details}  |  {index_text}"

        self.title_label.setText(self.loaded.path.name)
        self.detail_label.setText(details)
        self.zoom_label.setText(zoom_text if self.mode != "thumbnails" else "Grid")
        self.status.showMessage(f"{mode_text}  |  {self.loaded.path}")

    def handle_escape(self) -> None:
        if self.mode == "slideshow" or self.isFullScreen():
            self.show_image_view()
            return
        if self.mode == "thumbnails":
            self.show_image_view()
            return
        self.close()

    def report_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)
        self.status.showMessage(message.replace("\n", " "))

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            (
                f"<h2>{APP_NAME}</h2>"
                f"<p>Version {APP_VERSION}</p>"
                "<p>A modern, cross-platform image viewer built with "
                "PySide6, Pillow, uv, and PEP 723 inline script metadata.</p>"
                "<p>Open a file or directory, browse thumbnails, zoom images, "
                "and run a full-screen slideshow.</p>"
                "<p>Supported formats are detected by Pillow at runtime.</p>"
            ),
        )


def apply_modern_style(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    app.setStyleSheet(
        """
        QMainWindow, QWidget {
            background: #0f131a;
            color: #edf2f7;
            font-size: 13px;
        }
        QToolBar {
            background: #151a22;
            border: 0;
            border-bottom: 1px solid #252c37;
            padding: 8px 10px;
            spacing: 6px;
        }
        QToolBar::separator {
            background: #2b3340;
            width: 1px;
            margin: 7px 8px;
        }
        QToolButton {
            background: #202734;
            border: 1px solid #303948;
            border-radius: 7px;
            color: #f4f7fb;
            padding: 7px 10px;
            min-width: 46px;
        }
        QToolButton:hover {
            background: #2a3342;
            border-color: #4b5a70;
        }
        QToolButton:pressed, QToolButton:checked {
            background: #315f8f;
            border-color: #66a8e8;
        }
        QLabel#TitleLabel {
            color: #ffffff;
            font-size: 20px;
            font-weight: 650;
            letter-spacing: 0;
        }
        QLabel#DetailLabel {
            color: #9faec1;
            font-size: 12px;
        }
        QLabel#ZoomLabel {
            background: #10151d;
            border: 1px solid #303948;
            border-radius: 7px;
            color: #cbd6e4;
            min-width: 58px;
            padding: 7px 10px;
        }
        QWidget#Header {
            background: #111720;
            border-bottom: 1px solid #252c37;
        }
        QGraphicsView {
            background: #0b0e13;
            border: 0;
        }
        QListWidget {
            background: #0b0e13;
            border: 0;
            color: #e8eef6;
            padding: 18px;
            outline: 0;
        }
        QListWidget::item {
            background: #171d26;
            border: 1px solid #273140;
            border-radius: 8px;
            margin: 4px;
            padding: 10px;
        }
        QListWidget::item:hover {
            background: #202938;
            border-color: #46566f;
        }
        QListWidget::item:selected {
            background: #244261;
            border-color: #78b7f5;
        }
        QStatusBar {
            background: #151a22;
            border-top: 1px solid #252c37;
            color: #9faec1;
        }
        QScrollBar:vertical, QScrollBar:horizontal {
            background: #0f131a;
            border: 0;
            margin: 0;
        }
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
            background: #313b4c;
            border-radius: 5px;
            min-height: 28px;
            min-width: 28px;
        }
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
            background: #48566d;
        }
        QScrollBar::add-line, QScrollBar::sub-line {
            width: 0;
            height: 0;
        }
        """
    )


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    configure_windows_app_identity()
    configure_macos_app_identity()
    display_name = (
        os.environ.get("PXL_MACOS_APP_NAME", APP_DISPLAY_NAME)
        if sys.platform == "darwin"
        else APP_NAME
    )

    # Set this before QApplication is constructed so Qt can use it while
    # creating platform-native menus.
    QCoreApplication.setApplicationName(display_name)
    QCoreApplication.setApplicationVersion(APP_VERSION)
    QCoreApplication.setOrganizationName(APP_NAME)

    app = QApplication([display_name])
    app.setApplicationDisplayName(display_name)
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    apply_modern_style(app)
    viewer = PxlViewer(
        args.target,
        initial_mode=args.mode,
        slideshow_interval=args.interval,
    )
    if not icon.isNull():
        viewer.setWindowIcon(icon)
    viewer.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
