"""HelpWidget — main GUI for the Help plugin with toolbar and emoji buttons."""

from __future__ import annotations

import getpass
import logging
import pathlib
import re
import webbrowser
from typing import Optional

from qtpy.QtCore import Qt, QUrl
from qtpy.QtGui import QImage, QTextDocument
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
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
from chisurf.gui.glyphs import Glyphs
from chisurf.plugins.core.help.api import review
from chisurf.plugins.core.help.gui.client import HelpClient
from chisurf.gui import dialogs

logger = logging.getLogger(__name__)

#: Badge shown next to a page for each review status.
REVIEW_BADGES = {
    review.STATUS_REVIEWED: "✅",
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
    review.STATUS_UNREVIEWED: (
        "Not checked by a human. Largely machine-drafted; blocks release."
    ),
}

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


class HelpTextBrowser(QTextBrowser):
    """Custom text browser that handles local and remote resource loading."""

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
    - Tree navigation of documentation files
    - Full-text search across all docs
    - In-app Markdown editing and saving
    - Quick links to online docs and video tutorials

    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{Glyphs.BOOK} ChiSurf Help")
        self.setMinimumSize(800, 500)
        self.docs_index = {}
        self.current_path = None
        self.client = HelpClient()
        self._setup_central_widget()
        self._setup_toolbar()
        self.populate_docs()

    # ── central widget ─────────────────────────────────────────────

    def _setup_central_widget(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title = QLabel(f"{Glyphs.BOOK} ChiSurf Documentation and Help Resources")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        header.addWidget(title)
        header.addStretch()
        self.review_summary_label = QLabel("")
        self.review_summary_label.setStyleSheet("color: #888888; font-size: 9pt;")
        self.review_summary_label.setToolTip(
            "Human-review status of the user manual. Unreviewed or stale pages "
            "block a release."
        )
        header.addWidget(self.review_summary_label)
        layout.addLayout(header)

        # Splitter: tree | content
        splitter = QSplitter(Qt.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(False)
        self.tree.setHeaderLabel("Documents")
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(16)
        self.tree.itemClicked.connect(self._on_item_clicked)
        splitter.addWidget(self.tree)

        self.viewer = HelpTextBrowser()
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        self.viewer.anchorClicked.connect(self._on_anchor_clicked)
        self.viewer.setStyleSheet("QTextBrowser { padding: 8px; }")

        self.editor = QPlainTextEdit()
        self.editor.setVisible(False)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(4)

        self.title_label = QLabel(f"{Glyphs.FILE} Select a document")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: #888888; font-size: 8pt;")

        self.review_label = QLabel("")
        self.review_label.setWordWrap(True)
        self.review_label.setVisible(False)

        right_layout.addWidget(self.title_label)
        right_layout.addWidget(self.path_label)
        right_layout.addWidget(self.review_label)
        right_layout.addWidget(self.viewer, 1)
        right_layout.addWidget(self.editor, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

    # ── toolbar ─────────────────────────────────────────────────────

    def _setup_toolbar(self):
        toolbar = QToolBar("Help Tools")
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())
        toolbar.setStyleSheet(
            "QToolBar { spacing: 4px; }"
            "QToolButton { font-size: 11pt; padding: 4px 8px; }"
        )
        self.addToolBar(toolbar)

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

        # Edit
        self.edit_btn = toolbar.addAction(f"{Glyphs.EDIT}  Edit")
        self.edit_btn.setCheckable(True)
        self.edit_btn.setEnabled(False)
        self.edit_btn.toggled.connect(self._on_edit_toggled)

        # Save
        self.save_btn = toolbar.addAction(f"{Glyphs.SAVE}  Save")
        self.save_btn.setEnabled(False)
        self.save_btn.triggered.connect(self._save_current_document)

        toolbar.addSeparator()

        # Open Documentation
        doc_action = toolbar.addAction(f"{Glyphs.BOOK}  Open Docs")
        doc_action.triggered.connect(self._open_documentation)

        # Video Tutorials
        vid_action = toolbar.addAction("🎬  Video Tutorials")
        vid_action.triggered.connect(self._open_video_tutorials)

        toolbar.addSeparator()

        # Review sign-off
        self.review_btn = toolbar.addAction("✅  Mark reviewed")
        self.review_btn.setCheckable(True)
        self.review_btn.setEnabled(False)
        self.review_btn.setToolTip(
            "Record that a human has checked this manual page.\n"
            "Editing the page afterwards makes the sign-off stale automatically."
        )
        self.review_btn.toggled.connect(self._on_review_toggled)

        review_filter_label = QLabel("Show:")
        self.review_filter = QComboBox()
        self.review_filter.addItem("All pages", "all")
        self.review_filter.addItem("⬜ Unreviewed", review.STATUS_UNREVIEWED)
        self.review_filter.addItem("⚠️ Stale", review.STATUS_STALE)
        self.review_filter.addItem("✅ Reviewed", review.STATUS_REVIEWED)
        self.review_filter.setToolTip(
            "Filter the user manual by human-review status."
        )
        self.review_filter.currentIndexChanged.connect(
            lambda _: self._apply_review_filter()
        )
        toolbar.addWidget(review_filter_label)
        toolbar.addWidget(self.review_filter)

        toolbar.addSeparator()

        filter_label = QLabel(f"{Glyphs.SEARCH} Filter:")
        self.filter_line_edit = QLineEdit()
        self.filter_line_edit.setPlaceholderText("Type to filter documents...")
        self.filter_line_edit.setMaximumWidth(260)
        self.filter_line_edit.textChanged.connect(self._on_filter_text_changed)
        toolbar.addWidget(filter_label)
        toolbar.addWidget(self.filter_line_edit)

        toolbar.addSeparator()

        # Close
        close_action = toolbar.addAction(f"{Glyphs.CLOSE}  Close")
        close_action.triggered.connect(self.hide)

    # ── document discovery ──────────────────────────────────────────

    def populate_docs(self):
        """Populate the documentation tree."""
        self.tree.clear()
        self.docs_index = {}
        manual_root = QTreeWidgetItem(self.tree, ["📘 User manual"])
        docs_root = QTreeWidgetItem(self.tree, ["📄 Documentation"])
        core_root = QTreeWidgetItem(self.tree, ["📗 Core"])
        plugins_root = QTreeWidgetItem(self.tree, ["📙 Plugins"])
        self._build_manual_docs(manual_root)
        self._build_project_docs(docs_root)
        self._build_core_docs(core_root)
        self._build_plugin_docs(plugins_root)
        self._update_review_summary()
        self._apply_review_filter()

    def _build_manual_docs(self, parent_item):
        """Build the user-manual branch, badged with review status.

        The manual is reStructuredText and is the part under human-review
        gating, so it is discovered through the shared API rather than a local
        glob and each page carries its sign-off badge.
        """
        for entry in self._manual_entries():
            path = pathlib.Path(entry["path"])
            badge = REVIEW_BADGES.get(entry.get("review_status", ""), "")
            label = entry.get("title") or path.name
            item = QTreeWidgetItem(parent_item, [f"{badge} {label}".strip()])
            item.setData(0, Qt.UserRole, str(path))
            item.setData(0, Qt.UserRole + 1, entry.get("review_status", ""))
            tip = REVIEW_TOOLTIPS.get(entry.get("review_status", ""), "")
            if tip:
                item.setToolTip(0, f"{path.name}\n{tip}")
            self._index_document_item(item, path)

    def _build_project_docs(self, parent_item):
        """Build the branch for project documentation outside the manual."""
        base = pathlib.Path(cs.__file__).resolve().parent
        docs_dir = base.parent / "docs"
        manual_dir = docs_dir / "manual"
        if not docs_dir.exists():
            return
        for path in sorted(docs_dir.rglob("*.md")):
            if _is_within(path, manual_dir):
                continue
            try:
                rel = path.relative_to(docs_dir)
            except ValueError:
                rel = path.name
            title = self._extract_markdown_title(path)
            label = title if title else str(rel)
            item = QTreeWidgetItem(parent_item, [label])
            item.setData(0, Qt.UserRole, str(path))
            self._index_document_item(item, path)

    def _manual_entries(self):
        """Return the user-manual documents with review status attached."""
        try:
            result = self.client.list_docs()
            entries = (result or {}).get("entries", [])
            manual = [e for e in entries if e.get("category") == "User manual"]
            if manual:
                return sorted(manual, key=lambda e: e.get("file_name", ""))
        except Exception:
            pass
        # Offline fallback: read the tree directly.
        from chisurf.plugins.core.help.api.io import discover_docs

        try:
            info = discover_docs()
        except Exception:
            return []
        return [
            {
                "path": e.path,
                "title": e.title,
                "file_name": e.file_name,
                "review_status": e.review_status,
            }
            for e in info.entries
            if e.category == "User manual"
        ]

    def _build_core_docs(self, parent_item):
        """Build the branch for project-level documentation outside ``docs/``.

        The allow-listed roots come from the API layer so the tree and the
        document index cannot drift apart.
        """
        from chisurf.plugins.core.help.api.io import core_doc_paths

        root = pathlib.Path(cs.__file__).resolve().parent.parent
        for path in core_doc_paths(root):
            rel = path.relative_to(root)
            title = self._extract_markdown_title(path)
            label = title if title else str(rel)
            item = QTreeWidgetItem(parent_item, [label])
            item.setData(0, Qt.UserRole, str(path))
            self._index_document_item(item, path)

    def _build_plugin_docs(self, parent_item):
        plugin_settings = cs.core.settings.cs_settings.get('plugins', {})
        disabled_plugins = plugin_settings.get('disabled_plugins', [])
        hide_disabled_plugins = plugin_settings.get('hide_disabled_plugins', True)
        plugin_order = plugin_settings.get('plugin_order', {})
        experimental_mode = cs.core.settings.cs_settings.get('enable_experimental', False)

        try:
            plugin_infos = list(cs.plugins.iter_plugins())
        except Exception:
            plugin_infos = []

        module_order_pairs = []

        for info in plugin_infos:
            plugin_name = info.get('plugin_name') or info.get('module_name')
            module_name = info.get('module_name') or ''
            if not plugin_name:
                continue

            clean_name = plugin_name.split(":")[-1].strip() if ":" in plugin_name else plugin_name

            is_disabled = (
                plugin_name in disabled_plugins
                or module_name in disabled_plugins
                or clean_name in disabled_plugins
            )

            if is_disabled and hide_disabled_plugins and not experimental_mode:
                continue

            order = plugin_order.get(plugin_name, 0)
            module_order_pairs.append((order, plugin_name, info))

        module_order_pairs.sort(key=lambda x: (x[0], x[1]))

        for _order, plugin_name, info in module_order_pairs:
            plugin_dir = pathlib.Path(info.get('package_dir')).resolve()
            markdown_files = sorted(plugin_dir.rglob("*.md"))
            if not markdown_files:
                continue

            readme_path = None
            for p in markdown_files:
                if p.name.lower() in {"readme.md", "readme"}:
                    readme_path = p
                    break
            if readme_path is not None:
                readme_title = self._extract_markdown_title(readme_path)
            else:
                readme_title = None

            if len(markdown_files) == 1:
                md_path = markdown_files[0]
                doc_title = self._extract_markdown_title(md_path)
                if doc_title:
                    label = doc_title
                elif readme_path is not None and md_path == readme_path and readme_title:
                    label = readme_title
                else:
                    if ":" in plugin_name:
                        clean_name = plugin_name.split(":")[-1].strip()
                    else:
                        clean_name = plugin_name
                    label = clean_name or plugin_dir.name
                    if md_path.name.lower() not in {"readme.md", "readme"}:
                        label = f"{label} ({md_path.name})"
                item = QTreeWidgetItem(parent_item, [label])
                item.setData(0, Qt.UserRole, str(md_path))
                self._index_document_item(item, md_path)
            else:
                if ":" in plugin_name:
                    clean_name = plugin_name.split(":")[-1].strip()
                else:
                    clean_name = plugin_name
                plugin_label = readme_title or clean_name or plugin_dir.name
                plugin_item = QTreeWidgetItem(parent_item, [plugin_label])
                for md_path in markdown_files:
                    rel = md_path.relative_to(plugin_dir)
                    doc_title = self._extract_markdown_title(md_path)
                    file_label = doc_title if doc_title else str(rel)
                    file_item = QTreeWidgetItem(plugin_item, [file_label])
                    file_item.setData(0, Qt.UserRole, str(md_path))
                    self._index_document_item(file_item, md_path)

    # ── indexing & search ───────────────────────────────────────────

    def _extract_markdown_title(self, path):
        if path is None or not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            m = re.match(r"^(#{1,6})\s+(.*)", stripped)
            if not m:
                continue
            heading = m.group(2)
            heading = re.sub(r"\{\s*#[-\w]+\s*\}\s*$", "", heading).strip()
            if heading:
                return heading
        return None

    def _index_document_item(self, item, path):
        key = str(path)
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""
        lower_text = text.lower()
        headings = []
        first_heading = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            m = re.match(r"^(#{1,6})\s+(.*)", stripped)
            if not m:
                continue
            heading = m.group(2)
            heading = re.sub(r"\{\s*#[-\w]+\s*\}\s*$", "", heading).strip()
            if not heading:
                continue
            headings.append(heading)
            if first_heading is None:
                first_heading = heading
        headings_lc = "\n".join(h.lower() for h in headings) if headings else ""
        title = first_heading.lower() if first_heading is not None else None
        label = item.text(0).lower()
        file_name = path.name.lower()
        self.docs_index[key] = {
            "item": item,
            "path": path,
            "label": label,
            "file_name": file_name,
            "title": title,
            "headings": headings_lc,
            "text": lower_text,
        }

    def _find_first_leaf(self, parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, Qt.UserRole):
                return child
            result = self._find_first_leaf(child)
            if result is not None:
                return result
        return None

    def _on_filter_text_changed(self, text):
        text = text.strip().lower()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            self._apply_filter(child, text)
        self.tree.expandAll()

    def _apply_filter(self, item, text):
        if not text:
            item.setHidden(False)
            for i in range(item.childCount()):
                self._apply_filter(item.child(i), text)
            return True
        label_match = text in item.text(0).lower()
        meta_match = False
        path = item.data(0, Qt.UserRole)
        if path:
            info = self.docs_index.get(str(path))
            if info is not None:
                title = info.get("title") or ""
                if text in title:
                    meta_match = True
                elif text in info.get("file_name", ""):
                    meta_match = True
                elif text in info.get("headings", ""):
                    meta_match = True
                elif text in info.get("text", ""):
                    meta_match = True
        matches_self = label_match or meta_match
        child_matches = False
        for i in range(item.childCount()):
            if self._apply_filter(item.child(i), text):
                child_matches = True
        visible = matches_self or child_matches
        item.setHidden(not visible)
        return visible

    # ── document navigation ─────────────────────────────────────────

    def _on_item_clicked(self, item, column):
        path = item.data(0, Qt.UserRole)
        if not path:
            self._find_first_leaf(item)
            return
        file_path = pathlib.Path(path)
        # Through navigate(), so picking a page in the tree is part of the trail
        # Back walks -- a reader who clicks a cross-reference and then Back
        # expects to land where they were, whichever way they got there.
        self.navigate(file_path)

    def _reset_history(self):
        """Give this window its own history (a class-level list would be shared)."""
        self._history: list = []
        self._history_index: int = -1

    def navigate(self, file_path: pathlib.Path, anchor: Optional[str] = None):
        """Open a page **and record it in the history**.

        Every route into a document that a *reader* takes goes through here --
        the tree, a cross-reference, another tool's help link. Only the Back and
        Forward buttons call :meth:`_open_document_path` directly, so replaying
        history cannot append to it and trap the reader in a loop.
        """
        if not hasattr(self, "_history"):
            self._reset_history()
        path = pathlib.Path(file_path)
        if not path.exists():
            return
        entry = (path, anchor or "")
        if not self._history or self._history[self._history_index] != entry:
            # A new branch discards whatever was ahead, as a browser does.
            del self._history[self._history_index + 1:]
            self._history.append(entry)
            self._history_index = len(self._history) - 1
        self._open_document_path(path, anchor)
        self._update_history_buttons()

    def go_back(self):
        """Show the previous page in the history."""
        if not hasattr(self, "_history") or self._history_index <= 0:
            return
        self._history_index -= 1
        path, anchor = self._history[self._history_index]
        self._open_document_path(path, anchor or None)
        self._update_history_buttons()

    def go_forward(self):
        """Show the next page in the history."""
        if not hasattr(self, "_history") or self._history_index + 1 >= len(self._history):
            return
        self._history_index += 1
        path, anchor = self._history[self._history_index]
        self._open_document_path(path, anchor or None)
        self._update_history_buttons()

    def _update_history_buttons(self):
        """Enable Back/Forward according to where we are in the history."""
        if not hasattr(self, "_history"):
            self._reset_history()
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
        self.title_label.setText(file_path.name)
        self.path_label.setText(str(file_path))
        self.edit_btn.setEnabled(True)
        self._refresh_review_state(file_path)
        # Images are referenced relative to the document (``_images/…`` in the
        # manual, ``figures/…`` in the guides). A base URL alone does not make
        # QTextBrowser resolve them, so give it an explicit search path.
        try:
            self.viewer.setSearchPaths([str(file_path.parent)])
        except Exception:
            pass
        result = self.client.read_doc(str(file_path))
        if result is None:
            self.viewer.setPlainText(f"Could not read {file_path}")
            return
        text = result.get("content", "")
        if self.edit_btn.isChecked():
            # The *editor* shows the source as it is on disk -- rewriting the
            # roles there would save the rewrite back into the file.
            self.editor.setPlainText(text)
            self.editor.show()
            self.viewer.hide()
            self.save_btn.setEnabled(True)
        else:
            # MyST cross-reference roles are rewritten to Markdown links for
            # display only, so `{ref}`concept-x`` -- which a Markdown viewer
            # otherwise renders as literal text -- becomes something to click.
            from chisurf.gui.widgets.tools.doc_links import expand_roles

            shown = expand_roles(text, file_path.parent)
            html = result.get("html")
            if shown != text:
                try:
                    from chisurf.plugins.core.help.api.markdown import render_markdown

                    html = render_markdown(shown)
                except Exception:
                    logger.debug("could not re-render with expanded roles", exc_info=True)
                    html = None
            self._set_viewer_html(html, shown, file_path)
            self.viewer.show()
            self.editor.hide()
            self.save_btn.setEnabled(False)
            if anchor:
                try:
                    self.viewer.scrollToAnchor(anchor)
                except Exception:
                    pass

    def _on_anchor_clicked(self, url):
        """Follow a link in the page being read.

        The three cases, in order: an in-page anchor scrolls; a web address or a
        DOI opens in the system browser; anything else is treated as a **cross
        reference to another document** and resolved -- relative to the page
        being read first, then against the docs tree -- so the ordinary
        ``[text](other_page.md)`` that the sources are written with actually
        goes somewhere. Previously only a ``file://`` URL was followed, which is
        not what a Markdown link produces, so cross-references were dead.
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

            target = pathlib.Path(url.toLocalFile()) if url.isLocalFile() else None
            if target is None:
                base = self.current_path.parent if self.current_path else None
                target = resolve_document(url.path() or url.toString(), base)
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

        if checked:
            result = self.client.read_doc(str(self.current_path))
            if result is None:
                dialogs.error(
                    self, "Error", f"Could not read {self.current_path}"
                )
                self.edit_btn.setChecked(False)
                return
            text = result.get("content", "")
            self.editor.setPlainText(text)
            self.editor.show()
            self.viewer.hide()
            self.save_btn.setEnabled(True)
        else:
            result = self.client.read_doc(str(self.current_path))
            if result is None:
                self.viewer.setPlainText(f"Could not read {self.current_path}")
                self.viewer.show()
                self.editor.hide()
                self.save_btn.setEnabled(False)
                return
            text = result.get("content", "")
            self._set_viewer_html(result.get("html"), text, self.current_path)
            self.viewer.show()
            self.editor.hide()
            self.save_btn.setEnabled(False)

    def _save_current_document(self):
        if self.current_path is None:
            return
        text = self.editor.toPlainText()
        ok = self.client.save_doc(str(self.current_path), text)
        if not ok:
            dialogs.error(
                self, "Error", f"Could not save {self.current_path}"
            )
            return
        if not self.edit_btn.isChecked():
            result = self.client.read_doc(str(self.current_path))
            if result is None:
                self.viewer.setPlainText(text)
                return
            self._set_viewer_html(result.get("html"), text, self.current_path)
        # Saving changes the content hash, so a signed-off page becomes stale.
        self._refresh_review_state(self.current_path)
        self._refresh_tree_badges()

    # ── human review ────────────────────────────────────────────────

    def _set_viewer_html(
        self, html: Optional[str], text: str, file_path: pathlib.Path
    ):
        """Show *html* for *file_path*, resolving and scaling its images."""
        if html is None:
            self.viewer.setPlainText(text)
            return
        try:
            self.viewer.setSearchPaths([str(file_path.parent)])
        except Exception:
            pass
        try:
            width = self.viewer.viewport().width() - 24
            if width <= 0:
                width = 880
            html = _constrain_image_widths(html, file_path.parent, width)
        except Exception:
            pass
        try:
            self.viewer.setHtml(html, QUrl.fromLocalFile(str(file_path)))
        except Exception:
            self.viewer.setHtml(html)

    # ── human review ────────────────────────────────────────────────

    def _refresh_review_state(self, file_path: Optional[pathlib.Path]):
        """Update the review banner and the sign-off button for *file_path*."""
        if file_path is None:
            self.review_label.setVisible(False)
            self.review_btn.setEnabled(False)
            return

        info = self.client.review_status(str(file_path))
        tracked = bool(info.get("tracked"))
        status = info.get("status", "")

        self.review_btn.blockSignals(True)
        self.review_btn.setEnabled(tracked)
        self.review_btn.setChecked(tracked and status == review.STATUS_REVIEWED)
        self.review_btn.blockSignals(False)

        if not tracked:
            self.review_label.setVisible(False)
            return

        badge = REVIEW_BADGES.get(status, "")
        tip = REVIEW_TOOLTIPS.get(status, "")
        who = ""
        if status == review.STATUS_REVIEWED and info.get("reviewer"):
            who = f" — {info['reviewer']}, {info.get('date', '')}"
        colours = {
            review.STATUS_REVIEWED: ("#1b5e20", "#e8f5e9"),
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
        """Record or clear the sign-off for the current page."""
        if self.current_path is None:
            return
        try:
            reviewer = getpass.getuser()
        except Exception:
            reviewer = ""
        status = review.STATUS_REVIEWED if checked else review.STATUS_UNREVIEWED
        result = self.client.set_review_status(
            str(self.current_path), status, reviewer
        )
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
        """Re-read review status and update the manual branch badges."""
        statuses = {
            e["path"]: e.get("review_status", "") for e in self._manual_entries()
        }
        root = self.tree.topLevelItem(0)
        if root is None:
            return
        for i in range(root.childCount()):
            item = root.child(i)
            path = item.data(0, Qt.UserRole)
            if path not in statuses:
                continue
            status = statuses[path]
            label = item.text(0)
            for badge in REVIEW_BADGES.values():
                label = label.replace(badge, "").strip()
            item.setText(0, f"{REVIEW_BADGES.get(status, '')} {label}".strip())
            item.setData(0, Qt.UserRole + 1, status)
            tip = REVIEW_TOOLTIPS.get(status, "")
            if tip:
                item.setToolTip(0, f"{pathlib.Path(path).name}\n{tip}")
        self._apply_review_filter()

    def _apply_review_filter(self):
        """Hide manual pages that do not match the selected review status."""
        if not hasattr(self, "review_filter"):
            return
        wanted = self.review_filter.currentData()
        root = self.tree.topLevelItem(0)
        if root is None:
            return
        for i in range(root.childCount()):
            item = root.child(i)
            status = item.data(0, Qt.UserRole + 1)
            item.setHidden(wanted not in ("all", None) and status != wanted)

    def _update_review_summary(self):
        """Show the manual-wide review tally in the header."""
        if not hasattr(self, "review_summary_label"):
            return
        report = self.client.review_check()
        summary = report.get("summary")
        if not summary:
            self.review_summary_label.setText("")
            return
        mark = "✅" if report.get("passed") else "⬜"
        self.review_summary_label.setText(f"{mark} Manual: {summary}")

    # ── external links ──────────────────────────────────────────────

    def _open_documentation(self):
        """Open the ChiSurf documentation in a web browser."""
        webbrowser.open_new(help_url)

    def _open_video_tutorials(self):
        """Open the ChiSurf video tutorials in a web browser."""
        webbrowser.open_new("https://www.peulen.xyz/tutorial/")
