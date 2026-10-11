"""Explicit tour pages reveal controls without executing the awaited action."""

from emtk import im
from emtk.app import ImApp
from emtk.testing import Driver

from chisurf.emtk.tool_hub import ToolHubApp


class ExampleApp(ImApp):
    """A real child button whose action count proves no automatic pressing."""

    def __init__(self):
        self.item_rects = {}
        self.loads = 0
        super().__init__(self.render)

    def render(self):
        im.begin("example", (0, 0, *im.get_main_viewport().size))
        if im.button("Load example"):
            self.loads += 1
        self.item_rects["load_example"] = im.get_item_rect()
        im.end()


def test_explicit_page_reveals_real_target_without_pressing():
    """An awaited child action can route its page while keeping its wait intact."""
    child = ExampleApp()
    other = ExampleApp()
    hub = ToolHubApp(
        "Example",
        [
            {"name": "Files", "role": "files", "factory": lambda: child},
            {"name": "Compute", "role": "compute", "factory": lambda: other},
        ],
    )
    try:
        hub.select("compute")
        hub._tour_step(1, {"page": "files", "target": {"name": "load_example"}, "await": True})
        Driver(hub, size=(1100, 720)).frame(2)
        assert hub.selected == "files"
        assert hub._target_rect("load_example") is not None
        assert child.loads == other.loads == 0
    finally:
        hub.close()
