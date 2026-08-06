"""Every setting in one filterable table.

ChiMOL has **79 registered settings** and, until this, the only way to reach one
was to know its name and type ``set``. That is a command language pretending to
be an interface: a setting nobody can find is barely more use than a setting
that does not exist, which is the same failure the settings table was built to
prevent one level down.

The design is PyMOL's, from ``modules/pmg_qt/advanced_settings_gui.py`` -- which
is 92 lines and does exactly the right things: a filter box over a two-column
table, booleans as check boxes, everything else editable in place, and the
setting's own description as the tooltip. PyMOL is the reference for the GUI and
the UX, and this is why: the shape is obvious once seen and easy to get subtly
wrong from scratch.

Two things are ChiMOL's own rather than PyMOL's:

* the table is **chitable**, the project's table widget, so the search box, the
  sorting, the row counter and the type-aware editors come from the same place
  as every other table in ChiSurf rather than from a second hand-rolled
  ``QTableView``. This file first added a filter box and a status label of its
  own on top of it, which a screenshot immediately showed as **two search boxes
  and two row counters** stacked above the same table;
* a value is written through :func:`~chimol.settings.set_setting`, which is the
  *same* path the ``set`` command takes -- so the table cannot drift from the
  command, and a setting that is inert from the command line is equally inert
  here. It is a window onto one store, not a second one.
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.chitable import ChiTableWidget, ColumnSpec, RecordSource

from ..settings import SettingValueError, get_setting, iter_settings, set_setting

logger = logging.getLogger(__name__)


class _SettingRow:
    """One setting, as the table sees it.

    A row object rather than a dict so the value is *read back from the config*
    every time the table asks: a setting can be changed by a command, by a
    preset or by another widget while this is open, and a cached copy would show
    the value it had when the window was built.
    """

    def __init__(self, spec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def value(self):
        try:
            return get_setting(self.spec.name)
        except Exception:  # pragma: no cover - a setting whose section went
            return None

    @value.setter
    def value(self, new) -> None:
        set_setting(self.spec.name, new)

    @property
    def description(self) -> str:
        return self.spec.doc


def _get(row: _SettingRow, key: str):
    return getattr(row, key)


def _set(row: _SettingRow, key: str, value) -> bool:
    """Write a setting, and report a rejected value rather than swallowing it."""
    if key != "value":
        return False
    try:
        row.value = value
    except SettingValueError as exc:
        logger.warning("chimol: %s", exc)
        return False
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("chimol: could not set %s: %s", row.name, exc)
        return False
    return True


class SettingsTable(QtWidgets.QWidget):
    """A filterable table of every registered setting.

    Parameters
    ----------
    parent : QtWidgets.QWidget, optional
        Owner window.
    on_changed : callable, optional
        Called after a setting is written, so the viewer can redraw. Nothing
        here knows how to repaint a scene, and it should not.
    """

    def __init__(self, parent=None, *, on_changed=None) -> None:
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("ChiMOL settings")
        self.setMinimumSize(520, 560)
        self._on_changed = on_changed

        self._rows = [_SettingRow(spec) for spec in iter_settings()]
        specs = [
            ColumnSpec(key="name", label="Setting", editable=False, width=200),
            ColumnSpec(key="value", label="Value", editable=True, width=140),
            # The description is the reason the filter is worth having: someone
            # looking for the depth cue does not know it is spelled `fog_start`.
            ColumnSpec(key="description", label="What it does", editable=False),
        ]
        source = RecordSource(self._rows, specs, getter=_get, setter=self._write)

        # chitable brings the search box, the sort, the row counter and the
        # per-type editors; adding any of them here would be a second one.
        self.table = ChiTableWidget(source=source, parent=self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table, 1)

    # ------------------------------------------------------------------ #
    def _write(self, row: _SettingRow, key: str, value) -> bool:
        ok = _set(row, key, value)
        if ok and callable(self._on_changed):
            try:
                self._on_changed()
            except Exception:  # pragma: no cover - a viewer that went away
                logger.debug("chimol: settings table could not refresh", exc_info=True)
        return ok

    def filter_settings(self, text: str) -> int:
        """Show only the settings matching *text*; return how many survive.

        A thin pass-through to chitable's own search, kept because it is the
        useful handle for a test and for a caller that wants to open the window
        already narrowed -- ``show_settings_table(..., filter="cartoon")``.

        The **description** is searched as well as the name, which is the whole
        point of showing it: someone looking for the depth cue does not know it
        is spelled ``fog_start``.
        """
        self.table.set_search_text(str(text))
        return int(self.table.visible_row_count())


def show_settings_table(parent=None, *, on_changed=None, filter: str = "") -> SettingsTable:
    """Open the settings table and return it."""
    widget = SettingsTable(parent, on_changed=on_changed)
    if filter:
        widget.filter_settings(filter)
    widget.show()
    widget.raise_()
    return widget


__all__ = ["SettingsTable", "show_settings_table"]
