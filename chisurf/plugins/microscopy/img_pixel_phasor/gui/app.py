"""Native emtk phasor-FLIM tool (settings form, maps and phasor plot with its cursors from ``phasor_emtk.view.json``) on the shared pixel shell."""

from __future__ import annotations

from pathlib import Path

from emtk.docking import Region, Split

from ...imaging_emtk.pixel_app import PHOTON_FILE_FILTER, PixelToolApp
from ...imaging_emtk.plane import PlanePanel, PlaneRegions, semicircle
from .model import PhasorModel

HERE = Path(__file__).parent


class PhasorApp(PixelToolApp):
    """Phasor (g, s) of every detector window, with lifetime cursors on the phasor plane."""

    GUI_DIR = HERE
    SPEC = "phasor_emtk.view.json"
    TITLE = "Phasor-FLIM"
    HELP_TITLE = "Phasor-FLIM - Help"
    ROLE = "pixel_phasor"
    LAYOUT = Split("h", 0.32, Region("settings"), Region("views"))
    DIALOGS = {
        **PixelToolApp.DIALOGS,
        "irf": ("Open IRF photon file", "open", PHOTON_FILE_FILTER, "open_irf_path"),
    }

    def __init__(
        self, model: PhasorModel | None = None, coordinator=None, ndx_callback=None, **binding
    ) -> None:
        super().__init__(model or PhasorModel(), coordinator, ndx_callback, **binding)
        m = self.model
        panel = PlanePanel(
            "phasor_plane",
            collection=lambda: m.cursors,
            image=m.phasor_histogram_map,
            extent=m.cursor_extent,
            x_label="g",
            y_label="s",
            on_change=m.notify_cursors,
            overlay=lambda: [semicircle()],
            empty="No phasor yet. Select a photon file and press Run.",
            tooltip="Density of the phasor cloud; drag a cursor's handles to change which pixels it selects.",
        )
        regions = PlaneRegions(
            lambda: m.cursors,
            m.cursor_extent,
            lambda kind: m.request_dialog(kind),
            m.notify_cursors,
        )
        self.add_plane("phasor", panel, regions)
        self.add_plane("cursors", panel, regions)

    def export_settings(self) -> dict:
        state = super().export_settings()
        state["cursors"] = self.model.cursors.to_dict()
        return state

    def restore_settings(self, state: dict) -> None:
        from chisurf.core.roi import RegionCollection

        if isinstance(state, dict) and isinstance(state.get("cursors"), dict) and not self.job.busy:
            try:
                self.model.cursors = RegionCollection.from_dict(state["cursors"])
            except Exception:
                pass
        super().restore_settings(state)


def make_app(coordinator=None, **kwargs) -> PhasorApp:
    """Factory named by the manifest's ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return PhasorApp(coordinator=coordinator, **kwargs)
