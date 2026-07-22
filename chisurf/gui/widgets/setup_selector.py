"""Compact, reusable detector-setup chooser.

Many tools need to *pick* one of the saved detector setups (they are *edited*
elsewhere, in the Detector Def tool). Historically each rolled its own
``QLabel("Setup:") + QComboBox + reload QToolButton`` plus a summary line — this
widget replaces that copy-paste with one compact control.

Layout is intentionally minimal (one row: combo + reload; an optional muted
summary line below), so it drops cleanly into a form or a dock without stealing
vertical space. The setup name and its detectors are exposed through a small API
and a single :pyattr:`setupChanged` signal.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qtpy import QtCore, QtWidgets

from chisurf.gui.glyphs import Glyphs


def _default_loader(db_path: str | None = None) -> dict:
    """Load the saved detector setups via the canonical wizard loader."""
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import load_detector_setups

    return load_detector_setups(db_path=db_path, skip_migration=True)


class SetupSelector(QtWidgets.QWidget):
    """A compact detector-setup picker: a combo, a reload button, a summary line.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    show_summary : bool, default True
        Show a muted one-line summary of the selected setup's detectors below the
        combo (e.g. ``green, red, yellow``).
    show_reload : bool, default True
        Show the ``🔄`` reload button that re-reads the setups from storage.
    placeholder : str, default ""
        First (empty-name) combo entry, shown when nothing is selected.
    loader : callable, optional
        Zero/one-arg callable returning the ``{"setups": {...}, "last_used": ...}``
        dict. Defaults to the shared ``load_detector_setups``. Injectable for
        tests and RPC-backed callers.
    db_path : str, optional
        Passed to the default loader.
    """

    #: Emitted with the selected setup name (``""`` when cleared) on any change.
    setupChanged = QtCore.Signal(str)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        show_summary: bool = True,
        show_reload: bool = True,
        placeholder: str = "",
        loader: Callable[..., dict] | None = None,
        db_path: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._loader = loader or _default_loader
        self._db_path = db_path
        self._setups: dict[str, Any] = {}

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.combo = QtWidgets.QComboBox()
        self.combo.setToolTip(
            "Detector setup. Setups are created and edited in the Detector Def "
            "tool; here you only pick which one to use."
        )
        self.combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.currentTextChanged.connect(self._on_changed)
        row.addWidget(self.combo, 1)

        self.btn_reload: QtWidgets.QToolButton | None = None
        if show_reload:
            self.btn_reload = QtWidgets.QToolButton()
            self.btn_reload.setText(Glyphs.REFRESH)
            self.btn_reload.setToolTip("Reload the saved detector setups")
            self.btn_reload.clicked.connect(self.refresh)
            row.addWidget(self.btn_reload)
        outer.addLayout(row)

        self._placeholder = placeholder
        self.summary: QtWidgets.QLabel | None = None
        if show_summary:
            self.summary = QtWidgets.QLabel("")
            self.summary.setWordWrap(True)
            self.summary.setStyleSheet("color: palette(mid);")
            outer.addWidget(self.summary)

        self.refresh()

    # -- data -----------------------------------------------------------
    def refresh(self) -> None:
        """Re-read the setups from storage and repopulate, keeping the selection.

        Restores the previously-selected setup when it still exists, otherwise the
        stored ``last_used`` one.
        """
        try:
            data = self._loader(self._db_path) if self._db_path is not None else self._loader()
        except TypeError:
            data = self._loader()
        except Exception:
            data = {}
        data = data if isinstance(data, dict) else {}
        self._setups = data.get("setups", {}) if isinstance(data.get("setups"), dict) else {}
        last_used = data.get("last_used") or data.get("last_used_setup")

        previous = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(self._placeholder)
        for name in sorted(self._setups.keys()):
            self.combo.addItem(str(name))
        target = previous or (str(last_used) if last_used else "")
        if target and self.combo.findText(target) >= 0:
            self.combo.setCurrentText(target)
        self.combo.blockSignals(False)
        self._on_changed(self.combo.currentText())

    # -- selection API --------------------------------------------------
    def current_setup(self) -> str:
        """Return the selected setup name (``""`` when none)."""
        name = self.combo.currentText().strip()
        return name if name and name != self._placeholder else ""

    def current_setup_dict(self) -> dict | None:
        """Return the selected setup's dict (or ``None``)."""
        setup = self._setups.get(self.current_setup())
        return setup if isinstance(setup, dict) else None

    def current_detectors(self) -> dict:
        """Return the selected setup's ``detectors`` mapping (possibly empty)."""
        setup = self.current_setup_dict() or {}
        dets = setup.get("detectors", {})
        return dets if isinstance(dets, dict) else {}

    def detector_names(self) -> list[str]:
        """Return the selected setup's detector names."""
        return [n for n in self.current_detectors() if isinstance(n, str) and n.strip()]

    def set_current(self, name: str) -> None:
        """Select ``name`` if present."""
        if self.combo.findText(name) >= 0:
            self.combo.setCurrentText(name)

    # -- internals ------------------------------------------------------
    def _on_changed(self, _name: str) -> None:
        if self.summary is not None:
            names = self.detector_names()
            self.summary.setText(", ".join(names) if names else "No detectors")
        self.setupChanged.emit(self.current_setup())
