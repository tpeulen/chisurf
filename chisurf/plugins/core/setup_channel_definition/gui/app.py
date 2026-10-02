"""Native emtk Setup:Channel Definition tool.

One window with the page of the Qt tool: the shared editor
:class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget` (Setup row, TTTR Reading routine, PIE Windows,
Detectors, LUT handling, Optical Setup) under a thin strip with the host's Guide and Help buttons. The editor,
its Setup row (:class:`~chisurf.emtk.channel_setup_bar.SetupToolbar`), its tables and its floating windows are the
shared widget's; this app hosts it, opens the last used setup when it starts, remembers which sections are open and
adds the plugin's Help window and guided tour. Nothing here imports Qt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region

from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import LATEST, default_settings

HERE = Path(__file__).parent
#: The window title: the plugin's display name.
TITLE = "Setup: Channel Definition"


class SetupChannelDefinitionApp(ImApp):
    """Detector channels, PIE windows, reading routine, LUTs and optical setup of an instrument."""

    def __init__(
        self,
        settings: dict | None = None,
        model: ChannelDefinition | None = None,
        on_changed: Any = None,
        file_path: str | None = None,
        db: Any = None,
        autoload: bool = True,
        open_last_used: bool | None = None,
    ) -> None:
        fresh = settings is None and model is None
        if model is None:
            model = ChannelDefinition(
                default_settings() if settings is None else settings, file_path=file_path, db=db
            )
        self._on_changed = on_changed
        self.page = ChannelDefinitionWidget(
            model=model, on_changed=self._model_changed
        )
        self.model = self.page.model
        #: Rectangles of the named controls (tests, guided tours, embedding hosts): the page's and this app's.
        self.item_rects: dict[str, tuple] = self.page.item_rects
        self.help_window = EmTkHelpWindow(title="Setup: Channel Definition - Help", resource=HERE / "help.md", owner=self)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.page.item_rects.get(key),
        )
        self.page.on_used = self.tour.notify_used
        self.docks = DockManager(Region("setup"), name="setup_channel_definition")
        self.docks.add_window("setup", TITLE, self._draw_window, dock="setup", closable=False)
        #: The Qt tool lists the saved setups when it opens and opens the last used one; so does this one, on its
        #: first frame (the last used one only when it was not given a definition to show).
        self.autoload = autoload
        self.open_last_used = fresh if open_last_used is None else open_last_used
        super().__init__(gui=self._render, continuous=True)

    # ------------------------------------------------------------------ model
    def _model_changed(self, settings: dict) -> None:
        if callable(self._on_changed):
            self._on_changed(settings)

    # ------------------------------------------------------------------ frame
    def _render(self) -> None:
        if self.autoload:
            self.autoload = False
            self.toolbar.reload(open_last=self.open_last_used)
        vp = im.get_main_viewport()
        box = (float(vp.pos[0]), float(vp.pos[1]), float(vp.size[0]), float(vp.size[1]))
        self.docks.draw(box)
        self.page.draw_dialogs(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    @property
    def toolbar(self):
        """The state of the page's Setup row (Save, Rename, Delete, Public, Calibration)."""
        return self.page.toolbar

    def _draw_window(self, box: Any = None) -> None:
        self._draw_strip()
        self.page.draw()

    def _draw_strip(self) -> None:
        """The host's Guide and Help buttons, at the right above the page (as the Qt settings window has them)."""
        width = self._width("Guide") + self._width("Help") + im.get_style().item_spacing[0]
        im.dummy(max(im.get_content_region_avail()[0] - width - im.get_style().item_spacing[0], 0.0), 1.0)
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        self._item("guide", "Walk through choosing, editing and saving a setup.")
        im.same_line()
        if im.button("Help"):
            self.help_window.show()
        self._item("help", "Explain the page: setups, the reading routine, PIE windows, detectors, units of micro-time ranges and LUTs.")

    def _item(self, name: str, tooltip: str) -> None:
        """Tooltip and tour rectangle for the control just drawn."""
        im.set_item_tooltip(tooltip)
        self.item_rects[name] = im.get_item_rect()

    @staticmethod
    def _width(label: str) -> float:
        return im.calc_text_size(label)[0] + 18.0

    def _draw_prompt(self, box: tuple) -> None:
        """The name prompt and confirmations of the Setup row (drawn by the page; kept for hosts that call it)."""
        self.page.draw_prompt(box)

    # ------------------------------------------------------------ the old API
    def get_settings(self) -> dict:
        """The complete working definition (windows, detectors, reading, LUTs, optical setup)."""
        return self.model.get_settings()

    def files_dropped(self, paths) -> bool:
        """Files dropped on the window (see :meth:`ChannelDefinitionWidget.files_dropped`)."""
        return self.page.files_dropped(paths)

    on_files_dropped = files_dropped

    def load_data_into_tables(self, data: dict) -> None:
        """Replace the working definition by *data*, keeping the stores and the change callback."""
        self.page.load_definition(data)

    # ------------------------------------------------------------ persistence
    def export_settings(self) -> dict:
        """What is remembered: the working definition, the setups file and which sections are open."""
        return {
            "channel_definition": self.get_settings(),
            "page": self.page.export_state(),
            "setups_file": str(self.model.file_path) if self.model.file_path else None,
        }

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.file_path = settings.get("setups_file") or None
        if isinstance(settings.get("channel_definition"), dict):
            self.load_data_into_tables(settings["channel_definition"])
        self.page.restore_state(settings.get("page"))
        self.toolbar.reload()

    def close(self) -> None:
        """Stop a running read."""
        self.page.close()


def make_app(**kwargs: Any) -> SetupChannelDefinitionApp:
    """Build the tool (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return SetupChannelDefinitionApp(**kwargs)


#: The factory's earlier name, kept for callers that still use it.
create_app = make_app

__all__ = ["SetupChannelDefinitionApp", "LATEST", "make_app", "create_app"]
