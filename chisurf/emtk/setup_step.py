"""The declared setup step shared by native tool hubs."""

from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.plugins.emtk_layout import window_size


class SetupStepApp(ImApp):
    """Host the existing detector editor through an AutoForm custom section."""

    def __init__(self, model, on_changed=None, *, autoload=True):
        self.page = ChannelDefinitionWidget(model=model, on_changed=on_changed, host_app=self)
        self.model = model
        self.item_rects = self.page.item_rects
        spec = load_view_spec(str(Path(__file__).with_suffix(".view.json")))
        self.sections = spec["sections"]
        self.window_size = window_size(spec, (1100, 720))
        self.form = FormState()
        self.form.custom["channel_definition"] = self._draw_editor
        self.docks = DockManager(Region("setup"), name="shared_setup")
        self.docks.add_window(
            "setup", tr("Detector setup"), self._draw_window, dock="setup", closable=False
        )
        self.autoload = autoload
        super().__init__(gui=self._render, continuous=False)

    def _draw_editor(self, section, model, state, width):
        """Bind the declared custom section to the same editor used by standalone tools."""
        self.page.draw()

    def _draw_window(self, box=None):
        """Render the setup declaration inside its single dock."""
        draw_sections(self.sections, self, self.form)

    def _render(self):
        """Poll the editor and draw its dock and existing floating windows."""
        if self.autoload:
            self.autoload = False
            self.page.toolbar.reload_async(open_last=False)
        self.page.toolbar.poll()
        self.page.poll()
        frame = (0.0, 0.0, *im.get_main_viewport().size)
        self.docks.draw(frame)
        self.page.draw_dialogs(frame)

    def animating(self):
        """Keep drawing while the saved setups are read in the background."""
        return super().animating() or self.page.toolbar.loading

    def export_settings(self):
        """Persist page geometry/state; the hub owns the shared definition."""
        return self.page.export_state()

    def restore_settings(self, state):
        """Restore only page state, without replacing the hub's definition."""
        self.page.restore_state(state)

    def files_dropped(self, paths):
        """Read setup/measurement drops through the canonical detector editor."""
        return self.page.files_dropped(paths)

    on_files_dropped = files_dropped

    def close(self):
        """Release the editor's jobs and existing child dialogs."""
        self.page.close()
