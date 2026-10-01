"""Native emtk Trace Browser, in stages: the **Setup** page (card T1).

The Qt tool opens on a two-page workspace: page 0 is the detector setup (the
``DetectorWizardPage`` plus a *Continue* button), page 1 the trace browser.  This
module draws page 0 with the shared emtk setup editor
(:class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget`); *Continue* hands
the editor's result to :meth:`.model.TraceBrowserModel.accept_setup` (which derives
the selected channels exactly as the Qt tool does) and switches the page.  The
browser page is not ported yet: it is a labelled placeholder that shows only what
the model holds (the accepted setup), no data of its own.

All state is in :class:`~.model.TraceBrowserModel`; this module imports no Qt.
"""

from __future__ import annotations

import json
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region

from chisurf.core import setup_channel_definition as definition
from chisurf.core.fio import setup_store as store
from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import ChannelDefinitionWidget

from .model import TraceBrowserModel


def _plain(value: Any) -> Any:
    """Convert numpy scalars/arrays to JSON types (``json.dumps`` ``default=``)."""
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


class TraceBrowserApp(ImApp):
    """Trace Browser: setup page (done) and browser page (placeholder until card T2).

    Parameters
    ----------
    model : TraceBrowserModel, optional
        The state; a fresh one by default.
    setups_file : str or Path, optional
        Detector-setups JSON file offered on the setup page; ``None`` is the user's
        canonical file, which is what the Qt setup page reads.
    """

    def __init__(self, model: TraceBrowserModel | None = None, setups_file: Any = None) -> None:
        self.model = model or TraceBrowserModel()
        self.setups_file = str(setups_file) if setups_file else None
        self.editor: ChannelDefinitionWidget | None = None
        self.item_rects: dict[str, tuple] = {}
        self._new_editor(None)
        self._load_saved_setups(select_last=True)
        self.setup_docks = DockManager(Region("setup"), name="trace_browser_setup")
        self.setup_docks.add_window(
            "setup", "Setup definition", self.draw_setup, dock="setup", closable=False
        )
        self.browser_docks = DockManager(Region("browser"), name="trace_browser_browser")
        self.browser_docks.add_window(
            "browser", "Trace browser", self.draw_browser, dock="browser", closable=False
        )
        super().__init__(self.render, continuous=True)

    # -- the shared setup editor ------------------------------------------------
    def _new_editor(self, settings: dict | None) -> None:
        """Replace the setup editor by a fresh one holding *settings*."""
        if self.editor is not None:
            self.editor.close()
        model = ChannelDefinition(settings, file_path=self.setups_file)
        self.editor = ChannelDefinitionWidget(model=model)

    def _load_saved_setups(self, select_last: bool) -> None:
        """Offer the saved setups and, if asked, select the last used one.

        Reads the store the Qt setup page reads (the MMFDB, falling back to the
        setups JSON file, with the same one-time import of an old JSON file), so the
        drop-down lists the saved setups and the page starts on the last used one.
        With no saved setup the page starts empty.
        """
        assert self.editor is not None
        self.editor.model.refresh_setups()
        name = store.load_setups(self.setups_file, definition.CONFIG).get("last_used")
        if select_last and name in self.editor.model.setups:
            self.editor.select_setup(name)

    # -- actions ---------------------------------------------------------------
    def continue_to_browser(self) -> None:
        """Accept the editor's setup and show the browser page (the Qt *Continue*)."""
        assert self.editor is not None
        self.model.accept_setup(self.editor.model.get_settings())

    def back_to_setup(self) -> None:
        """Return to the setup page (the Qt *Select setup* button)."""
        self.model.back_to_setup()

    # -- one frame -------------------------------------------------------------
    def render(self) -> None:
        width, height = im.get_main_viewport().size
        box = (0.0, 0.0, float(width), float(height))
        (self.setup_docks if self.model.page == "setup" else self.browser_docks).draw(box)
        assert self.editor is not None
        self.editor.draw_dialogs(box)

    def draw_setup(self, box: Any) -> None:
        """Page 0: *Continue*, then the shared setup editor."""
        if im.button("Continue"):
            self.continue_to_browser()
        im.set_item_tooltip("Accept detector setup and open trace browser")
        self.item_rects["continue"] = im.get_item_rect()
        im.separator()
        assert self.editor is not None
        self.editor.draw()

    def draw_browser(self, box: Any) -> None:
        """Page 1 placeholder: back button, a notice, and the accepted setup."""
        if im.button("← Select setup"):
            self.back_to_setup()
        im.set_item_tooltip("Go back to the detector setup page")
        self.item_rects["back"] = im.get_item_rect()
        im.separator()
        im.text_wrapped(
            "The trace browser stage (folder, file table, ratings, trace plot, export) is "
            "not ported to emtk yet. Use Select setup to return to the setup."
        )
        im.separator()
        model = self.model
        name = (model.setup_settings or {}).get("setup_name") or "(unsaved setup)"
        im.text(f"Accepted setup: {name}")
        channels = model.selected_channels
        im.text(
            "Selected channels: " + (", ".join(map(str, channels)) if channels else "auto-detect")
        )
        im.text(f"File type: {model.setup_filetype or 'Auto'}")

    # -- persistence -----------------------------------------------------------
    def export_settings(self) -> dict:
        """What the setup page remembers: the setups file, the setup and its name."""
        assert self.editor is not None
        setup = json.loads(json.dumps(self.editor.model.get_settings(), default=_plain))
        return {
            "setups_file": self.setups_file,
            "setup_name": self.editor.model.current_name,
            "setup": setup,
        }

    def restore_settings(self, state: dict) -> None:
        """Restore the setups file and the working setup written by :meth:`export_settings`."""
        state = state or {}
        self.setups_file = str(state["setups_file"]) if state.get("setups_file") else None
        setup = state.get("setup")
        self._new_editor(setup if isinstance(setup, dict) else None)
        self._load_saved_setups(select_last=not isinstance(setup, dict))

    def close(self) -> None:
        """Stop the setup editor's reader thread."""
        if self.editor is not None:
            self.editor.close()


def make_app() -> TraceBrowserApp:
    """Factory for the (later) manifest ``entrypoints.emtk``."""
    return TraceBrowserApp()
