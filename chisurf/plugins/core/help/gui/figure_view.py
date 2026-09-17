"""A figure, opened big.

A plot in a documentation page is laid out to the text column, and the column
is a *reading* width — narrower than the window, and narrower still than the
figure deserves when it carries four panels of axes. Every reader eventually
wants the picture full size, and until now there was nowhere to go: the page
had one rendering of it and that was the only one.

So a figure is clickable, and a click opens it here — scaled to the screen,
zoomable, and dismissed with a click or ``Esc``. The dialog resolves the image
itself from the same name Qt's rich text stored, so it shows the file's real
pixels rather than an enlargement of the thumbnail the page was showing.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy.QtCore import Qt
from qtpy.QtGui import QImage, QKeySequence, QPixmap
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

#: Fraction of the screen a figure is allowed to fill when it opens.
SCREEN_FRACTION = 0.85


def load_image(name: str, base_dir: pathlib.Path | None = None) -> QImage | None:
    """Return the image a rich-text image name refers to.

    Parameters
    ----------
    name : str
        The name Qt stored on the image format — a file path, a ``file:`` URL
        or a ``data:`` URI.
    base_dir : pathlib.Path, optional
        Directory a relative path resolves against.

    Returns
    -------
    QImage or None
        ``None`` when the image cannot be read.
    """
    text = str(name or "")
    if not text:
        return None

    if text.startswith("data:"):
        import base64

        try:
            payload = text.split(",", 1)[1]
            raw = base64.b64decode(payload)
        except Exception:
            logger.debug("could not decode an inline image", exc_info=True)
            return None
        image = QImage()
        return image if image.loadFromData(raw) else None

    if text.startswith("file://"):
        from qtpy.QtCore import QUrl

        text = QUrl(text).toLocalFile()

    path = pathlib.Path(text)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    if not path.is_file():
        return None
    image = QImage(str(path))
    return None if image.isNull() else image


class FigureDialog(QDialog):
    """A modal window showing one figure at its own size.

    Parameters
    ----------
    image : QImage
        The figure.
    title : str
        Window title — the file name is enough to recognise it by.
    parent : QWidget, optional
        Parent window.
    """

    #: Zoom steps, as a multiple of the fit-to-window scale.
    ZOOM_STEP = 1.25

    def __init__(self, image: QImage, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title or "Figure")
        self._image = image
        self._scale = 1.0
        self._fitted = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        self.area = QScrollArea()
        self.area.setWidget(self.label)
        self.area.setWidgetResizable(False)
        self.area.setAlignment(Qt.AlignCenter)
        self.area.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(self.area, 1)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addStretch(1)
        for text, tip, slot in (
            ("−", "Zoom out (Ctrl+-)", lambda: self.zoom(1 / self.ZOOM_STEP)),
            ("⤢", "Fit to the window (Ctrl+0)", self.fit),
            ("1:1", "Actual pixels (Ctrl+1)", self.actual_size),
            ("+", "Zoom in (Ctrl++)", lambda: self.zoom(self.ZOOM_STEP)),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        self.size_label = QLabel(f"{image.width()} × {image.height()} px")
        self.size_label.setStyleSheet("color: #8a8a8a; font-size: 9pt;")
        row.addWidget(self.size_label)
        layout.addLayout(row)

        for sequence, slot in (
            (QKeySequence.ZoomIn, lambda: self.zoom(self.ZOOM_STEP)),
            (QKeySequence("Ctrl+="), lambda: self.zoom(self.ZOOM_STEP)),
            (QKeySequence.ZoomOut, lambda: self.zoom(1 / self.ZOOM_STEP)),
            (QKeySequence("Ctrl+0"), self.fit),
            (QKeySequence("Ctrl+1"), self.actual_size),
        ):
            QShortcut(sequence, self).activated.connect(slot)

        self.resize(*self._opening_size())
        self.fit()

    # ── sizing ────────────────────────────────────────────────────────

    def _opening_size(self) -> tuple[int, int]:
        """Return a window size that shows the figure without covering the screen."""
        width, height = self._image.width(), self._image.height()
        try:
            available = self.screen().availableGeometry()
            limit_w = int(available.width() * SCREEN_FRACTION)
            limit_h = int(available.height() * SCREEN_FRACTION)
        except Exception:
            limit_w, limit_h = 1200, 900
        scale = min(1.0, limit_w / max(1, width), limit_h / max(1, height))
        return max(320, round(width * scale)), max(240, round(height * scale) + 40)

    def _apply(self) -> None:
        """Draw the figure at the current scale."""
        width = max(1, round(self._image.width() * self._scale))
        height = max(1, round(self._image.height() * self._scale))
        pixmap = QPixmap.fromImage(
            self._image.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.label.setPixmap(pixmap)
        self.label.resize(pixmap.size())
        percent = round(self._scale * 100)
        self.size_label.setText(f"{self._image.width()} × {self._image.height()} px · {percent}%")

    def fit(self) -> None:
        """Scale the figure to the window.

        The window's own size is the fallback: before the dialog is shown, the
        scroll area's viewport has not been laid out and reports whatever it
        was constructed at, which fits the figure to the wrong box.
        """
        viewport = self.area.viewport().size()
        width, height = viewport.width(), viewport.height()
        if width < 40 or height < 40 or not self.area.isVisible():
            width = max(80, self.width() - 24)
            height = max(80, self.height() - 64)
        self._scale = min(
            1.0,
            max(0.05, width / max(1, self._image.width())),
            max(0.05, height / max(1, self._image.height())),
        )
        self._fitted = True
        self._apply()

    def actual_size(self) -> None:
        """Show one image pixel per screen pixel."""
        self._scale = 1.0
        self._fitted = False
        self._apply()

    def zoom(self, factor: float) -> None:
        """Multiply the current scale by *factor*."""
        self._scale = max(0.05, min(8.0, self._scale * factor))
        self._fitted = False
        self._apply()

    # ── events ────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        """Keep a fitted figure fitted while the window is resized."""
        super().resizeEvent(event)
        if self._fitted:
            self.fit()

    def mouseReleaseEvent(self, event):
        """Close on a click anywhere, which is what a lightbox does."""
        if event.button() == Qt.LeftButton:
            self.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Ctrl+wheel zooms; a plain wheel scrolls the view."""
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom(self.ZOOM_STEP if delta > 0 else 1 / self.ZOOM_STEP)
                event.accept()
                return
        super().wheelEvent(event)


def show_figure(name: str, base_dir: pathlib.Path | None = None, parent=None) -> bool:
    """Open *name* in a modal figure window.

    Parameters
    ----------
    name : str
        The rich-text image name.
    base_dir : pathlib.Path, optional
        Directory a relative path resolves against.
    parent : QWidget, optional
        Parent window.

    Returns
    -------
    bool
        Whether a window was opened.
    """
    image = load_image(name, base_dir)
    if image is None:
        return False
    title = pathlib.Path(str(name).split("?")[0]).name or "Figure"
    dialog = FigureDialog(image, title=title, parent=parent)
    dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec()
    return True
