"""Compatibility shim for the console's old name.

The console used to be ``QIPythonWidget``, a ``qtconsole.RichJupyterWidget``
driving an in-process Jupyter kernel. It is now
:class:`chisurf.gui.chinsole.Chinsole`, which needs no Jupyter, no IPython and
no ZeroMQ.

This module exists so the rename is not also a rewrite of every call site. New
code should import from :mod:`chisurf.gui.chinsole` directly; this shim is a
migration aid and will be removed once the last caller is gone.
"""

from __future__ import annotations

from qtpy import QtGui

from chisurf.gui.chinsole import Chinsole, ConsoleConfig, ConsoleRole
from chisurf.gui.chinsole.settings import editor_font

__all__ = ["QIPythonWidget", "make_editor_font_from_settings"]


def make_editor_font_from_settings() -> QtGui.QFont:
    """Return the console font from the ChiSurf settings.

    Returns
    -------
    qtpy.QtGui.QFont
    """
    return editor_font()


class QIPythonWidget(Chinsole):
    """The ChiSurf console, under its historic name.

    Parameters
    ----------
    history_widget : QtWidgets.QPlainTextEdit, optional
        Mirrors every executed cell.
    recording : bool, optional
        Start the macro recorder immediately.
    """

    def __init__(
            self,
            history_widget=None,
            recording: bool = False,
            *args,
            **kwargs,
    ) -> None:
        config = kwargs.pop("config", None) or ConsoleConfig(
            role=ConsoleRole.INTERACTIVE,
            init_source=None,
        )
        super().__init__(config)
        self.history_widget = history_widget
        if recording:
            self.start_recording()
