"""The Excitation Windows tool (emtk): pick a measurement and, optionally, a setup; see the windows.

The panel is the shared :class:`chisurf.emtk.excitation_windows.WindowsReview` (its AutoForm spec
``chisurf/emtk/excitation_windows.view.json``); this app adds the setup to check, the Guide and
Help buttons, and what *Use detected windows* does here: the setup with the detected windows is
written to the settings folder and added to the Datasets workspace as a ``setup`` row, where the
setup editor, Record and the burst analyses pick it up. Nothing imports Qt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.excitation_windows import WindowsReview
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, action_caption

HERE = Path(__file__).parent
TITLE = "Setup: Excitation Windows"


class ExcitationWindowsApp(ImApp):
    """Detect PIE / µs-ALEX excitation windows and check a setup's windows against them."""

    window_size = (820, 820)

    def __init__(self, setup: dict | None = None, workspace: bool = True) -> None:
        self.review = WindowsReview(setup, on_accept=self._accepted, workspace=workspace)
        self.setup_address = ""
        self.setup_text = tr("No setup: the windows are only detected (pick a setup to check it).")
        self.saved_text = ""
        self.setup_input = None
        if workspace:
            try:
                from chisurf.plugins.tttr.workspace_io import NamedWorkspaceInput

                self.setup_input = NamedWorkspaceInput("excitation_windows", "setup", self,
                                                       height=40)
            except Exception:  # noqa: BLE001 - a bare host: no setup list
                self.setup_input = None
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.help_window = EmTkHelpWindow(
            title="Setup: Excitation Windows - Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json", owner=self, wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key),
        )
        self.review.form.on_used = self.tour.notify_used
        self.docks = DockManager(Region("windows"), name="excitation_windows")
        self.docks.add_window("windows", TITLE, self._draw_window, dock="windows",
                              closable=False)
        super().__init__(gui=self._render, continuous=True)

    # -- inputs ---------------------------------------------------------------------------------
    def take_setup(self, address: str) -> None:
        """Check the windows of the setup at *address* (a workspace ``setup`` row or a file)."""
        from chisurf.plugins.core.excitation_windows.api import load_setup

        self.setup_address = str(address)
        self.review.set_setup(load_setup(self.setup_address))
        self.setup_text = tr("Setup: {name}").format(name=Path(self.setup_address).name)

    def _accepted(self, windows: dict, detection, check=None) -> None:
        from chisurf.core.settings import get_path
        from chisurf.plugins.core.excitation_windows.api import apply_to_setup
        from chisurf.plugins.tttr.workspace_io import add_setup

        setup = self.review.setup or {}
        if not setup.get("detectors"):
            groups = {"green": [0], "red": [1]}
            if detection.donor_detectors and detection.acceptor_detectors:
                def chs(names):
                    return sorted({int(n.split()[-1]) for n in names if n.startswith("ch ")})

                groups = {"green": chs(detection.donor_detectors),
                          "red": chs(detection.acceptor_detectors)}
            setup = {**setup, "detectors": {k: {"chs": v} for k, v in groups.items() if v}}
        fixed = apply_to_setup(setup, {
            "proposal": windows, "detection": detection.to_dict(),
            "proposal_gates": check.proposal_gates if check is not None else {},
        })
        stem = Path(self.setup_address or self.review.measurement or "measurement").stem
        path = get_path("settings") / "excitation_windows" / f"{stem}.windows.setup.json"
        address = add_setup(path, fixed)
        self.saved_text = tr("Saved the setup with the detected windows: {name}").format(
            name=Path(address).name
        )
        self.review.done = ""  # the tool stays open

    # -- frame --------------------------------------------------------------------------------------
    def _render(self) -> None:
        vp = im.get_main_viewport()
        box = (float(vp.pos[0]), float(vp.pos[1]), float(vp.size[0]), float(vp.size[1]))
        self.docks.draw(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _draw_window(self, box: Any = None) -> None:
        self._draw_strip()
        if self.setup_input is not None:
            im.text(tr("Setup to check"))
            draw_form(self.setup_input.spec, self.setup_input, self.setup_input.form)
            rect = self.setup_input.form.rects.get("workspace_input_rows")
            if rect:
                self.item_rects["setup_input"] = rect
        im.text_wrapped(self.setup_text)
        self.review.draw()
        self.item_rects.update(self.review.form.rects)
        if self.saved_text:
            im.text_wrapped(self.saved_text)

    def _draw_strip(self) -> None:
        width = sum(im.calc_text_size(action_caption(k))[0] + 18.0 for k in ("guide", "help"))
        im.dummy((max(im.get_content_region_avail()[0] - width - 8.0, 0.0), 1.0))
        im.same_line()
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()

    # -- persistence -------------------------------------------------------------------------------
    def export_settings(self) -> dict:
        """Nothing to remember between sessions but the last setup picked."""
        return {"setup": self.setup_address}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        if (settings or {}).get("setup"):
            try:
                self.take_setup(settings["setup"])
            except Exception:  # noqa: BLE001 - a setup that is gone: start without
                self.setup_address = ""


def _first(payload: dict, key: str) -> str:
    from chisurf.core.plugin.workspace_input import read_address

    values = payload.get(key) or []
    values = values if isinstance(values, list) else [values]
    if not values:
        raise ValueError("nothing picked")
    return str(read_address(str(values[0])))


def receive_measurement(app: Any, payload: dict) -> bool:
    """Hand-off receiver (``measurement``): detect the windows of a photon stream. *app* is the
    tool or a bare :class:`~chisurf.emtk.excitation_windows.WindowsReview`."""
    review = getattr(app, "review", app)
    review.set_measurement(_first(payload, "measurement"))
    return True


def receive_setup(app: ExcitationWindowsApp, payload: dict) -> bool:
    """Hand-off receiver (``setup``): check this setup's windows."""
    values = payload.get("setup") or []
    values = values if isinstance(values, list) else [values]
    if not values:
        raise ValueError("nothing picked")
    app.take_setup(str(values[0]))
    return True


def make_app(**kwargs: Any) -> ExcitationWindowsApp:
    """Build the tool (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return ExcitationWindowsApp(**kwargs)


__all__ = ["ExcitationWindowsApp", "make_app", "receive_measurement", "receive_setup"]

