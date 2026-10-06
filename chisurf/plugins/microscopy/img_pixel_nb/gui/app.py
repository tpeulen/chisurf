"""Native emtk Number & Brightness tool (settings, maps, parameter plane with gates from ``nb_emtk.view.json``) on the shared pixel shell."""

from __future__ import annotations

from pathlib import Path

from emtk.docking import Region, Split

from ...imaging_emtk.pixel_app import PixelToolApp
from ...imaging_emtk.plane import PlanePanel, PlaneRegions
from .model import NBModel
from .view_model import PLANE_AXES

HERE = Path(__file__).parent


class NBApp(PixelToolApp):
    """Apparent and molecular brightness and number of every detector window, with gates on the parameter plane and cross N&B."""

    GUI_DIR = HERE
    SPEC = "nb_emtk.view.json"
    TITLE = "Number & Brightness"
    HELP_TITLE = "Number & Brightness - Help"
    ROLE = "pixel_nb"
    LAYOUT = Split("h", 0.34, Region("settings"), Region("views"))
    OUTCOMES = {**PixelToolApp.OUTCOMES, "demo": "demo"}

    def __init__(
        self, model: NBModel | None = None, coordinator=None, ndx_callback=None, **binding
    ) -> None:
        super().__init__(model or NBModel(), coordinator, ndx_callback, **binding)
        m = self.model
        panel = PlanePanel(
            "nb_plane",
            collection=lambda: m.gates,
            image=m.plane_histogram,
            extent=m.plane_extent,
            x_label=lambda: PLANE_AXES.get(m.plane_x, m.plane_x),
            y_label=lambda: PLANE_AXES.get(m.plane_y, m.plane_y),
            on_change=m.notify_gates,
            empty="No parameter plane yet. Select a photon file and press Run.",
            tooltip="Histogram of the displayed window on the chosen axes; drag a gate's handles to select a population.",
        )
        regions = PlaneRegions(
            lambda: m.gates, m.plane_extent, lambda kind: m.request_dialog(kind), m.notify_gates
        )
        self.add_plane("gates", panel, regions)

    def export_settings(self) -> dict:
        state = super().export_settings()
        state["gates"] = self.model.gates.to_dict()
        return state

    def restore_settings(self, state: dict) -> None:
        from chisurf.core.roi import RegionCollection

        if isinstance(state, dict) and isinstance(state.get("gates"), dict) and not self.job.busy:
            try:
                self.model.gates = RegionCollection.from_dict(state["gates"])
            except Exception:
                pass
        super().restore_settings(state)


def make_app(coordinator=None, **kwargs) -> NBApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return NBApp(coordinator=coordinator, **kwargs)
