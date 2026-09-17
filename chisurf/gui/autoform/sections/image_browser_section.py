"""Reusable ``image_browser`` AutoForm custom section.

A browsable list of named image *entries* (files, molecules, frames, …) beside a
full image canvas — the shared workspace shape used by the TTTR image browser,
the molecule-wise MLE tool and any imaging tool that needs "pick one of many,
show its image".  The canvas is the existing :class:`ImageMapWidget` (colormap,
z-slider, movie playback, markers, ROI, pixel-pick), so a browser inherits all of
it for free.

Declare it in a ``view.json`` as::

    {"type": "custom", "key": "image_browser", "title": "Images",
     "options": {
        "entries_source": "browse_entries", "entry_attr": "current_entry",
        "select_call": "select_entry", "target": "current_image",
        "info_source": "entry_info", "filter": true,
        "colormap": true, "default_colormap": "magma"
     }}

Model contract (all names resolve to attributes/methods on the bound model):

* ``entries_source`` (**required**) — zero-arg method returning the entry list.
  Each entry is either a plain string, or a mapping with ``id`` and optional
  ``label``/``badge``/``rating`` (``badge`` is dim right-hand text such as a size
  or a ★ rating; ``rating`` drives the editable star row).
* ``entry_attr`` — model attribute that receives the current entry ``id``.
* ``selected_ids_attr`` — model attribute that receives the list of selected
  ids; when set the list allows multi-selection.
* ``select_call`` — method called after a pick (``fn(entry_id)`` or ``fn()``).
* ``target`` (**required**) — zero-arg method returning the *current* entry's
  image (2-D ``(y, x)`` or 3-D ``(frame, y, x)``); forwarded to the canvas.
* ``info_source`` — method returning HTML shown in a metadata panel under the
  list.
* ``filter`` — show a search box that narrows the list by label substring.
* ``rating_call`` / ``max_rating`` — method ``fn(entry_id, rating)`` enabling an
  editable star row (0…``max_rating``) acting on the current entry.
* ``note_source`` / ``note_call`` / ``note_placeholder`` — an editable per-entry
  note box: ``note_source()`` returns the current note text, ``note_call(entry_id,
  text)`` persists edits (read-only when only ``note_source`` is given).
* ``on_drop`` — method ``fn(paths)`` called with dropped file paths.
* ``list_width`` — initial width of the list pane (px).

Every remaining option is forwarded verbatim to the inner :class:`ImageMapWidget`
(``colormap``, ``default_colormap``, ``colormap_attr``, ``movie``,
``markers_source``, ``labels_source`` (on-image text overlays), ``roi_source``,
``select_attr``, ``on_pick``, ``channel_source``/``channel_attr``/``channel_call``,
brush options, …).
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.glyphs import Glyphs

from .builtin import ImageMapWidget
from .registry import register_section

logger = logging.getLogger(__name__)

#: Options consumed by the browser shell; everything else goes to the canvas.
_BROWSER_OPTIONS = frozenset(
    {
        "entries_source",
        "entry_attr",
        "selected_ids_attr",
        "select_call",
        "info_source",
        "filter",
        "rating_call",
        "max_rating",
        "on_drop",
        "list_width",
        "note_source",
        "note_call",
        "note_placeholder",
    }
)


def _normalise_entry(entry) -> dict:
    """Coerce an entry (string or mapping) into ``{id, label, badge, rating}``."""
    if isinstance(entry, dict):
        eid = entry.get("id", entry.get("name", entry.get("label")))
        label = str(entry.get("label", entry.get("name", eid)))
        return {
            "id": eid,
            "label": label,
            "badge": entry.get("badge"),
            "rating": entry.get("rating"),
        }
    return {"id": entry, "label": str(entry), "badge": None, "rating": None}


class ImageBrowserWidget(QtWidgets.QWidget):
    """Entry list + :class:`ImageMapWidget` canvas + optional metadata panel."""

    #: marker so :meth:`AutoForm.refresh_plots` re-reads this widget.
    AUTOFORM_REFRESH = True
    #: marker so AutoForm's panel builder gives this widget the spare vertical space
    #: instead of appending a trailing stretch that pins it to its size hint.
    _autoform_expanding = True

    def __init__(self, model, target: str | None = None, **options):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self._model = model
        self._target = target or options.get("target")
        self._entries_source = options.get("entries_source")
        self._entry_attr = options.get("entry_attr")
        self._selected_ids_attr = options.get("selected_ids_attr")
        self._select_call = options.get("select_call")
        self._info_source = options.get("info_source")
        self._rating_call = options.get("rating_call")
        self._max_rating = int(options.get("max_rating", 3))
        self._on_drop = options.get("on_drop")
        self._note_source = options.get("note_source")
        self._note_call = options.get("note_call")
        self._note_placeholder = options.get("note_placeholder", "Note…")
        self._entries: list[dict] = []
        self._current_id = None
        self._committed_id = object()  # sentinel: nothing committed yet
        self._syncing = False

        canvas_opts = {k: v for k, v in options.items() if k not in _BROWSER_OPTIONS}

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        # ── left: filter · list · rating · info ──
        left = QtWidgets.QWidget()
        left_lay = QtWidgets.QVBoxLayout(left)
        left_lay.setContentsMargins(2, 2, 2, 2)
        left_lay.setSpacing(2)

        self._filter_edit = None
        if options.get("filter"):
            self._filter_edit = QtWidgets.QLineEdit()
            self._filter_edit.setPlaceholderText("Filter…")
            self._filter_edit.setClearButtonEnabled(True)
            self._filter_edit.textChanged.connect(self._apply_filter)
            left_lay.addWidget(self._filter_edit)

        self._list = QtWidgets.QListWidget()
        self._list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
            if self._selected_ids_attr
            else QtWidgets.QAbstractItemView.SingleSelection
        )
        self._list.currentItemChanged.connect(self._on_current_changed)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        left_lay.addWidget(self._list, 1)

        self._star_row = None
        self._star_buttons: list[QtWidgets.QToolButton] = []
        if self._rating_call:
            self._star_row = self._build_star_row()
            left_lay.addWidget(self._star_row)

        self._info = None
        if self._info_source:
            self._info = QtWidgets.QTextEdit()
            self._info.setReadOnly(True)
            self._info.setMaximumHeight(110)
            left_lay.addWidget(self._info)

        self._note = None
        if self._note_call or self._note_source:
            self._note = QtWidgets.QPlainTextEdit()
            self._note.setPlaceholderText(self._note_placeholder)
            self._note.setMaximumHeight(80)
            self._note.setReadOnly(not self._note_call)
            self._note.textChanged.connect(self._on_note_changed)
            left_lay.addWidget(self._note)

        splitter.addWidget(left)

        # ── right: the shared image canvas ──
        self._canvas = ImageMapWidget(model, self._target, **canvas_opts)
        splitter.addWidget(self._canvas)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([int(options.get("list_width", 220)), 600])

        if self._on_drop:
            self.setAcceptDrops(True)

        self.refresh()

    # ── star-rating row (edits the current entry) ──
    def _build_star_row(self) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(0)
        lay.addWidget(QtWidgets.QLabel("Rating"))
        for i in range(1, self._max_rating + 1):
            btn = QtWidgets.QToolButton()
            btn.setText(Glyphs.STAR_OFF)
            btn.setAutoRaise(True)
            btn.setToolTip(f"Rate {i}/{self._max_rating}")
            btn.clicked.connect(lambda _checked=False, value=i: self._set_rating(value))
            self._star_buttons.append(btn)
            lay.addWidget(btn)
        clear = QtWidgets.QToolButton()
        clear.setText(Glyphs.CLOSE)
        clear.setAutoRaise(True)
        clear.setToolTip("Clear rating")
        clear.clicked.connect(lambda: self._set_rating(0))
        lay.addWidget(clear)
        lay.addStretch(1)
        return row

    def _set_rating(self, value: int) -> None:
        if self._current_id is None:
            return
        fn = getattr(self._model, self._rating_call, None)
        if callable(fn):
            try:
                fn(self._current_id, int(value))
            except Exception:  # pragma: no cover - model-defined
                logger.debug("rating_call %r failed", self._rating_call, exc_info=True)
        self.refresh()

    def _update_stars(self) -> None:
        if not self._star_buttons:
            return
        rating = 0
        for e in self._entries:
            if e["id"] == self._current_id and e.get("rating"):
                rating = int(e["rating"])
                break
        for i, btn in enumerate(self._star_buttons, start=1):
            btn.setText(Glyphs.STAR_ON if i <= rating else Glyphs.STAR_OFF)

    # ── selection ──
    def _current_selection_ids(self) -> list:
        return [it.data(QtCore.Qt.UserRole) for it in self._list.selectedItems()]

    def _on_current_changed(self, current, _previous) -> None:
        if self._syncing:
            return
        entry_id = current.data(QtCore.Qt.UserRole) if current is not None else None
        self._commit(entry_id)

    def _commit(self, entry_id) -> None:
        """Set the current entry on the model and redraw.

        ``select_call`` fires only when the current entry actually changed.
        """
        self._current_id = entry_id
        if self._entry_attr is not None:
            try:
                setattr(self._model, self._entry_attr, entry_id)
            except Exception:  # pragma: no cover - defensive
                logger.debug("could not set %r", self._entry_attr, exc_info=True)
        if entry_id != self._committed_id:
            self._committed_id = entry_id
            if self._select_call:
                fn = getattr(self._model, self._select_call, None)
                if callable(fn):
                    try:
                        fn(entry_id)
                    except TypeError:
                        fn()
                    except Exception:  # pragma: no cover - model-defined
                        logger.debug("select_call %r failed", self._select_call, exc_info=True)
        self._update_stars()
        self._update_info()
        self._update_note()
        self._canvas.refresh()

    def add_roi(self, **kwargs):
        """Add a region shape to the canvas, returning a chiplot ROI handle.

        Forwarded to the inner :class:`ImageMapWidget` so this browser is also a
        surface :class:`~chisurf.gui.widgets.roi.overlay.RegionOverlay` can draw
        a shared region collection on — a tool whose image lives behind an entry
        list should not need a different overlay from one whose image does not.
        """
        return self._canvas.add_roi(**kwargs)

    def _on_selection_changed(self) -> None:
        if self._syncing or not self._selected_ids_attr:
            return
        try:
            setattr(self._model, self._selected_ids_attr, self._current_selection_ids())
        except Exception:  # pragma: no cover - defensive
            logger.debug("could not set %r", self._selected_ids_attr, exc_info=True)

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    # ── editable note ──
    def _update_note(self) -> None:
        if self._note is None:
            return
        fn = getattr(self._model, self._note_source, None) if self._note_source else None
        try:
            text = fn() if callable(fn) else (fn or "")
        except Exception:  # pragma: no cover - model-defined
            text = ""
        self._note.blockSignals(True)
        self._note.setPlainText(str(text or ""))
        self._note.blockSignals(False)

    def _on_note_changed(self) -> None:
        if self._syncing or not self._note_call or self._current_id is None:
            return
        fn = getattr(self._model, self._note_call, None)
        if callable(fn):
            try:
                fn(self._current_id, self._note.toPlainText())
            except Exception:  # pragma: no cover - model-defined
                logger.debug("note_call %r failed", self._note_call, exc_info=True)

    # ── info panel ──
    def _update_info(self) -> None:
        if self._info is None:
            return
        fn = getattr(self._model, self._info_source, None)
        try:
            html = fn() if callable(fn) else (fn or "")
        except Exception:  # pragma: no cover - model-defined
            html = ""
        self._info.setHtml(str(html or ""))

    # ── AutoForm refresh ──
    def refresh(self) -> None:
        """Reload the entry list from the model and redraw the canvas."""
        fn = getattr(self._model, self._entries_source, None) if self._entries_source else None
        try:
            raw = list(fn()) if callable(fn) else []
        except Exception:  # pragma: no cover - model-defined
            logger.debug("entries_source %r failed", self._entries_source, exc_info=True)
            raw = []
        self._entries = [_normalise_entry(e) for e in raw]

        # Preserve the selection by id across reloads.
        want = self._current_id
        if self._entry_attr is not None:
            model_cur = getattr(self._model, self._entry_attr, None)
            if model_cur is not None:
                want = model_cur

        self._syncing = True
        self._list.clear()
        select_row = 0
        for row, e in enumerate(self._entries):
            text = e["label"]
            if e.get("badge"):
                text = f"{text}    {e['badge']}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, e["id"])
            self._list.addItem(item)
            if e["id"] == want:
                select_row = row
        if self._entries:
            self._list.setCurrentRow(select_row)
        self._syncing = False

        # Commit the (possibly newly-)selected entry to the model + canvas. The
        # setCurrentRow above was suppressed by ``_syncing`` so no signal fired.
        self._commit(self._entries[select_row]["id"] if self._entries else None)

        if self._filter_edit is not None:
            self._apply_filter(self._filter_edit.text())

    # ── drag-drop of files onto the browser ──
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        """Accept drags carrying file URLs when ``on_drop`` is configured."""
        if self._on_drop and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        """Forward dropped file paths to the model's ``on_drop`` handler."""
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if not paths:
            return
        fn = getattr(self._model, self._on_drop, None)
        if callable(fn):
            try:
                fn(paths)
            except Exception:  # pragma: no cover - model-defined
                logger.debug("on_drop %r failed", self._on_drop, exc_info=True)
        self.refresh()


@register_section("image_browser")
def _image_browser_section_factory(model, target: str | None = None, **options):
    """Custom-section factory for the reusable image browser."""
    return ImageBrowserWidget(model, target, **options)


__all__ = ["ImageBrowserWidget"]
