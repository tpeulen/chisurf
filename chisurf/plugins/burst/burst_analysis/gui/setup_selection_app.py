"""Step 0 of the burst workflow, *Setup Selection*: the shared detector-setup editor, drawn with emtk.

The step is :class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget` -- the same one-page editor the
Setup: Channel Definition tool, the FCS channel presets and the burst tools embed (setup row with Save / Rename /
Delete, TTTR reading routine, PIE windows, detectors with the polarisation switch, LUT handling, optical setup, the
micro-time decay preview) -- under a strip with this step's Guide and Help. It opens the last used setup when it
starts. The workflow reads the chosen setup through :meth:`BurstSetupSelectionApp.selected_setup_name` /
:meth:`selected_setup_data`, and is told of every change by ``on_changed``.

This replaced a 2178-line hand-written duplicate of that editor (kept for review under
``okf/plugins/emtk-ports/burst_analysis/pre-upgrade/``). Nothing here imports Qt.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region

from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

HERE = Path(__file__).resolve().parent

#: Kept for the Qt host, which paints its background before the first frame.
WINDOW_BG = (30, 32, 38, 255)

TITLE = "Detector setup"


class BurstSetupSelectionApp(ImApp):
    """The detector setup of a burst workflow: the shared editor plus Guide / Help / Proceed.

    Parameters
    ----------
    settings : dict, optional
        A working definition to start from (default: the last used setup of the store).
    model : ChannelDefinition, optional
        The definition and its store (default: built from *settings*).
    on_changed : callable, optional
        Called with the complete definition after every selection or edit.
    on_proceed : callable, optional
        Called by the *Proceed* button (the workflow hub moves on); its label and tooltip are
        :attr:`PROCEED_LABEL` / :attr:`PROCEED_TIP`, so a hub with other step names says where it goes.
    autoload : bool
        List the stored setups (and open the last used one) on the first frame.
    """

    PROCEED_LABEL = "Proceed to Data Selection"
    PROCEED_TIP = "Go on to 1. Data Selection with this setup."

    def __init__(
        self,
        settings: dict | None = None,
        *,
        model: ChannelDefinition | None = None,
        on_changed: Callable[[dict], None] | None = None,
        on_proceed: Callable[[], None] | None = None,
        autoload: bool = True,
    ) -> None:
        self._on_changed = on_changed
        self.on_proceed = on_proceed
        self.page = ChannelDefinitionWidget(settings, model=model, on_changed=self._changed)
        self.model = self.page.model
        self.item_rects: dict[str, tuple] = self.page.item_rects
        self.help_window = EmTkHelpWindow(
            title="Setup Selection - Help",
            resource=HERE / "setup_selection_help.md",
            owner=self,
            size=(660.0, 480.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "setup_selection_guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key),
        )
        self.page.on_used = self.tour.notify_used
        self.docks = DockManager(Region("setup"), name="burst_setup_selection")
        self.docks.add_window("setup", TITLE, self._draw_window, dock="setup", closable=False)
        self.autoload = autoload
        self.open_last_used = settings is None and model is None
        super().__init__(gui=self._render, continuous=True)

    # -- the workflow's view of the step ------------------------------------------------------------------- #
    def _changed(self, settings: dict) -> None:
        if callable(self._on_changed):
            self._on_changed(settings)

    def selected_setup_name(self) -> str:
        """Name of the setup on the page ('' for an unsaved working definition)."""
        return str(self.model.current_name or "")

    def selected_setup_data(self) -> dict[str, Any]:
        """The complete working definition (windows, detectors, reading, LUTs, optical setup)."""
        return self.model.get_settings()

    def get_settings(self) -> dict[str, Any]:
        """The working definition, as the Qt detector page's ``get_settings`` returned it."""
        return self.selected_setup_data()

    def refresh_setups(self) -> list[str]:
        """Re-read the store; the stored setup names."""
        return self.model.refresh_setups()

    def select_setup(self, name: str) -> bool:
        """Show the stored setup *name*; ``False`` when the store has none of that name."""
        if not name or name == self.selected_setup_name():
            return bool(name)
        try:
            self.page.select_setup(name)
        except ValueError:
            return False
        self.autoload = False  # a setup chosen by the workflow wins over "open the last used one"
        return True

    def load_data_into_tables(self, settings: dict) -> None:
        """Show the workflow's setup here: select it by name, else show its definition as a working copy."""
        settings = settings or {}
        name = str(settings.get("setup_name") or "")
        if name and self.select_setup(name):
            return
        if settings.get("detectors") or settings.get("windows"):
            self.page.load_definition(copy.deepcopy(settings))
            self.autoload = False

    # -- frame --------------------------------------------------------------------------------------------- #
    def _render(self) -> None:
        if self.autoload:
            self.autoload = False
            self.page.toolbar.reload(open_last=self.open_last_used)
        self.page.poll()
        vp = im.get_main_viewport()
        box = (float(vp.pos[0]), float(vp.pos[1]), float(vp.size[0]), float(vp.size[1]))
        self.docks.draw(box)
        self.page.draw_dialogs(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _draw_window(self, box: Any = None) -> None:
        self._draw_strip()
        self.page.draw()

    def _draw_strip(self) -> None:
        if im.button("Guide##setup_step"):
            self.tour.start()
        self._item("guide", "Walk through choosing, checking and saving the detector setup of this workflow.")
        im.same_line()
        if im.button("Help##setup_step"):
            self.help_window.show()
        self._item("help", "What the detector setup decides for every later step.")
        im.same_line()
        ready = bool(self.model.data.get("detectors"))
        im.begin_disabled(not ready or not callable(self.on_proceed))
        if im.button(self.PROCEED_LABEL):
            self.tour.notify_used("proceed")
            self.on_proceed()
        im.end_disabled()
        self._item(
            "proceed",
            self.PROCEED_TIP if ready else "Define at least one detector first.",
        )
        im.same_line()
        name = self.selected_setup_name()
        im.text_disabled(f"Setup: {name}" if name else "Unsaved working setup")

    def _item(self, name: str, tooltip: str) -> None:
        im.set_item_tooltip(tooltip)
        self.item_rects[name] = im.get_item_rect()

    # -- host input / persistence -------------------------------------------------------------------------- #
    def files_dropped(self, paths) -> bool:
        return bool(self.page.files_dropped(paths))

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    def export_settings(self) -> dict[str, Any]:
        return {
            "setup_name": self.selected_setup_name(),
            "channel_definition": self.model.get_settings(),
            "page": self.page.export_state(),
        }

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        self.page.restore_state(state.get("page"))
        if not self.select_setup(str(state.get("setup_name") or "")) and isinstance(
            state.get("channel_definition"), dict
        ):
            self.page.load_definition(state["channel_definition"])
            self.autoload = False

    def close(self) -> None:
        self.page.close()


def make_app(**kwargs: Any) -> BurstSetupSelectionApp:
    """The setup step alone."""
    from chisurf.emtk.i18n import install

    install()
    return BurstSetupSelectionApp(**kwargs)


__all__ = ["BurstSetupSelectionApp", "TITLE", "WINDOW_BG", "make_app"]
