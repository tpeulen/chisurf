"""The bare drop-only conversion tool: one drop target, no options, no nag.

Distinct from the ``tttr_to_pto`` drop *guard* (``gui/guard.py``): the guard
asks permission before converting a file dropped on someone else's tool; this
widget *is* the explicit "convert" action a guard would otherwise ask
permission for, for people who already know which direction they want and do
not want to be asked. It is also distinct from the settings-heavy
``tttr/converter`` hub, which transcodes between vendor container formats and
has nothing to do with `.pto`.

Works **both ways**, telling the two apart by what was dropped: a vendor file
(``.ptu``, ``.spc``, ``.ht3``, ...) is packed into a `.pto` beside it; a
`.pto` is unpacked back to the vendor file(s) it embeds. Either way the
original the drop started from is kept -- packing never deletes the vendor
file, and unpacking never touches the container.
"""

from __future__ import annotations

from pathlib import Path

from qtpy import QtWidgets

from chisurf.core.fio import staging
from chisurf.core.fio.pto import SUFFIX as PTO_SUFFIX
from chisurf.core.fio.pto import is_measurement
from chisurf.gui.widgets.tools.chisurf_dock_tool import PathDropListWidget

__all__ = ["TttrToPtoTool"]


class TttrToPtoTool(QtWidgets.QWidget):
    """One drop target: pack a vendor file into `.pto`, or unpack a `.pto` back."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("TTTR ⇄ .pto")

        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Drop a vendor photon file (.ptu, .spc, .ht3, ...) to pack it into "
            "a .pto beside it, or drop a .pto to unpack the original vendor "
            "file(s) back out. Whichever direction you drop, the file you "
            "dropped is kept untouched."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._list = PathDropListWidget(path_filter=self._accepts)
        self._list.setToolTip(
            "Drop a vendor file to pack it, or a .pto to unpack it. There is "
            "no prompt here -- this tool is the explicit action a drop guard "
            "would otherwise ask permission for."
        )
        self._list.pathsDropped.connect(self._on_dropped)
        layout.addWidget(self._list, 1)

    @staticmethod
    def _accepts(path: str) -> bool:
        """Accept a vendor photon file, or an existing `.pto` container."""
        p = Path(path)
        if p.suffix.lower() == PTO_SUFFIX:
            return True
        return p.suffix.lower() in staging.VENDOR_EXTENSIONS

    def _on_dropped(self, paths: list) -> None:
        """Pack or unpack every dropped path, reporting each outcome in place."""
        from chisurf.plugins.core.tttr_to_pto import api

        for path in paths:
            p = Path(path)
            row = self._list.count()
            if p.suffix.lower() == PTO_SUFFIX or is_measurement(p):
                self._list.addItem(f"{p.name} — unpacking…")
                item = self._list.item(row)
                try:
                    recovered = api.extract(path)
                    names = ", ".join(r.name for r in recovered)
                    item.setText(f"{p.name} → {names}")
                except Exception as exc:  # a container with no embedded file, ...
                    item.setText(f"{p.name}: could not unpack ({exc})")
            else:
                self._list.addItem(f"{p.name} — packing…")
                item = self._list.item(row)
                try:
                    target = api.convert(path, keep_original=True)
                    item.setText(f"{p.name} → {target.name}")
                except Exception as exc:  # a locked/unwritable folder, a bad file, ...
                    item.setText(f"{p.name}: could not pack ({exc})")
