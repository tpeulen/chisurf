"""FCS channel-definition plugin (AutoForm port).

This GUI plugin defines logical FCS correlation channel pairs per *detector
setup*. Detector setups (windows/detectors/TTTR reading) are managed by
:mod:`chisurf.gui.widgets.wizard.tttr_channeldefinition` and stored in
``detector_setups.json``. This plugin adds a small JSON file in the user
settings directory::

    ~/.chisurf/fcs_channel_setups.json

The JSON structure is::

    {
        "version": 1,
        "setups": {
            "<setup_name>": {
                "pairs": [
                    {"name": str, "channel_a": str, "channel_b": str,
                     "kind": str | null, "n_bins": int, "n_casc": int,
                     "make_fine": bool},
                    ...
                ],
                "_is_public": bool
            },
            ...
        },
        "last_used_setup": "<setup_name>" | null
    }

The *channel_a* / *channel_b* names are the logical channel keys constructed
from a detector setup (e.g. ``"prompt_green"``); the burst-wise diffusion plugin
reads this JSON to know which channel pairs to correlate.

The UI is data-driven: the layout lives in ``fcs_channel_preset.view.json`` and
is rendered by :class:`~chisurf.gui.autoform.auto_form.AutoForm` over
:class:`~chisurf.plugins.fcs.fcs_channel_preset.gui.view_model.FCSChannelViewModel`.
The pairs table is the custom ``fcs_channel_pairs`` section registered in
:mod:`chisurf.plugins.fcs.fcs_channel_preset.gui.sections`. This host only wires
the two together and reacts to model events (close / save notifications).
"""

from __future__ import annotations

from qtpy import QtWidgets

from chisurf.core import i18n
from chisurf.gui.autoform.auto_form import AutoForm
from chisurf.gui.glyphs import Glyphs

# Registering the custom pairs section must happen before AutoForm builds.
from . import sections  # noqa: F401
from .view_model import FCSChannelViewModel
from chisurf.gui import dialogs

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:  # pragma: no cover - headless without the GUI helper
    persist_plugin_state = lambda n: lambda c: c  # noqa: E731


# Plugin category/name for the ChiSurf menu.
name = "Setup:FCS Definitions"
icon = Glyphs.ANTENNA


@persist_plugin_state("fcs_channel_preset")
class FCSChannelWidget(QtWidgets.QWidget):
    """Host widget: an :class:`AutoForm` over the channel-definition view-model."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        db_path: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(i18n.tr("FCS Channel Definitions"))
        self.resize(720, 460)

        self.model = FCSChannelViewModel(db_path=db_path)
        self.auto_form = AutoForm(self.model)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.auto_form)

        self.model.add_observer(self._on_model_event)

    # ── model event bridge ───────────────────────────────────────────
    def _on_model_event(self, event: str) -> None:
        if event == "close":
            self.close()
        elif event == "setup_changed":
            # Keep bound form fields (public flag, setup combo) in sync with the
            # model after a programmatic selection change.
            self.auto_form.sync_fields()
        elif event == "saved":
            dialogs.information(
                self,
                i18n.tr("Saved"),
                i18n.tr("Saved the FCS channel pairs for the selected detector setup."),
            )
        elif event == "save_failed":
            dialogs.warning(
                self,
                i18n.tr("Save failed"),
                i18n.tr("Could not save the FCS channel pairs."),
            )
        elif event == "no_setup":
            dialogs.warning(
                self,
                i18n.tr("No setup selected"),
                i18n.tr("Select a detector setup first."),
            )


#: Backwards-compatible alias (historically a dialog).
FCSChannelDialog = FCSChannelWidget


if __name__ == "plugin":  # pragma: no cover
    app = QtWidgets.QApplication.instance()
    parent = None if app is None else app.activeWindow()
    dialog = FCSChannelWidget(parent)
    dialog.show()
