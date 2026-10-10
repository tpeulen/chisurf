"""Qt widgets that only *host* an emtk app (the Qt shell and AutoForm embed sections need a QWidget).

The apps are the plugins' emtk twins; nothing here draws. A Qt surface that embeds a plugin
(the unified Settings hub, the first-run wizard's ``embed`` section) names one of these classes
instead of a plugin-side Qt tool.
"""

from __future__ import annotations

import importlib

from qtpy import QtWidgets


class EmtkEmbed(QtWidgets.QWidget):
    """A QWidget that shows the emtk app built by ``factory`` and forwards the app's lifetime.

    Parameters
    ----------
    factory : str
        ``"pkg.module:function"`` returning the emtk app.
    title : str, optional
        The window title.
    parent : QtWidgets.QWidget, optional
        The Qt parent.
    """

    FACTORY = ""
    TITLE = ""

    def __init__(self, factory: str = "", title: str = "", parent=None) -> None:
        super().__init__(parent)
        from emtk.qt_host import ControlHost

        path = factory or self.FACTORY
        module_name, _, attr = path.partition(":")
        make = getattr(importlib.import_module(module_name), attr)
        self.app = make()
        self.host = ControlHost(self.app)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)
        self.setWindowTitle(title or self.TITLE)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Let the app save its state before the host goes."""
        close = getattr(self.app, "close", None)
        if callable(close):
            close()
        super().closeEvent(event)


class FCSChannelEmbed(EmtkEmbed):
    """The FCS channel-pair definitions editor (``fcs/fcs_channel_preset``)."""

    FACTORY = "chisurf.plugins.fcs.fcs_channel_preset.gui.app:create_app"
    TITLE = "FCS Channel Definitions"


class AnisotropyEmbed(EmtkEmbed):
    """The time-resolved anisotropy workflow (``fluorescence_decay/tr_anisotropy``)."""

    FACTORY = "chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app:make_app"
    TITLE = "Anisotropy"


__all__ = ["AnisotropyEmbed", "EmtkEmbed", "FCSChannelEmbed"]
