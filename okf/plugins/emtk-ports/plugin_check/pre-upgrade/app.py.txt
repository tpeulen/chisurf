"""Native plugin checker: startup evidence, with explicit pending-port status."""
from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split

from .model import PluginCheckModel


def _caption(text):
    """Fit a table-cell caption; the tooltip/details retain the full value."""
    width = max(0, im.get_content_region_avail()[0])
    if im.calc_text_size(text)[0] <= width:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if im.calc_text_size(text[:middle] + "…")[0] <= width:
            low = middle
        else:
            high = middle - 1
    return text[:low] + "…"


class PluginCheckApp(ImApp):
    window_title = "ChiSurf Plugin Check"

    def __init__(self, model=None):
        self.model = model or PluginCheckModel()
        self.selected = next(iter(self.model.catalog), None)
        self.docks = DockManager(Split("h", 0.65, Region("plugins"), Region("details")))
        self.docks.add_window("plugins", "Plugin startup checks", self.draw_list, dock="plugins")
        self.docks.add_window("details", "Plugin details", self.draw_details, dock="details")
        super().__init__(self.render)

    def export_settings(self) -> dict:
        return {"selected": self.selected}

    def restore_settings(self, settings: dict) -> None:
        selected = settings.get("selected")
        if selected in self.model.catalog:
            self.selected = selected

    def render(self):
        self.model.poll()
        viewport = im.get_main_viewport()
        self.docks.draw((*viewport.pos, *viewport.size))

    def draw_list(self, box):
        im.begin_disabled(self.model.running)
        if im.button("Test all plugins"):
            self.model.start()
        im.set_item_tooltip("Construct and render every declared native plugin in a separate process.")
        im.same_line()
        if im.button("Test safe plugins"):
            self.model.start(safe=True)
        im.set_item_tooltip("Check the first ten plugins using short startup timeouts.")
        if im.button("Refresh"):
            self.model.refresh()
        im.set_item_tooltip("Rescan plugin manifests and clear the displayed startup results.")
        im.same_line()
        if im.button("Clear blacklist"):
            self.model.blacklisted.clear()
            self.model.failures.clear()
        im.set_item_tooltip("Allow plugins blacklisted after repeated failures to be tested again.")
        _, self.model.skip_blacklisted = im.checkbox("Skip blacklisted", self.model.skip_blacklisted)
        im.set_item_tooltip("Skip plugins with five consecutive recorded startup failures.")
        _, self.model.delay = im.drag_float("Delay between plugins [s]", self.model.delay, 0.1, 0, 10)
        im.set_item_tooltip("Pause between startup checks; cancellation remains responsive during the pause.")
        im.end_disabled()
        if self.model.running:
            if im.button("Stop"):
                self.model.stop()
            im.set_item_tooltip("Stop the sweep and terminate the currently tested child process.")
        im.progress_bar(self.model.current / max(self.model.total, 1), overlay=f"{self.model.current}/{self.model.total}")
        im.text_wrapped(self.model.message)
        im.text_disabled("Startup checks do not establish scientific or workflow parity.")
        im.separator()
        if im.begin_table("plugin_results", 5, im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.RESIZABLE):
            for name, weight in zip(("Plugin", "Status", "Source", "Depends on", "Error"), (2.0, 1.0, 0.7, 1.5, 1.5)):
                im.table_setup_column(name, im.TableColumnFlags.WIDTH_STRETCH, weight)
            im.table_headers_row()
            for key, manifest in sorted(self.model.catalog.items()):
                im.push_id(key)
                im.table_next_row()
                im.table_next_column()
                display = manifest.get("display_name") or key
                if im.selectable(f"{_caption(display.split(':')[-1])}##plugin", key == self.selected):
                    self.selected = key
                im.set_item_tooltip(f"{display}\nInspect {key}: metadata, dependencies and full startup errors.")
                result = self.model.results.get(key, {})
                im.table_next_column()
                status = result.get("status", "not checked")
                color = {"pass": (110, 220, 140, 255), "fail": (245, 110, 110, 255),
                         "skipped": (235, 190, 90, 255), "pending": (235, 190, 90, 255)
                         }.get(status, (165, 170, 180, 255))
                im.text_colored(color, status)
                im.table_next_column()
                im.text(manifest.get("source", "builtin"))
                im.table_next_column()
                requires = manifest.get("requires", {})
                optional = manifest.get("optional_requires", {})
                dependencies = ", ".join([*requires, *(f"{name} (optional)" for name in optional)])
                im.text(_caption(dependencies))
                im.set_item_tooltip(dependencies or "No plugin dependencies declared.")
                im.table_next_column()
                error = result.get("error", "")
                im.text(_caption(error.splitlines()[0] if error else ""))
                im.set_item_tooltip(error or "No startup error reported.")
                im.pop_id()
            im.end_table()

    def draw_details(self, box):
        if self.selected not in self.model.catalog:
            im.text("Select a plugin to inspect its details.")
            return
        manifest = self.model.catalog[self.selected]
        im.text(manifest.get("display_name") or self.selected)
        im.text(f"Version: {manifest.get('version', '')}")
        im.text_wrapped(manifest.get("description", ""))
        for kind in ("dependencies", "requires", "optional_requires", "entrypoints"):
            im.separator_text(kind.replace("_", " ").title())
            for name, value in manifest.get(kind, {}).items():
                im.text_wrapped(f"{name}: {value}")
        im.separator_text("Startup result")
        result = self.model.results.get(self.selected, {})
        im.text_wrapped(result.get("error") or result.get("status", "Not checked"))
        if result.get("traceback"):
            im.text_wrapped(result["traceback"])

    def animating(self):
        return self.model.running or not self.model._events.empty() or super().animating()

    def close(self):
        self.model.close()


def make_app():
    from chisurf.emtk.i18n import install

    install()
    return PluginCheckApp()
