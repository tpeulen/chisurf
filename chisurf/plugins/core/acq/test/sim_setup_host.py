"""A minimal emtk host for the simulation setup dialog, for the dialog's tests.

The dialog (:class:`~chisurf.plugins.core.acq.gui.sim_setup.SimulationSetupDialog`) is a
self-contained emtk surface: it takes a parameter dictionary and hands the edited one to an
``on_apply`` callback. This host draws it full-viewport and validates *OK* the way a real host
must -- by building the simulator engine from the merged parameters -- so the tests exercise the
dialog without depending on any particular acquisition window.
"""

from __future__ import annotations

from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.view_form import FormState

from chisurf.plugins.core.acq.gui.sim_setup import SimulationSetupDialog
from chisurf.plugins.core.acq.tcspc_devices.simulation.core import algorithms


def default_params() -> dict[str, Any]:
    """A small, valid simulator parameter set (one species, two detectors)."""
    return {
        "N_species": 1,
        "N_ph_max": 256,
        "N_channels": 2,
        "M": [10.0],
        "D": [3.0],
        "q": [300.0, 225.0],
        "q_bg": [0.001, 0.001],
        "k_rad": [0.0],
        "k_nrad": [0.0],
        "box_xy": 2.0,
        "box_z": 4.0,
        "focus_param": [0.3, 2.0],
        "dt": 0.01,
        "psf_type": "analytic_gaussian3d",
        "analytic_excitation": True,
        "rmt1seed": 12345,
        "rmt2seed": 12346,
        "N_tac_channels": 4096,
        "tac_dt": 0.004069,
        "decay_lifetimes": [[[1.0, 3.2]]],
    }


class SimSetupHost(ImApp):
    """Host the simulation setup dialog over the whole viewport.

    Attributes
    ----------
    params : dict
        The parameters the last accepted *OK* produced (merged over the starting ones).
    status : str
        Why the last *OK* was refused, or ``""``.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        """Open the dialog on *params* merged over :func:`default_params`."""
        self.params = {**default_params(), **(params or {})}
        self.status = ""
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.sim_setup = SimulationSetupDialog(dict(self.params), on_apply=self.apply)
        self.sim_setup.show()
        super().__init__(self.render, continuous=True)

    def apply(self, params: dict[str, Any]) -> bool:
        """Accept *params* when the simulator engine can be built from them."""
        candidate = {**self.params, **params}
        try:
            algorithms.build_engine(candidate)
        except Exception as exc:  # noqa: BLE001 - any engine refusal is reported, not raised
            self.status = f"Simulation settings rejected: {exc}"
            return False
        self.params, self.status = candidate, ""
        return True

    def render(self) -> None:
        """Draw the dialog and publish its control rectangles."""
        vp = im.get_main_viewport()
        self.sim_setup.draw((*vp.pos, *vp.size))
        self.item_rects.update(self.sim_setup.rects)

    def close(self) -> None:
        """Nothing to release."""
