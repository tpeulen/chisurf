"""AutoForm ``memory_editor`` section — a hex view over RAM or VRAM.

Declared in a ``.view.json`` as::

    {"type": "custom", "key": "memory_editor", "target": "raw_block",
     "title": "Bytes", "options": {"height": 260, "columns": 16}}

The bound attribute may be:

* ``bytes`` / ``bytearray`` / ``memoryview`` / a NumPy array -- shown directly;
* a :class:`~chimol.cmtk.memory_editor.MemorySource`;
* a **list** of either, or a callable returning one -- which grows a picker
  above the dump, so one section can show a whole set of buffers.

Leaving ``target`` off probes the running renderer instead
(:mod:`chimol.core.memory_probe`) and lists what it holds in host memory
and on the device, largest first, with the totals in the caption. That is the
"where did the memory go" view, and it is the reason this section exists: the
question used to be answerable only by adding a print statement and re-running,
and for a GPU buffer not even then.

Why it shows a result and does not set one
------------------------------------------
It is deliberately absent from the documentation generator's
``CUSTOM_PARAM_KEYS``, alongside ``image`` and the info box: a hex dump is a
*view*. Editing is possible when the underlying block is writable and the
section was given ``read_only: false``, but that is a debugging affordance, not
a parameter the user of a fitting model sets.

Options
-------
``columns`` : int, default 16
``height`` : int, default 260
``read_only`` : bool, default ``True``
``ascii`` : bool, default ``True``
``preview`` : bool, default ``True``
    Show the decoded-value footer.
``minimum_bytes`` : int, default 1024
    Probe mode only: blocks smaller than this are not listed.
``handle`` : str, optional
    Publish the widget on the model under this attribute name.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


class MemoryEditorWidget(QtWidgets.QWidget):
    """A source picker, a hex dump, and a caption saying what was found."""

    #: AutoForm.refresh_plots() calls refresh() on sections that ask for it.
    AUTOFORM_REFRESH = True

    def __init__(self, model, target: str = "", **options) -> None:
        super().__init__()
        self._model = model
        self._target = str(target or "")
        self._options = dict(options)
        self._sources: list = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.picker = QtWidgets.QComboBox()
        self.picker.currentIndexChanged.connect(self._on_pick)
        layout.addWidget(self.picker)

        self.editor = None
        self._host = None
        try:
            from chimol.cmtk import memory_editor as me
            from chimol.cmtk.qt_host import ControlHost

            self.editor = me.MemoryEditor(
                None,
                columns=int(self._options.get("columns", 16)),
                read_only=bool(self._options.get("read_only", True)),
            )
            self.editor.show_ascii = bool(self._options.get("ascii", True))
            self.editor.show_data_preview = bool(self._options.get("preview", True))
            self._host = ControlHost(self.editor)
            self._host.setMinimumHeight(int(self._options.get("height", 260)))
            layout.addWidget(self._host, 1)
        except ImportError as problem:
            logger.warning("memory_editor unavailable (%s)", problem)
            layout.addWidget(QtWidgets.QLabel("hex view unavailable (chimol not importable)"))

        self.caption = QtWidgets.QLabel("")
        self.caption.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.caption)

        handle = self._options.get("handle")
        if handle:
            setattr(model, str(handle), self)
        self.refresh()

    # -- sources -------------------------------------------------------- #
    def _gather(self) -> tuple[list, str]:
        """Return ``(sources, caption)`` for whatever this section is bound to."""
        from chimol.cmtk import memory_editor as me

        if not self._target:
            return self._probe()

        value = getattr(self._model, self._target, None)
        if callable(value):
            value = value()
        if value is None:
            return [], "nothing bound"

        items = value if isinstance(value, (list, tuple)) else [value]
        sources = []
        for index, item in enumerate(items):
            if isinstance(item, me.MemorySource):
                sources.append(item)
                continue
            try:
                sources.append(
                    me.BufferSource(item, name=f"{self._target}[{index}]"
                                    if len(items) > 1 else self._target)
                )
            except TypeError:
                logger.debug("memory_editor: %r is not a buffer", type(item))
        total = sum(one.size() for one in sources)
        return sources, f"{len(sources)} block(s), {_human(total)}"

    def _probe(self) -> tuple[list, str]:
        """Probe the running renderer for its RAM and VRAM blocks."""
        try:
            from chimol.core import memory_probe
        except ImportError as problem:
            return [], f"probe unavailable ({problem})"

        root = getattr(self._model, "viewer", None) or getattr(self._model, "view", None)
        if root is None:
            root = self._model
        device = getattr(root, "device", None)
        found = memory_probe.report(
            root, device, minimum=int(self._options.get("minimum_bytes", 1024))
        )
        return list(found.sources), found.summary()

    def refresh(self) -> None:
        """Re-gather the sources and rebuild the picker.

        The current selection is kept by *name* rather than by index: a probe
        run a second time finds the same blocks in a different order as often
        as not, and an index would silently switch which buffer is on screen.
        """
        if self.editor is None:
            return
        wanted = self.picker.currentText()
        self._sources, caption = self._gather()
        self.caption.setText(caption)

        self.picker.blockSignals(True)
        self.picker.clear()
        for one in self._sources:
            kind = getattr(one, "kind", "")
            detail = getattr(one, "detail", "")
            label = f"{one.name}  ({_human(one.size())}"
            label += f", {kind}" if kind else ""
            label += f", {detail})" if detail else ")"
            self.picker.addItem(label)
        self.picker.setVisible(len(self._sources) > 1)
        index = max(self.picker.findText(wanted), 0)
        self.picker.setCurrentIndex(index)
        self.picker.blockSignals(False)
        self._show(index)

    def _on_pick(self, index: int) -> None:
        """The user chose a different block."""
        self._show(index)

    def _show(self, index: int) -> None:
        """Point the hex view at one of the gathered sources."""
        if self.editor is None:
            return
        source = self._sources[index] if 0 <= index < len(self._sources) else None
        self.editor.set_source(source)
        error = getattr(source, "error", "")
        if error:
            self.caption.setText(f"{self.caption.text()} — read failed: {error}")
        if self._host is not None:
            self._host.update()

    # -- public surface ------------------------------------------------- #
    def goto(self, address: int, highlight_to: int | None = None) -> None:
        """Scroll to an address and highlight from it."""
        if self.editor is not None:
            self.editor.goto(int(address), highlight_to)
            if self._host is not None:
                self._host.update()


def _human(count: int) -> str:
    """Bytes as a short human-readable string."""
    size = float(count)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


@register_section("memory_editor")
def _memory_editor_section_factory(model, target: str = "", **options):
    """Custom-section factory for the hex view over RAM and VRAM."""
    return MemoryEditorWidget(model, target, **options)


__all__ = ["MemoryEditorWidget"]
