"""Numerical calculator state, independent of Qt hosting."""

from __future__ import annotations

import pathlib

import numpy as np

from chisurf.core.dataspec import load_view_spec
from chisurf.core.fluorescence.anisotropy.kappa2 import s2delta

from .client import Kappa2DistClient

_GUI_DIR = pathlib.Path(__file__).parent


class _Kappa2DistModel:
    """Backing model for the k² distribution calculator.

    Input fields are declared in ``k2dist.view.json`` and rendered by the EMTK
    app in :mod:`.app`, which writes straight through to these attributes.
    Call :meth:`compute` to run the selected model, then read the output fields.
    """

    def __init__(self) -> None:
        self.model_type = "cone"
        self.r_0 = 0.380
        self.r_Dinf = 0.050
        self.r_Ainf = 0.100
        self.r_ADinf = 0.005
        self.kappa2_true = 0.667
        self.fret_efficiency = 0.001
        self.step = 1.5
        self.n_bins = 131
        self.rAD_known = False

        self.k2_mean = 0.0
        self.k2_sd = 0.0
        self.Rapp_mean = 0.0
        self.RappSD = 0.0
        self.delta_deg = 0.0
        self._k2scale: np.ndarray | None = None
        self._k2hist: np.ndarray | None = None
        self._k2_values: np.ndarray | None = None

    def view_spec(self):
        return load_view_spec(_GUI_DIR / ".." / "k2dist.view.json")

    def kappa2_plot_series(self) -> list[dict]:
        if self._k2scale is None or self._k2hist is None:
            return []
        x = np.asarray(self._k2scale[1:], dtype=float)
        y = np.asarray(self._k2hist, dtype=float)
        return [
            {"x": x.tolist(), "y": y.tolist(), "name": "kappa2", "color": "#1f77b4", "width": 2}
        ]

    @property
    def SD2(self) -> float:
        ratio = self.r_Dinf / max(self.r_0, 1e-10)
        return -np.sqrt(max(ratio, 0.0))

    @property
    def SA2(self) -> float:
        ratio = self.r_Ainf / max(self.r_0, 1e-10)
        return np.sqrt(max(ratio, 0.0))

    @property
    def delta(self) -> float:
        _, d = s2delta(
            s2_donor=self.SD2,
            s2_acceptor=self.SA2,
            r_inf_AD=self.r_ADinf,
            r_0=self.r_0,
        )
        return d

    def compute(self, client: Kappa2DistClient) -> None:
        """Execute the computation via the RPC client."""
        result = client.compute(
            model_type=self.model_type,
            r_0=self.r_0,
            r_Dinf=self.r_Dinf,
            r_Ainf=self.r_Ainf,
            r_ADinf=self.r_ADinf,
            kappa2_true=self.kappa2_true,
            fret_efficiency=self.fret_efficiency,
            step=self.step,
            n_bins=self.n_bins,
            rAD_known=self.rAD_known,
        )
        if not result.get("ok"):
            self._k2scale = None
            self._k2hist = None
            self._k2_values = None
            return

        r = result["result"]
        self._k2scale = np.asarray(r["k2_scale"], dtype=float)
        self._k2hist = np.asarray(r["k2_hist"], dtype=float)
        self._k2_values = np.asarray(r["k2_values"], dtype=float)
        self.k2_mean = r["k2_mean"]
        self.k2_sd = r["k2_sd"]
        self.Rapp_mean = r["Rapp_mean"]
        self.RappSD = r["RappSD"]
        self.delta_deg = r["delta_deg"]
