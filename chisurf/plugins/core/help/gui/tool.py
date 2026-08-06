"""The ChiSurf help browser.

The documentation ChiSurf ships is large — theory pages, workflow guides, the
fitting manual, a reference section and one page per plugin — and a reader who
already knows which file they want is not the reader who needs help. So this
window is built around three things:

* **Structure.** The tree is the documentation's own table of contents, read
  from the ``toctree`` blocks the published manual is built from
  (:mod:`~chisurf.plugins.core.help.api.toc`), not a directory listing. Order
  and grouping are the author's.
* **A way in.** It opens on a start page that says what each part of the
  documentation is for and offers the pages a new user needs first, and its
  search ranks whole pages with a matching excerpt rather than hiding rows of a
  tree.
* **Pages that read like pages.** Formulas are typeset, admonitions are boxes,
  cross-references are links, and the colours are the running theme's
  (:mod:`~chisurf.plugins.core.help.api.markdown`).

Authoring — editing a page, and the human-review sign-off that gates a release —
is a maintainer's job, not a reader's, and lives behind the *Authoring* toggle.
"""

from __future__ import annotations

import getpass
import html as _html
import logging
import pathlib
import re
import webbrowser
from typing import Optional

from qtpy.QtCore import QEvent, QStringListModel, Qt, QTimer, QUrl
from qtpy.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextCursor,
    QTextDocument,
)
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QShortcut,
    QSplitter,
    QTextBrowser,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import chisurf as cs
import chisurf.core.settings
from chisurf.core.info import help_url
from chisurf.gui import dialogs
from chisurf.gui.glyphs import Glyphs
from chisurf.plugins.core.help.api import markdown as md_api, review, toc as toc_api
from chisurf.plugins.core.help.gui.ask_panel import AskPanel
from chisurf.plugins.core.help.gui.client import HelpClient

logger = logging.getLogger(__name__)

#: Badge shown next to a page for each review status.
REVIEW_BADGES = {
    review.STATUS_REVIEWED: "✅",
    review.STATUS_AI_REVIEWED: "🤖",
    review.STATUS_STALE: "⚠️",
    review.STATUS_UNREVIEWED: "⬜",
}

#: Explanation shown as a tooltip / status line for each review status.
REVIEW_TOOLTIPS = {
    review.STATUS_REVIEWED: "Checked by a human and unchanged since.",
    review.STATUS_STALE: (
        "Was checked, but the page has been edited since — it needs "
        "re-checking and counts as unreviewed."
    ),
    review.STATUS_AI_REVIEWED: (
        "Read and corrected by an agent, but not yet confirmed against the "
        "running application by a human. Still blocks a release."
    ),
    review.STATUS_UNREVIEWED: (
        "Nobody and nothing has been through this page. Largely "
        "machine-drafted; blocks release."
    ),
}

#: Row colour per review status, shown only while authoring. A colour says the
#: same thing as a badge character without changing the row's font.
REVIEW_COLOURS = {
    review.STATUS_AI_REVIEWED: "#6cb6ff",
    review.STATUS_STALE: "#e0a458",
    review.STATUS_UNREVIEWED: "#e0736d",
}

#: Icon per top-level section, so the parts are told apart at a glance.
SECTION_ICONS = {
    "Getting started": "🚀",
    "Fundamentals — photophysics": "🔬",
    "Concepts — the theory": "📐",
    "Guides — how to in ChiSurf": "🧭",
    "Fitting interface & examples": "📘",
    "Reference": "📑",
    "Plugins": "🧩",
    "Literature": "📚",
    "About ChiSurf": "ℹ️",
    "Developing ChiSurf": "🛠",
}

#: Pages offered on the start page to somebody who has just opened ChiSurf.
START_HERE = (
    ("docs/getting_started/index.rst", "Install, launch, and find your way around"),
    ("docs/manual/data_import.rst", "Import data and create your first fit"),
    ("docs/manual/fit_interface.rst", "The fitting interface, parameter by parameter"),
    ("docs/guides/index.md", "Pick the workflow you want to run"),
)

#: Roles in the tree item's data, beyond the document path.
_ROLE_PATH = Qt.UserRole
_ROLE_REVIEW = Qt.UserRole + 1
_ROLE_KIND = Qt.UserRole + 2

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    def _noop_persist_plugin_state(name):
        def decorator(cls):
            return cls
        return decorator
    persist_plugin_state = _noop_persist_plugin_state


def _is_within(path: pathlib.Path, directory: pathlib.Path) -> bool:
    """Whether *path* lies inside *directory*."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
#: ``src="/guides/figures/x.png"`` -- root-relative to ``docs/``, not to the disk.
_ROOT_RELATIVE_SRC = re.compile(r'(src\s*=\s*["\'])/(?!/)([^"\']+)', re.IGNORECASE)


def _docs_root_prefix() -> str:
    """Absolute path of ``docs/`` with a trailing separator, for image sources."""
    from chisurf.plugins.core.help.api.toc import docs_root

    return f"{docs_root()}/"
_IMG_SRC = re.compile(r'src\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _constrain_image_widths(html: str, base_dir: pathlib.Path, max_width: int) -> str:
    """Make document images render sensibly in Qt's rich-text engine.

    Two adjustments are needed. Qt renders images at their native pixel size and
    ignores CSS ``max-width``, so a full-resolution manual screenshot would push
    the text off the page; an explicit ``width``/``height`` fixes that, read from
    the image header rather than by decoding the file. Separately, docutils emits
    block images as a bare ``<img class="align-center">`` between paragraphs —
    without the docutils stylesheet Qt lays that out erratically, floating the
    image away from its place in the text, so the image is wrapped in a centred
    paragraph and the unusable class dropped.

    Parameters
    ----------
    html : str
        Rendered document HTML.
    base_dir : pathlib.Path
        Directory that relative image sources resolve against.
    max_width : int
        Maximum rendered width in pixels.

    Returns
    -------
    str
        HTML with images sized and wrapped for Qt.

    """
    if max_width <= 0:
        return html

    def _fix(match: "re.Match[str]") -> str:
        tag = match.group(0)
        # A source beginning with "/" is root-relative *to the documentation*,
        # which is how Sphinx reads it; taken as a filesystem path it points at
        # the root of the disk and the image is simply missing.
        tag = _ROOT_RELATIVE_SRC.sub(
            lambda m: f'{m.group(1)}{_docs_root_prefix()}{m.group(2)}', tag
        )
        preceding = html[: match.start()].rstrip().lower()
        # A bare block image sits between paragraphs; an inline one does not.
        is_block = preceding.endswith(("</p>", "</div>", "<div>", "</h1>", "</h2>"))

        tag = re.sub(r'\s*class\s*=\s*["\'][^"\']*["\']', "", tag, flags=re.IGNORECASE)

        if not re.search(r"\bwidth\s*=", tag, re.IGNORECASE):
            src_match = _IMG_SRC.search(tag)
            if src_match:
                src = src_match.group(1)
                if not src.startswith(("http://", "https://", "data:")):
                    path = pathlib.Path(src)
                    if not path.is_absolute():
                        path = base_dir / path
                    try:
                        from qtpy.QtGui import QImageReader

                        size = QImageReader(str(path)).size()
                        width, height = size.width(), size.height()
                    except Exception:
                        width = height = 0
                    if width > 0 and height > 0 and width > max_width:
                        scaled = max(1, round(height * max_width / width))
                        tag = (
                            tag[:-1].rstrip("/")
                            + f' width="{max_width}" height="{scaled}">'
                        )

        return f'<p align="center">{tag}</p>' if is_block else tag

    return _IMG_TAG.sub(_fix, html)


#: Smallest gutter a page keeps, so text never touches the scrollbar.
MIN_GUTTER = 10

#: Qt's own margin around the document body, which sits inside the gutter.
_DOCUMENT_MARGIN = 4


def measure_margin(available: int, maximum: int, minimum: int = MIN_GUTTER) -> int:
    """Return the gutter that holds a text column of *maximum* inside *available*.

    A maximised help window is over a thousand pixels of text per line, which is
    roughly twice what is comfortable to read, so the column is centred inside
    the viewport. In a narrow window the viewport *is* the column and only the
    minimum gutter is kept.

    Parameters
    ----------
    available : int
        Viewport width in pixels.
    maximum : int
        Widest text column to allow, in pixels.
    minimum : int, optional
        Gutter to keep even when the viewport is narrower than *maximum*.

    Returns
    -------
    int
        Margin to leave on each side.

    """
    return max(minimum, (available - maximum) // 2)


#: Emoji rendered to pixmaps, keyed by (character, pixel size).
_EMOJI_ICONS: dict = {}


def emoji_icon(character: str, size: int = 16):
    """Return *character* drawn into an icon.

    An emoji is the clearest label a section row can carry, and it is also the
    one thing that must not appear in the row's *text*: Qt falls back to a
    colour font for the whole item and the fallback's metrics restyle the row.
    Painting it into a pixmap keeps the picture and leaves the type alone.

    Parameters
    ----------
    character : str
        One or two emoji.
    size : int, optional
        Icon edge length in logical pixels; use the row height.

    Returns
    -------
    QtGui.QIcon
        The rendered icon, cached; a null icon if it cannot be drawn.

    """
    key = (character, size)
    cached = _EMOJI_ICONS.get(key)
    if cached is not None:
        return cached
    icon = QIcon()
    try:
        ratio = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0
        ratio = max(1.0, float(ratio))
        pixmap = QPixmap(int(size * ratio), int(size * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            font = QFont(painter.font())
            font.setPixelSize(int(size * 0.86))
            painter.setFont(font)
            painter.drawText(
                pixmap.rect(), Qt.AlignCenter, character
            )
        finally:
            painter.end()
        icon = QIcon(pixmap)
    except Exception:
        logger.debug("could not draw the icon %r", character, exc_info=True)
    _EMOJI_ICONS[key] = icon
    return icon


class HelpTextBrowser(QTextBrowser):
    """Text browser that loads local and remote resources and holds a measure.

    The readable-column limit used to be written into the page as fixed body
    margins, computed for the width the viewport happened to have when the page
    was rendered. Qt's rich-text engine lays those out once, so narrowing the
    window afterwards left the gutters at their old size: the text column
    collapsed to a fraction of the window, most of the page went blank and the
    document — still as wide as the window it was rendered for — grew a
    horizontal scrollbar. The limit lives on the *document's root frame*
    instead, where it can be recomputed on every resize without re-rendering
    the page or losing the reading position. Figures and typeset formulas are
    resized along with it, for the same reason: one formula wider than the
    window is enough to slide every paragraph on the page sideways.
    """

    #: Widest comfortable text column, in pixels. Beyond roughly this the eye
    #: loses the start of the next line; the manual's screenshots are wider and
    #: are allowed to be, which is why this bounds the *text* and not the page.
    MAX_TEXT_WIDTH = 860

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #: Width each image was laid out at when the page arrived, keyed by
        #: source. Scaling always starts from this, so narrowing and widening
        #: the window again restores the figure rather than compounding.
        self._image_sizes: dict = {}
        #: Column the document is currently laid out for.
        self._column: Optional[int] = None

    def setHtml(self, html, *args):
        """Show *html* and fit it to the current column."""
        self._image_sizes = {}
        self._column = None
        super().setHtml(html, *args)
        self.apply_measure()

    def resizeEvent(self, event):
        """Re-fit the text column and its figures to the new viewport width."""
        super().resizeEvent(event)
        self.apply_measure()

    def apply_measure(self):
        """Fit the page to the viewport, capped at ``MAX_TEXT_WIDTH``.

        Called on resize and after every page load, and cheap to call often:
        it returns immediately unless the column actually changed, because
        rewriting frame and image formats relays the document out — which can
        resize the viewport again.
        """
        try:
            column = self.text_column_width()
            if self._column == column:
                return
            self._column = column
            frame = self.document().rootFrame()
            margin = measure_margin(self.viewport().width(), self.MAX_TEXT_WIDTH)
            frame_format = frame.frameFormat()
            if abs(frame_format.leftMargin() - margin) >= 0.5:
                frame_format.setLeftMargin(margin)
                frame_format.setRightMargin(margin)
                frame.setFrameFormat(frame_format)
            self._fit_images(column)
        except Exception:
            logger.debug("could not apply the text measure", exc_info=True)

    def _fit_images(self, column: int):
        """Scale every figure and formula down to at most *column* pixels.

        The scan and the edit are two passes: applying a format inside the
        fragment iteration would be mutating the thing being walked.
        """
        document = self.document()
        edits = []
        block = document.begin()
        while block.isValid():
            fragments = block.begin()
            while not fragments.atEnd():
                fragment = fragments.fragment()
                if fragment.charFormat().isImageFormat():
                    scaled = self._scaled_image(fragment.charFormat(), column)
                    if scaled is not None:
                        edits.append((fragment.position(), fragment.length(), scaled))
                fragments += 1
            block = block.next()
        if not edits:
            return

        was_modified = document.isModified()
        cursor = QTextCursor(document)
        for position, length, image in edits:
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.KeepAnchor)
            cursor.setCharFormat(image)
        if not was_modified:
            document.setModified(False)

    def _scaled_image(self, char_format, column: int):
        """Return *char_format* resized to *column*, or *None* if it fits.

        The size is derived from the width the image had when the page arrived,
        not from its current one, so narrowing and widening the window again
        restores the figure instead of shrinking it twice.
        """
        image = char_format.toImageFormat()
        natural = self._image_sizes.get(image.name())
        if natural is None:
            natural = (image.width(), image.height())
            self._image_sizes[image.name()] = natural
        width, height = natural
        if width <= 0 or height <= 0:
            return None
        target = min(width, column)
        if abs(image.width() - target) < 1:
            return None
        image.setWidth(target)
        image.setHeight(max(1, round(height * target / width)))
        return image

    def text_column_width(self) -> int:
        """Return the width text is laid out in, images and formulas included.

        This is what is left of the viewport once the gutters and the
        document's own margin are taken off, so a figure given this width fits
        without a horizontal scrollbar.
        """
        available = max(320, self.viewport().width())
        margin = measure_margin(available, self.MAX_TEXT_WIDTH)
        return max(160, available - 2 * margin - 2 * _DOCUMENT_MARGIN)

    def loadResource(self, type, name):
        """Load local or remote resources for the help browser."""
        try:
            if name.scheme() in ("http", "https"):
                import urllib.request
                try:
                    with urllib.request.urlopen(name.toString()) as resp:
                        data = resp.read()
                except Exception:
                    return super().loadResource(type, name)
                if type == QTextDocument.ImageResource:
                    img = QImage()
                    try:
                        if img.loadFromData(data):
                            return img
                    except Exception:
                        pass
                    return data
        except Exception:
            pass
        return super().loadResource(type, name)


@persist_plugin_state("help_documentation")
class HelpWidget(QMainWindow):
    """Documentation browser and help resource viewer for ChiSurf.

    Features
    --------
    - A tree built from the documentation's own table of contents
    - A start page, and ranked full-text search with excerpts
    - Typeset formulas, themed pages and working cross-references
    - Previous/next navigation along the reading order
    - Authoring tools (edit, save, review sign-off) behind a toggle

    """

    #: Widest comfortable text column, in pixels. Owned by the viewer, which
    #: applies it; kept here as the name the rest of the window reads it by.
    MAX_TEXT_WIDTH = HelpTextBrowser.MAX_TEXT_WIDTH

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{Glyphs.BOOK} ChiSurf Help")
        self.setMinimumSize(900, 560)
        self.docs_index: dict = {}
        self.current_path: Optional[pathlib.Path] = None
        self.client = HelpClient()
        self._toc: Optional[toc_api.Node] = None
        self._items: dict[str, QTreeWidgetItem] = {}
        self._order: list[toc_api.Node] = []
        self._trail: dict[str, str] = {}
        self._reset_history()
        self._setup_central_widget()
        self._setup_toolbar()
        self._setup_shortcuts()
        self.populate_docs()
        self.show_home()

    # ── central widget ─────────────────────────────────────────────

    def _setup_central_widget(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumWidth(240)
        # The application's own font, explicitly: the tree must not drift into
        # a different face or size from the rest of ChiSurf.
        self.tree.setFont(QApplication.font())
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemActivated.connect(self._on_item_clicked)
        splitter.addWidget(self.tree)

        self.viewer = HelpTextBrowser()
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        self.viewer.anchorClicked.connect(self._on_anchor_clicked)
        self.viewer.setFrameShape(QTextBrowser.NoFrame)

        self.editor = QPlainTextEdit()
        self.editor.setVisible(False)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setFont(QFont("Menlo", 10))

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(2)

        # The address bar: every page has an address, and a reader (or a bug
        # report, or a colleague) can type or paste one. It accepts a
        # documentation path, a source path with a #symbol, a citation key or a
        # URL -- the same vocabulary the links in the pages use.
        address_row = QHBoxLayout()
        address_row.setContentsMargins(0, 0, 0, 2)
        address_row.setSpacing(4)
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText(
            "Address — docs/concepts/fret.md, chisurf/core/fitting/fit.py#sample_fit, "
            "cite:magde1972, https://…"
        )
        self.address_edit.setClearButtonEnabled(True)
        self.address_edit.returnPressed.connect(self._on_address_entered)
        self.address_completer_model = QStringListModel(self)
        completer = QCompleter(self.address_completer_model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.address_edit.setCompleter(completer)
        address_row.addWidget(QLabel("Address:"))
        address_row.addWidget(self.address_edit, 1)
        right_layout_address = address_row

        self.breadcrumb_label = QLabel("")
        self.breadcrumb_label.setStyleSheet("color: #8a8a8a; font-size: 9pt;")
        self.title_label = QLabel("ChiSurf documentation")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.path_label = QLabel("")
        self.path_label.setVisible(False)

        self.review_label = QLabel("")
        self.review_label.setWordWrap(True)
        self.review_label.setVisible(False)

        right_layout.addLayout(right_layout_address)
        right_layout.addWidget(self.breadcrumb_label)
        right_layout.addWidget(self.title_label)
        right_layout.addWidget(self.path_label)
        right_layout.addWidget(self.review_label)
        right_layout.addWidget(self.viewer, 1)
        right_layout.addWidget(self.editor, 1)

        splitter.addWidget(right_panel)

        # The tree and the search box both assume the reader knows roughly
        # where the answer is. The Ask panel is for when they do not; it is a
        # third column rather than a dialog, so an answer and the page it
        # cites are on screen together.
        self.ask_panel = AskPanel(self.client)
        self.ask_panel.pageRequested.connect(self._on_ask_page_requested)
        self.ask_panel.setVisible(False)
        splitter.addWidget(self.ask_panel)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 900, 0])
        layout.addWidget(splitter, 1)
        self.splitter = splitter

    # ── toolbar ─────────────────────────────────────────────────────

    def _setup_toolbar(self):
        toolbar = QToolBar("Help")
        # Named, or QMainWindow.saveState() drops it with a warning and the
        # window comes back without its toolbars.
        toolbar.setObjectName("help_toolbar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar { spacing: 3px; }"
            "QToolButton { font-size: 11pt; padding: 3px 7px; }"
        )
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        home = toolbar.addAction("⌂")
        home.setToolTip("Start page (Alt+Home)")
        home.triggered.connect(self.show_home)

        # Back / Forward. Documentation is a web of cross-references, and a
        # reader who follows one has no way back to where they were reading
        # without them -- the tree selects a page, it does not remember a path.
        self.back_btn = toolbar.addAction("◀")
        self.back_btn.setToolTip("Back to the previous page")
        self.back_btn.setEnabled(False)
        self.back_btn.triggered.connect(self.go_back)
        self.forward_btn = toolbar.addAction("▶")
        self.forward_btn.setToolTip("Forward again")
        self.forward_btn.setEnabled(False)
        self.forward_btn.triggered.connect(self.go_forward)
        toolbar.addSeparator()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search the documentation…   (Ctrl+F)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(280)
        self.search_edit.setMaximumWidth(460)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.search_edit.returnPressed.connect(self._run_search)
        toolbar.addWidget(QLabel(f" {Glyphs.SEARCH} "))
        toolbar.addWidget(self.search_edit)
        # Typing must not re-scan the documentation on every keystroke.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._run_search)

        toolbar.addSeparator()
        doc_action = toolbar.addAction(f"{Glyphs.BOOK}  Online docs")
        doc_action.setToolTip("Open the documentation website in a browser")
        doc_action.triggered.connect(self._open_documentation)
        vid_action = toolbar.addAction("🎬  Videos")
        vid_action.setToolTip("Open the ChiSurf video tutorials")
        vid_action.triggered.connect(self._open_video_tutorials)

        toolbar.addSeparator()
        self.ask_btn = toolbar.addAction("💬  Ask")
        self.ask_btn.setCheckable(True)
        self.ask_btn.setToolTip(
            "Ask the documentation a question in plain words (Ctrl+Shift+A). "
            "The answer names the pages it came from. Needs an AI provider "
            "configured in Settings → AI."
        )
        self.ask_btn.toggled.connect(self._on_ask_toggled)

        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().Expanding, spacer.sizePolicy().Preferred
        )
        toolbar.addWidget(spacer)

        self.authoring_btn = toolbar.addAction("✎")
        self.authoring_btn.setCheckable(True)
        self.authoring_btn.setToolTip(
            "Authoring tools: edit a page, and record the human review that "
            "gates a release. For maintainers of the documentation."
        )
        self.authoring_btn.toggled.connect(self._on_authoring_toggled)

        close_action = toolbar.addAction(f"{Glyphs.CLOSE}")
        close_action.setToolTip("Close the help window")
        close_action.triggered.connect(self.hide)

        self._setup_authoring_toolbar()

    def _setup_authoring_toolbar(self):
        """Build the second toolbar row; hidden until *Authoring* is on."""
        bar = QToolBar("Authoring")
        bar.setObjectName("help_authoring_toolbar")
        bar.setMovable(False)
        bar.setStyleSheet("QToolButton { padding: 3px 7px; }")
        self.addToolBarBreak()
        self.addToolBar(bar)
        bar.setVisible(False)
        self.authoring_toolbar = bar

        self.edit_btn = bar.addAction(f"{Glyphs.EDIT}  Edit")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setEnabled(False)
        self.edit_btn.toggled.connect(self._on_edit_toggled)

        self.save_btn = bar.addAction(f"{Glyphs.SAVE}  Save")
        self.save_btn.setEnabled(False)
        self.save_btn.triggered.connect(self._save_current_document)

        bar.addSeparator()

        self.review_btn = bar.addAction("✅  Mark reviewed")
        self.review_btn.setCheckable(True)
        self.review_btn.setEnabled(False)
        self.review_btn.setToolTip(
            "Record that a *human* has checked this manual page against the "
            "running application.\n"
            "Editing the page afterwards makes the sign-off stale automatically."
        )
        self.review_btn.toggled.connect(self._on_review_toggled)

        self.ai_review_btn = bar.addAction("🤖  AI-reviewed")
        self.ai_review_btn.setCheckable(True)
        self.ai_review_btn.setEnabled(False)
        self.ai_review_btn.setToolTip(
            "Record that an agent has read and corrected this page.\n"
            "Weaker than a human sign-off — an agent cannot check a screenshot "
            "against the interface — so it does not clear the release gate, and "
            "it never overwrites a human sign-off."
        )
        self.ai_review_btn.toggled.connect(self._on_ai_review_toggled)

        bar.addWidget(QLabel(" Show: "))
        self.review_filter = QComboBox()
        self.review_filter.addItem("All pages", "all")
        self.review_filter.addItem("⬜ Unreviewed", review.STATUS_UNREVIEWED)
        self.review_filter.addItem("🤖 AI-reviewed", review.STATUS_AI_REVIEWED)
        self.review_filter.addItem("⚠️ Stale", review.STATUS_STALE)
        self.review_filter.addItem("✅ Reviewed", review.STATUS_REVIEWED)
        self.review_filter.setToolTip("Filter the user manual by human-review status.")
        self.review_filter.currentIndexChanged.connect(lambda _: self._apply_review_filter())
        bar.addWidget(self.review_filter)

        bar.addSeparator()
        self.developer_btn = bar.addAction("🛠  Developer docs")
        self.developer_btn.setCheckable(True)
        self.developer_btn.setToolTip(
            "Also list architecture notes and the bundled modules' documentation."
        )
        self.developer_btn.toggled.connect(lambda _: self.populate_docs())

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Expanding, spacer.sizePolicy().Preferred)
        bar.addWidget(spacer)
        self.review_summary_label = QLabel("")
        self.review_summary_label.setStyleSheet("color: #888888; font-size: 9pt;")
        self.review_summary_label.setToolTip(
            "Human-review status of the user manual. Unreviewed or stale pages "
            "block a release."
        )
        bar.addWidget(self.review_summary_label)

    def _setup_shortcuts(self):
        """Keyboard: search, history, home and zoom, as a browser has them."""
        for sequence, slot in (
            (QKeySequence.Find, self.search_edit.setFocus),
            (QKeySequence.Back, self.go_back),
            (QKeySequence.Forward, self.go_forward),
            (QKeySequence("Alt+Home"), self.show_home),
            (QKeySequence("Ctrl+Shift+A"), self.show_ask_panel),
            (QKeySequence.ZoomIn, lambda: self.zoom(+1)),
            (QKeySequence("Ctrl+="), lambda: self.zoom(+1)),
            (QKeySequence("Ctrl++"), lambda: self.zoom(+1)),
            (QKeySequence.ZoomOut, lambda: self.zoom(-1)),
            (QKeySequence("Ctrl+-"), lambda: self.zoom(-1)),
            (QKeySequence("Ctrl+0"), self.reset_zoom),
        ):
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(slot)
        self.viewer.viewport().installEventFilter(self)

    # ── zoom ────────────────────────────────────────────────────────

    #: Body text size in points, and the range the reader may take it to.
    DEFAULT_FONT_SIZE = 12.0
    MIN_FONT_SIZE = 7.0
    MAX_FONT_SIZE = 24.0

    @property
    def font_size(self) -> float:
        """Point size the pages are rendered at."""
        return getattr(self, "_font_size", self.DEFAULT_FONT_SIZE)

    def zoom(self, steps: int = 1):
        """Make the text larger or smaller by *steps* half-point increments.

        The page is re-rendered rather than scaled: its sizes are given in
        points in the stylesheet, so ``QTextBrowser.zoomIn`` would move the
        body text and leave every heading, table and formula where it was.
        """
        self.set_font_size(self.font_size + 0.5 * steps)

    def reset_zoom(self):
        """Back to the default text size."""
        self.set_font_size(self.DEFAULT_FONT_SIZE)

    def set_font_size(self, size: float):
        """Render at *size* points, clamped, keeping the reading position."""
        size = max(self.MIN_FONT_SIZE, min(self.MAX_FONT_SIZE, float(size)))
        if abs(size - self.font_size) < 1e-6:
            return
        self._font_size = size
        # The formulas are images sized in points, so they are re-typeset too.
        self._math_renderer = None
        position = self.viewer.verticalScrollBar().value()
        maximum = max(1, self.viewer.verticalScrollBar().maximum())
        self._reshow()
        bar = self.viewer.verticalScrollBar()
        bar.setValue(round(bar.maximum() * position / maximum))

    def _reshow(self):
        """Render the page that is open again, at the current size."""
        if self.current_path is not None:
            self._open_document_path(self.current_path)
        elif self.search_edit.text().strip():
            self._run_search()
        else:
            self._show_generated(self._home_html())

    #: Modifiers that turn the wheel into a zoom. Ctrl/⌘ is the browser
    #: convention; Shift is here because on a trackpad Ctrl+scroll is taken by
    #: the operating system's own screen magnifier, and the gesture then never
    #: reaches the application at all.
    ZOOM_MODIFIERS = Qt.ControlModifier | Qt.ShiftModifier | Qt.MetaModifier

    def eventFilter(self, watched, event):
        """Ctrl/⌘ + wheel and Shift + wheel zoom, as they do in a browser."""
        try:
            if (
                watched is self.viewer.viewport()
                and event.type() == QEvent.Wheel
                and event.modifiers() & self.ZOOM_MODIFIERS
            ):
                # Shift+wheel is horizontal scrolling on most mice, so the
                # delta arrives on x rather than y; either axis zooms.
                delta = event.angleDelta().y() or event.angleDelta().x()
                if delta:
                    self.zoom(1 if delta > 0 else -1)
                return True
        except Exception:
            logger.debug("could not handle a wheel event", exc_info=True)
        return super().eventFilter(watched, event)

    def _on_authoring_toggled(self, checked: bool):
        self.authoring_toolbar.setVisible(checked)
        if not checked and self.edit_btn.isChecked():
            self.edit_btn.setChecked(False)
        self._refresh_tree_badges()
        self._update_review_summary()
        self._refresh_review_state(self.current_path)

    # ── the tree ────────────────────────────────────────────────────

    def populate_docs(self):
        """Rebuild the navigation tree from the documentation's contents."""
        self.tree.clear()
        self._items = {}
        self._order = []
        self._trail = {}
        include_dev = bool(
            getattr(self, "developer_btn", None) and self.developer_btn.isChecked()
        )
        try:
            self._toc = toc_api.build_toc(include_development=include_dev)
        except Exception:
            logger.exception("could not read the documentation contents")
            self._toc = toc_api.Node("ChiSurf help", kind="section")

        for section in self._toc.children:
            item = QTreeWidgetItem(self.tree, [self._label(section)])
            self._decorate(item, section, {}, ["", section.title])
            for child in section.children:
                self._add_node(item, child, {}, [section.title])
        # Badges last: the statuses are read for the pages that ended up in the
        # tree, so nothing rediscovers the documentation a second time.
        self._refresh_tree_badges()
        self._refresh_address_completions()
        self._update_review_summary()

    def _add_node(self, parent, node, statuses, trail):
        item = QTreeWidgetItem(parent, [self._label(node)])
        self._decorate(item, node, statuses, trail + [node.title])
        for child in node.children:
            self._add_node(item, child, statuses, trail + [node.title])
        return item

    def _icon_size(self) -> int:
        """Icon edge length that matches the tree's own row height."""
        try:
            return max(12, self.tree.fontMetrics().height())
        except Exception:
            return 16

    def _label(self, node) -> str:
        """The row's text — the title alone.

        The icons live in the item's *icon* role, not in this string. An emoji
        inside the text makes Qt fall back to a colour font for the whole item,
        and the fallback has different metrics, so the row ends up in a
        different face and size from the rest of the application. Painted into
        a pixmap by :func:`emoji_icon` it is just a picture beside a label, and
        the label keeps the application's font.
        """
        return node.title

    def _decorate(self, item, node, statuses, trail):
        """Attach a node's data, badge and tooltip to its tree item."""
        item.setData(0, _ROLE_KIND, node.kind)
        if node.kind == "section":
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            icon = SECTION_ICONS.get(node.title)
            if icon:
                item.setIcon(0, emoji_icon(icon, self._icon_size()))
        if node.path is None:
            item.setData(0, _ROLE_PATH, None)
            return
        key = str(node.path)
        item.setData(0, _ROLE_PATH, key)
        status = statuses.get(key, "")
        item.setData(0, _ROLE_REVIEW, status)
        tip = node.summary or ""
        if tip:
            item.setToolTip(0, self._wrap_tooltip(tip))
        self._items[key] = item
        self._order.append(node)
        self._trail[key] = " › ".join(part for part in trail[:-1] if part)

    @staticmethod
    def _wrap_tooltip(text: str, width: int = 72) -> str:
        """Wrap a tooltip; Qt shows a long single line as a screen-wide bar."""
        import textwrap

        return "\n".join(
            line
            for paragraph in text.splitlines()
            for line in textwrap.wrap(paragraph, width) or [""]
        )

    def _review_statuses(self) -> dict:
        """Return ``{path: status}`` for the review-tracked pages in the tree.

        Read straight from the review registry rather than through
        ``help.docs.list``, which rediscovers every document in the project —
        a second full walk of the tree the contents were just built from.
        """
        statuses = {}
        try:
            for node in self._order:
                if node.path is None or not review.is_tracked(node.path):
                    continue
                statuses[str(node.path)] = review.status_of(node.path).status
        except Exception:
            logger.debug("review status unavailable", exc_info=True)
        return statuses

    # ── the address bar ─────────────────────────────────────────────

    def _refresh_address_completions(self):
        """Offer every page in the tree as a completion."""
        if not hasattr(self, "address_completer_model"):
            return
        root = toc_api.repository_root()
        addresses = []
        for key in self._items:
            try:
                addresses.append(pathlib.Path(key).relative_to(root).as_posix())
            except ValueError:
                addresses.append(key)
        self.address_completer_model.setStringList(sorted(addresses))

    def _set_address(self, path: Optional[pathlib.Path]):
        """Show the address of what is on screen, without disturbing typing."""
        if not hasattr(self, "address_edit") or self.address_edit.hasFocus():
            return
        if path is None:
            self.address_edit.setText("")
            return
        try:
            text = path.relative_to(toc_api.repository_root()).as_posix()
        except ValueError:
            text = str(path)
        self.address_edit.setText(text)

    def _on_address_entered(self):
        """Go to whatever was typed: a page, a source symbol, a key or a URL."""
        text = self.address_edit.text().strip()
        if not text:
            return
        if text.startswith(("http://", "https://", "doi:", "mailto:")):
            from chisurf.gui.widgets.tools.doc_links import open_link

            open_link(text)
            return
        if text.startswith("cite:"):
            from chisurf.plugins.core.help.api.bibliography import bibliography, entry_url
            from chisurf.gui.widgets.tools.doc_links import open_link

            entry = bibliography().get(text[len("cite:"):].strip())
            if entry is not None:
                open_link(entry_url(entry))
                return

        from chisurf.plugins.core.help.api.source_links import is_source_path

        if is_source_path(text):
            from chisurf.gui.widgets.tools.code_links import open_source

            if open_source(text):
                return

        from chisurf.gui.widgets.tools.doc_links import resolve_document

        base = self.current_path.parent if self.current_path else None
        anchor = ""
        if "#" in text:
            text, _, anchor = text.partition("#")
        target = resolve_document(text, base)
        if target is not None:
            self.navigate(target, anchor or None)
            return
        # Not an address: treat it as something to search for, which is what a
        # browser does with a bare word.
        self.search_edit.setText(text)
        self._run_search()

    # ── search ──────────────────────────────────────────────────────

    def _on_search_text_changed(self, _text):
        self._search_timer.start()

    def _on_filter_text_changed(self, text):
        """Filter the tree to the pages matching *text* (kept for callers)."""
        self.search_edit.setText(text)

    def _run_search(self):
        query = self.search_edit.text().strip()
        if len(query) < 2:
            self._filter_tree("")
            if self.current_path is None:
                self.show_home()
            return
        hits = self.search(query)
        self._filter_tree_to({str(hit["node"].path) for hit in hits})
        self._show_results(query, hits)

    def search(self, query: str, limit: int = 40) -> list[dict]:
        """Rank the documentation against *query*.

        Parameters
        ----------
        query : str
            What the reader typed.
        limit : int, optional
            Most results to return.

        Returns
        -------
        list of dict
            ``{"node", "score", "excerpt"}``, best first. A title match beats a
            heading match beats a body match, because a page *about* the thing
            asked for is almost always the one wanted.

        """
        needle = query.strip().lower()
        if not needle:
            return []
        words = [word for word in re.split(r"\s+", needle) if word]
        results = []
        for node in self._order:
            entry = self._indexed(node.path)
            if entry is None:
                continue
            score = 0
            for word in words:
                if word in entry["title"]:
                    score += 12
                if word in entry["file_name"]:
                    score += 4
                if word in entry["headings"]:
                    score += 5
                count = entry["text"].count(word)
                if count:
                    score += min(count, 8)
            if needle in entry["title"]:
                score += 20
            if not score:
                continue
            results.append(
                {
                    "node": node,
                    "score": score,
                    "excerpt": self._excerpt(entry["raw"], words),
                }
            )
        results.sort(key=lambda hit: (-hit["score"], hit["node"].title))
        return results[:limit]

    def _indexed(self, path: Optional[pathlib.Path]) -> Optional[dict]:
        """Return (and cache) the searchable form of a page."""
        if path is None:
            return None
        key = str(path)
        entry = self.docs_index.get(key)
        if entry is not None:
            return entry
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            return None
        # The OKF header is metadata: matching it is fine, quoting it back at
        # the reader as a result excerpt is not.
        raw = md_api.strip_front_matter(raw)
        headings = "\n".join(
            match.group(1)
            for match in re.finditer(r"^#{1,6}\s+(.+)$", raw, re.M)
        ).lower()
        entry = {
            "path": path,
            "raw": raw,
            "text": raw.lower(),
            "headings": headings,
            "file_name": path.name.lower(),
            "title": (toc_api.page_title(path) or path.stem).lower(),
        }
        self.docs_index[key] = entry
        return entry

    @staticmethod
    def _excerpt(raw: str, words: list[str], width: int = 220) -> str:
        """Return the passage around the first match, as readable plain text.

        The source is markup in two dialects, and an excerpt that shows it —
        ``(concept-anisotropy)=``, a row of ``''''''``, ``.. seealso::`` — costs
        the reader more than it tells them, so the markup is stripped rather
        than merely collapsed.
        """
        text = re.sub(r"```.*?```", " ", raw, flags=re.DOTALL)
        text = re.sub(r"^---\s*\n.*?\n---\s*\n", " ", text, flags=re.DOTALL)
        text = re.sub(r"^\([A-Za-z0-9_.:-]+\)=\s*$", " ", text, flags=re.M)
        text = re.sub(r"^\s*\.\.\s+\S+::.*$", " ", text, flags=re.M)
        text = re.sub(r"^\s*:[\w-]+:.*$", " ", text, flags=re.M)
        text = re.sub(r"^([!-/:-@\[-`{-~])\1{2,}\s*$", " ", text, flags=re.M)
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r":\w+:`([^`]*)`", r"\1", text)
        text = re.sub(r"\{\w+\}`([^`]*)`", r"\1", text)
        text = re.sub(r"[#*`>|]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        lowered = text.lower()
        position = -1
        for word in words:
            position = lowered.find(word)
            if position >= 0:
                break
        if position < 0:
            return text[:width]
        start = max(0, position - width // 3)
        excerpt = text[start: start + width].strip()
        return ("…" if start else "") + excerpt + ("…" if start + width < len(text) else "")

    def _filter_tree(self, needle: str):
        """Show every row again (an empty *needle*), or only the matching ones."""
        if not needle:
            self._filter_tree_to(None)

    def _filter_tree_to(self, keys: Optional[set]):
        """Keep only the rows in *keys* — the search hits — or all of them.

        The tree is filtered by the *result set* rather than by the raw string:
        a phrase like "anisotropy g-factor" appears verbatim in no title, so
        matching the string against rows emptied the tree exactly when the
        search had found forty pages.
        """
        root = self.tree.invisibleRootItem()
        for index in range(root.childCount()):
            self._filter_item(root.child(index), keys)
        if keys is not None:
            self.tree.expandAll()

    def _filter_item(self, item, keys: Optional[set]) -> bool:
        if keys is None:
            item.setHidden(False)
            for index in range(item.childCount()):
                self._filter_item(item.child(index), None)
            return True
        path = item.data(0, _ROLE_PATH)
        matched = bool(path) and str(path) in keys
        for index in range(item.childCount()):
            if self._filter_item(item.child(index), keys):
                matched = True
        item.setHidden(not matched)
        return matched

    def _show_results(self, query: str, hits: list[dict]):
        """Render the search results as a page."""
        self.current_path = None
        self.breadcrumb_label.setText("Search")
        self.title_label.setText(f"{len(hits)} result(s) for “{query}”")
        self.review_label.setVisible(False)
        if hasattr(self, "edit_btn"):
            self.edit_btn.setEnabled(False)
            self.save_btn.setEnabled(False)

        if not hits:
            body = (
                "<p>Nothing matched. Try a single word — the search covers every "
                "page's full text, so a narrower term usually finds more.</p>"
            )
        else:
            rows = []
            for hit in hits:
                node = hit["node"]
                where = self._trail.get(str(node.path), "")
                rows.append(
                    f'<p><a href="{_html.escape(str(node.path), quote=True)}">'
                    f'<b>{_html.escape(node.title)}</b></a>'
                    + (f' <span class="doc-hit">— {_html.escape(where)}</span>' if where else "")
                    + f'<br><span class="doc-hit">{_html.escape(hit["excerpt"])}</span></p>'
                )
            body = "\n".join(rows)
        self._show_generated(f"<h1>Search</h1>{body}")

    # ── the start page ──────────────────────────────────────────────

    def show_home(self):
        """Show the start page: what the documentation holds, and where to begin."""
        self.current_path = None
        self.breadcrumb_label.setText("")
        self.title_label.setText("ChiSurf documentation")
        self.review_label.setVisible(False)
        if hasattr(self, "edit_btn"):
            self.edit_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            self.review_btn.setEnabled(False)
        self._show_generated(self._home_html())
        self._push_history(None, "")

    def _home_html(self) -> str:
        root = toc_api.repository_root()
        parts = [
            "<h1>ChiSurf documentation</h1>",
            "<p>ChiSurf analyses time-resolved and single-molecule fluorescence "
            "data — TCSPC, FCS and smFRET. The documentation is in four layers: "
            "the <b>theory</b> of each method, a <b>guide</b> that runs it in "
            "this application, the <b>fitting interface</b> itself with complete "
            "worked examples, and a <b>reference</b> for formats, settings and "
            "every plugin parameter.</p>",
            "<h2>Start here</h2>",
        ]
        for relative, description in START_HERE:
            path = root / relative
            if not path.is_file():
                continue
            title = toc_api.page_title(path) or path.stem
            parts.append(
                f'<p><a href="{_html.escape(str(path), quote=True)}">'
                f"<b>{_html.escape(title)}</b></a> — "
                f'<span class="doc-hit">{_html.escape(description)}</span></p>'
            )

        parts.append("<h2>The parts of the documentation</h2>")
        for section in (self._toc.children if self._toc else []):
            icon = SECTION_ICONS.get(section.title, "📄")
            target = section.path or (
                section.children[0].path if section.children else None
            )
            heading = _html.escape(section.title)
            if target is not None:
                heading = (
                    f'<a href="{_html.escape(str(target), quote=True)}">{heading}</a>'
                )
            parts.append(
                f'<p>{icon} <span class="doc-card-title">{heading}</span><br>'
                f'<span class="doc-hit">{_html.escape(section.summary)}</span></p>'
            )
            names = [child.title for child in section.children[:6]]
            if names:
                parts.append(
                    '<p class="doc-hit">'
                    + _html.escape(" · ".join(names))
                    + ("…" if len(section.children) > 6 else "")
                    + "</p>"
                )
        parts.append(
            "<hr><p class=\"doc-hit\">Press <b>Ctrl+F</b> to search every page, "
            "or use the tree on the left. Every plugin's <b>?</b> button opens "
            "its own help here.</p>"
        )
        return "\n".join(parts)

    def _show_generated(self, body_html: str):
        """Show HTML this window generated (start page, search results)."""
        from chisurf.plugins.core.help.api import theme as _theme

        css = _theme.stylesheet(self.doc_theme, font_size=self.font_size)
        self._set_viewer_html(f"<html><head>{css}</head><body>{body_html}</body></html>", "", None)

    # ── document navigation ─────────────────────────────────────────

    def _on_item_clicked(self, item, column=0):
        path = item.data(0, _ROLE_PATH)
        if not path:
            item.setExpanded(not item.isExpanded())
            return
        # Through navigate(), so picking a page in the tree is part of the trail
        # Back walks -- a reader who clicks a cross-reference and then Back
        # expects to land where they were, whichever way they got there.
        self.navigate(pathlib.Path(path))

    def _reset_history(self):
        """Give this window its own history (a class-level list would be shared)."""
        self._history: list = []
        self._history_index: int = -1

    def _push_history(self, path: Optional[pathlib.Path], anchor: str):
        entry = (path, anchor or "")
        if self._history and self._history[self._history_index] == entry:
            return
        # A new branch discards whatever was ahead, as a browser does.
        del self._history[self._history_index + 1:]
        self._history.append(entry)
        self._history_index = len(self._history) - 1
        self._update_history_buttons()

    # ── the Ask panel ───────────────────────────────────────────────

    def _on_ask_toggled(self, checked: bool):
        """Show or hide the question panel, keeping the reading column wide."""
        self.ask_panel.setVisible(checked)
        total = sum(self.splitter.sizes()) or self.width()
        if checked:
            panel = max(340, int(total * 0.3))
            tree = self.splitter.sizes()[0] or 300
            self.splitter.setSizes([tree, max(200, total - tree - panel), panel])
            self.ask_panel.input.setFocus()
        else:
            tree = self.splitter.sizes()[0] or 300
            self.splitter.setSizes([tree, max(200, total - tree), 0])

    def show_ask_panel(self):
        """Open the question panel and put the cursor in it."""
        self.ask_btn.setChecked(True)

    def _on_ask_page_requested(self, document: str, section: str):
        """Open a page the assistant cited.

        The identifier is bundle-relative (``docs/concepts/fret.md``), which is
        what the index reports and what the reader sees; it is resolved here
        rather than in the panel, because navigation belongs to the browser.
        """
        from chisurf.core.agent import doc_index

        path = doc_index.resolve(document)
        if path is None:
            return
        anchor = md_api.slugify_heading(section) if section else None
        self.navigate(pathlib.Path(path), anchor)

    def navigate(self, file_path: pathlib.Path, anchor: Optional[str] = None):
        """Open a page **and record it in the history**.

        Every route into a document that a *reader* takes goes through here --
        the tree, a cross-reference, another tool's help link. Only the Back and
        Forward buttons call :meth:`_open_document_path` directly, so replaying
        history cannot append to it and trap the reader in a loop.
        """
        path = pathlib.Path(file_path)
        if not path.exists():
            return
        self._push_history(path, anchor or "")
        self._open_document_path(path, anchor)

    def go_back(self):
        """Show the previous page in the history."""
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._replay()

    def go_forward(self):
        """Show the next page in the history."""
        if self._history_index + 1 >= len(self._history):
            return
        self._history_index += 1
        self._replay()

    def _replay(self):
        path, anchor = self._history[self._history_index]
        if path is None:
            self.current_path = None
            self._show_generated(self._home_html())
            self.title_label.setText("ChiSurf documentation")
            self.breadcrumb_label.setText("")
        else:
            self._open_document_path(path, anchor or None)
        self._update_history_buttons()

    def _update_history_buttons(self):
        """Enable Back/Forward according to where we are in the history."""
        back = getattr(self, "back_btn", None)
        forward = getattr(self, "forward_btn", None)
        if back is not None:
            back.setEnabled(self._history_index > 0)
        if forward is not None:
            forward.setEnabled(self._history_index + 1 < len(self._history))

    def _open_document_path(self, file_path: pathlib.Path, anchor: Optional[str] = None):
        if not file_path.exists():
            return
        self.current_path = file_path
        key = str(file_path)
        title = toc_api.page_title(file_path) or file_path.name
        self.title_label.setText(title)
        self.breadcrumb_label.setText(self._trail.get(key, ""))
        self.path_label.setText(key)
        self._set_address(file_path)
        if hasattr(self, "edit_btn"):
            self.edit_btn.setEnabled(True)
        self._select_in_tree(key)
        self._refresh_review_state(file_path)
        # Images are referenced relative to the document (``_images/…`` in the
        # manual, ``figures/…`` in the guides). A base URL alone does not make
        # QTextBrowser resolve them, so give it an explicit search path.
        try:
            self.viewer.setSearchPaths([str(file_path.parent)])
        except Exception:
            pass
        result = self.client.read_doc(key)
        if result is None:
            self.viewer.setPlainText(f"Could not read {file_path}")
            return
        text = result.get("content", "")
        if hasattr(self, "edit_btn") and self.edit_btn.isChecked():
            # The *editor* shows the source as it is on disk -- rewriting the
            # roles there would save the rewrite back into the file.
            self.editor.setPlainText(text)
            self.editor.show()
            self.viewer.hide()
            self.save_btn.setEnabled(True)
        else:
            html, shown = self._render(file_path, text)
            if html is not None:
                html = self._append_pager(html, file_path)
            self._set_viewer_html(html, shown, file_path)
            self.viewer.show()
            self.editor.hide()
            if hasattr(self, "save_btn"):
                self.save_btn.setEnabled(False)
            if anchor:
                try:
                    self.viewer.scrollToAnchor(anchor)
                except Exception:
                    pass

    def _select_in_tree(self, key: str):
        """Reveal and select the tree row for the page being shown."""
        item = self._items.get(key)
        if item is None:
            return
        self.tree.blockSignals(True)
        try:
            self.tree.setCurrentItem(item)
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self.tree.scrollToItem(item)
        finally:
            self.tree.blockSignals(False)

    def _append_pager(self, html: str, file_path: pathlib.Path) -> str:
        """Add previous/next links along the documentation's reading order.

        A manual is read in order at least once; without this the only way from
        one page to the next is to find it again in the tree.
        """
        paths = [node.path for node in self._order]
        try:
            position = paths.index(file_path)
        except ValueError:
            return html
        previous = self._order[position - 1] if position > 0 else None
        following = self._order[position + 1] if position + 1 < len(self._order) else None
        if previous is None and following is None:
            return html
        left = (
            f'<a href="{_html.escape(str(previous.path), quote=True)}">◀ '
            f"{_html.escape(previous.title)}</a>" if previous else ""
        )
        right = (
            f'<a href="{_html.escape(str(following.path), quote=True)}">'
            f"{_html.escape(following.title)} ▶</a>" if following else ""
        )
        pager = (
            '<hr><table width="100%" border="0" cellpadding="0" cellspacing="0"><tr>'
            f'<td align="left">{left}</td><td align="right">{right}</td>'
            "</tr></table>"
        )
        if "</body>" in html:
            return html.replace("</body>", f"{pager}</body>", 1)
        return html + pager

    # ── rendering ───────────────────────────────────────────────────

    @property
    def doc_theme(self):
        """Colours for rendered pages, following the application's palette."""
        if getattr(self, "_doc_theme", None) is None:
            from chisurf.plugins.core.help.api import theme as _theme

            self._doc_theme = _theme.from_palette(self.viewer)
        return self._doc_theme

    @property
    def math_renderer(self):
        """Shared LaTeX renderer, so a formula is typeset once per session."""
        if getattr(self, "_math_renderer", None) is None:
            from chisurf.plugins.core.help.api.mathtext import MathRenderer

            # The formulas are bounded by the *text column*, not by the window:
            # a formula wider than the column gives the whole page a horizontal
            # scrollbar, and every paragraph on it then slides sideways.
            try:
                column = self.viewer.text_column_width()
            except Exception:
                column = self.MAX_TEXT_WIDTH
            self._math_renderer = MathRenderer(
                colour=self.doc_theme.text,
                font_size=self.font_size,
                max_width=column,
            )
        return self._math_renderer

    def _render(self, file_path: pathlib.Path, text: str):
        """Render *text* for display, returning ``(html, source_shown)``.

        MyST cross-reference roles are rewritten to Markdown links first, so
        ``{ref}`concept-x``` — which a Markdown converter renders as literal
        text — becomes something to click. Rendering happens here rather than
        in the backend because only the GUI knows the theme the page has to
        match.
        """
        from chisurf.gui.widgets.tools.doc_links import expand_roles
        from chisurf.plugins.core.help.api.bibliography import expand_citations

        try:
            shown = expand_roles(text, file_path.parent)
        except Exception:
            logger.debug("could not expand cross-reference roles", exc_info=True)
            shown = text
        try:
            # ``{cite}`key``` becomes a link to the paper, resolved against the
            # one bibliography the website's `cite` role reads as well.
            shown = expand_citations(shown)
        except Exception:
            logger.debug("could not expand citations", exc_info=True)
        try:
            # ``{src}`file#symbol``` becomes a link the click handler routes to
            # the code editor.
            from chisurf.plugins.core.help.api.source_links import expand_source_roles

            shown = expand_source_roles(shown)
        except Exception:
            logger.debug("could not expand source roles", exc_info=True)
        try:
            from chisurf.plugins.core.help.api.render import render_document

            html = render_document(
                shown,
                file_path,
                theme=self.doc_theme,
                math=self.math_renderer,
                font_size=self.font_size,
            )
        except Exception:
            # Not debug: the reader is about to be shown raw Markdown, source
            # syntax and all, and nothing else says why.
            logger.warning("could not render %s", file_path, exc_info=True)
            html = None
        return html, shown

    def _set_viewer_html(
        self, html: Optional[str], text: str, file_path: Optional[pathlib.Path]
    ):
        """Show *html* for *file_path*, resolving and scaling its images."""
        if html is None:
            self.viewer.setPlainText(text)
            return
        base_dir = file_path.parent if file_path is not None else None
        if base_dir is not None:
            try:
                self.viewer.setSearchPaths([str(base_dir)])
            except Exception:
                pass
        try:
            if base_dir is not None:
                html = _constrain_image_widths(
                    html, base_dir, self.viewer.text_column_width()
                )
        except Exception:
            pass
        self._paint_viewer_background()
        try:
            if file_path is not None:
                self.viewer.setHtml(html, QUrl.fromLocalFile(str(file_path)))
            else:
                self.viewer.setHtml(html)
        except Exception:
            self.viewer.setHtml(html)

    def _paint_viewer_background(self):
        """Give the viewport the page's own background colour.

        Qt paints the area around the document with the widget's base colour,
        not the body background from the HTML, so without this a themed page
        sits in a rectangle of a different shade.
        """
        try:
            self.viewer.setStyleSheet(
                "QTextBrowser { padding: 10px; border: none; "
                f"background-color: {self.doc_theme.background}; }}"
            )
        except Exception:
            logger.debug("could not apply the document background", exc_info=True)

    def _on_anchor_clicked(self, url):
        """Follow a link in the page being read.

        The three cases, in order: an in-page anchor scrolls; a web address or a
        DOI opens in the system browser; anything else is treated as a **cross
        reference to another document** and resolved -- relative to the page
        being read first, then against the docs tree -- so the ordinary
        ``[text](other_page.md)`` that the sources are written with actually
        goes somewhere.
        """
        from chisurf.gui.widgets.tools.doc_links import open_link, resolve_document

        try:
            fragment = url.fragment() or None
            if not url.scheme() and not url.path() and fragment:
                self.viewer.scrollToAnchor(fragment)
                return
            if url.scheme() in ("http", "https", "ftp", "mailto", "doi"):
                open_link(url)
                return

            base = self.current_path.parent if self.current_path else None
            raw = url.path() or url.toString()
            # Source, not documentation: open it in the code editor, at the
            # symbol the link names.
            from chisurf.plugins.core.help.api.source_links import is_source_path

            if is_source_path(raw) or (fragment and is_source_path(f"{raw}#{fragment}")):
                from chisurf.gui.widgets.tools.code_links import open_source

                if open_source(f"{raw}#{fragment}" if fragment else raw, base):
                    return

            target = pathlib.Path(url.toLocalFile()) if url.isLocalFile() else None
            if target is None:
                target = resolve_document(raw, base)
            if target is not None and target.exists():
                if target.suffix.lower() in (".md", ".rst", ".txt"):
                    self.navigate(target, fragment)
                    return
                open_link(QUrl.fromLocalFile(str(target)))
                return
            # Not a document and not a web address: hand it to the shared
            # resolver, which knows about DOIs written bare.
            if not open_link(url, self.current_path.parent if self.current_path else None):
                logger.debug("help: nowhere to go for %s", url.toString())
        except Exception:
            logger.debug("help: could not follow %s", url.toString(), exc_info=True)

    # ── edit / save ──────────────────────────────────────────────────

    def _on_edit_toggled(self, checked):
        if self.current_path is None:
            if checked:
                self.edit_btn.setChecked(False)
            return

        self.edit_btn.setText(f"{Glyphs.EYE}  View" if checked else f"{Glyphs.EDIT}  Edit")

        result = self.client.read_doc(str(self.current_path))
        if result is None:
            dialogs.error(self, "Error", f"Could not read {self.current_path}")
            if checked:
                self.edit_btn.setChecked(False)
            return
        text = result.get("content", "")
        if checked:
            self.editor.setPlainText(text)
            self.editor.show()
            self.viewer.hide()
            self.save_btn.setEnabled(True)
        else:
            html, shown = self._render(self.current_path, text)
            self._set_viewer_html(html, shown, self.current_path)
            self.viewer.show()
            self.editor.hide()
            self.save_btn.setEnabled(False)

    def _save_current_document(self):
        if self.current_path is None:
            return
        text = self.editor.toPlainText()
        ok = self.client.save_doc(str(self.current_path), text)
        if not ok:
            dialogs.error(self, "Error", f"Could not save {self.current_path}")
            return
        self.docs_index.pop(str(self.current_path), None)
        if not self.edit_btn.isChecked():
            html, shown = self._render(self.current_path, text)
            self._set_viewer_html(html, shown, self.current_path)
        # Saving changes the content hash, so a signed-off page becomes stale.
        self._refresh_review_state(self.current_path)
        self._refresh_tree_badges()

    # ── human review ────────────────────────────────────────────────

    def _refresh_review_state(self, file_path: Optional[pathlib.Path]):
        """Update the review banner and both sign-off buttons for *file_path*."""
        if not hasattr(self, "review_btn"):
            return
        if file_path is None or not self.authoring_btn.isChecked():
            self.review_label.setVisible(False)
            self.review_btn.setEnabled(False)
            self.ai_review_btn.setEnabled(False)
            return

        info = self.client.review_status(str(file_path))
        tracked = bool(info.get("tracked"))
        status = info.get("status", "")

        for button, level in (
            (self.review_btn, review.STATUS_REVIEWED),
            (self.ai_review_btn, review.STATUS_AI_REVIEWED),
        ):
            button.blockSignals(True)
            button.setEnabled(tracked)
            button.setChecked(tracked and status == level)
            button.blockSignals(False)

        if not tracked:
            self.review_label.setVisible(False)
            return

        badge = REVIEW_BADGES.get(status, "")
        tip = REVIEW_TOOLTIPS.get(status, "")
        who = ""
        if status in review.SIGNED_STATUSES and info.get("reviewer"):
            kind = "agent" if info.get("reviewer_kind") == "ai" else info["reviewer"]
            who = f" — {kind}, {info.get('date', '')}"
        elif status == review.STATUS_STALE and info.get("previous_status"):
            who = f" — was {info['previous_status']}"
        colours = {
            review.STATUS_REVIEWED: ("#1b5e20", "#e8f5e9"),
            review.STATUS_AI_REVIEWED: ("#0d47a1", "#e3f2fd"),
            review.STATUS_STALE: ("#e65100", "#fff3e0"),
            review.STATUS_UNREVIEWED: ("#b71c1c", "#ffebee"),
        }
        fg, bg = colours.get(status, ("#000000", "#f0f0f0"))
        self.review_label.setText(f"{badge} {status.upper()}{who} — {tip}")
        self.review_label.setStyleSheet(
            f"color: {fg}; background: {bg}; padding: 4px; border-radius: 3px;"
            "font-size: 9pt;"
        )
        self.review_label.setVisible(True)

    def _on_review_toggled(self, checked: bool):
        """Record or clear the *human* sign-off for the current page."""
        self._record_review(
            review.STATUS_REVIEWED if checked else review.STATUS_UNREVIEWED
        )

    def _on_ai_review_toggled(self, checked: bool):
        """Record or clear the *agent* sign-off for the current page."""
        self._record_review(
            review.STATUS_AI_REVIEWED if checked else review.STATUS_UNREVIEWED
        )

    def _record_review(self, status: str):
        """Write *status* for the open page and refresh what shows it."""
        if self.current_path is None:
            return
        if status == review.STATUS_AI_REVIEWED:
            reviewer = "agent"
        else:
            try:
                reviewer = getpass.getuser()
            except Exception:
                reviewer = ""
        result = self.client.set_review_status(str(self.current_path), status, reviewer)
        if not result:
            dialogs.warning(
                self,
                "Review status",
                f"Could not record review status for {self.current_path.name}.",
            )
        self._refresh_review_state(self.current_path)
        self._refresh_tree_badges()
        self._update_review_summary()

    def _refresh_tree_badges(self):
        """Re-read review status and colour the tree while authoring.

        Colour, not a badge character: an emoji in a row makes Qt fall back to
        a colour font for the whole item, with different metrics, so a badged
        manual was set in a different face from everything above it. The state
        still has to be visible at a glance while reviewing, and a foreground
        colour does that without touching the type.
        """
        statuses = self._review_statuses()
        showing = bool(getattr(self, "authoring_btn", None) and self.authoring_btn.isChecked())
        for key, item in self._items.items():
            status = statuses.get(key)
            if status is None:
                continue
            item.setData(0, _ROLE_REVIEW, status)
            colour = REVIEW_COLOURS.get(status) if showing else None
            if colour is None:
                item.setData(0, Qt.ForegroundRole, None)
            else:
                item.setForeground(0, QBrush(QColor(colour)))
            # The badge is an icon, never text: as text it would restyle the row.
            if showing and item.data(0, _ROLE_KIND) != "section":
                badge = REVIEW_BADGES.get(status, "")
                item.setIcon(0, emoji_icon(badge, self._icon_size()) if badge else QIcon())
            elif item.data(0, _ROLE_KIND) != "section":
                item.setIcon(0, QIcon())
            tip = item.toolTip(0).split("\n\n")[0]
            hint = REVIEW_TOOLTIPS.get(status, "")
            item.setToolTip(0, f"{tip}\n\n{hint}" if hint else tip)
        self._apply_review_filter()

    def _apply_review_filter(self):
        """Hide review-tracked pages that do not match the selected status."""
        if not hasattr(self, "review_filter"):
            return
        wanted = self.review_filter.currentData()
        for key, item in self._items.items():
            status = item.data(0, _ROLE_REVIEW)
            if not status:
                continue
            item.setHidden(wanted not in ("all", None) and status != wanted)

    def _update_review_summary(self):
        """Show the manual-wide review tally in the authoring toolbar."""
        if not hasattr(self, "review_summary_label"):
            return
        if not self.authoring_btn.isChecked():
            self.review_summary_label.setText("")
            return
        report = self.client.review_check()
        summary = report.get("summary")
        if not summary:
            self.review_summary_label.setText("")
            return
        mark = "✅" if report.get("passed") else "⬜"
        self.review_summary_label.setText(f"{mark} Manual: {summary} ")

    # ── external links ──────────────────────────────────────────────

    def _open_documentation(self):
        """Open the ChiSurf documentation in a web browser."""
        webbrowser.open_new(help_url)

    def _open_video_tutorials(self):
        """Open the ChiSurf video tutorials in a web browser."""
        webbrowser.open_new("https://www.peulen.xyz/tutorial/")
