"""Core plugin for switching the active MMFDB user."""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Setup:Switch User"


def show_switch_user(parent=None) -> None:
    """Open the ChiSurf login dialog to switch the active MMFDB user.

    Parameters
    ----------
    parent : QtWidgets.QWidget, optional
        Parent widget for the modal dialog.
    """
    from chisurf.gui import LoginDialog

    dialog = LoginDialog(parent=parent)
    dialog.exec()


def __getattr__(attribute):
    """Load the legacy Qt widget only when a Qt host requests it."""
    if attribute == "SwitchUserWidget":
        from qtpy import QtWidgets

        class SwitchUserWidget(QtWidgets.QWidget):
            def showEvent(self, event):
                super().showEvent(event)
                show_switch_user(parent=self)
                self.close()

        return SwitchUserWidget
    raise AttributeError(attribute)


if __name__ == "plugin":
    show_switch_user(globals().get("window"))


__all__ = ["SwitchUserWidget", "name", "show_switch_user"]
