"""Multi-component photon-counting-histogram (PCH) fit model."""

from __future__ import annotations

import numpy as np

import chisurf.core.fitting
import chisurf.logging
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.models.pch import pch


class PchMultiComponentModel(ModelCurve):
    """PCH of a mixture: per species a molecular brightness and a mean occupancy.

    Where `FidaModel` computes the histogram through the FIDA generating function
    with an explicit brightness profile, this one convolves the single-species
    distributions of an open system (see :mod:`chisurf.core.models.pch.pch`).
    """

    name = "PCH multi-component"
    view_spec_file = "pch.view.json"

    #: Most species the model fits. A species is switched off by zeroing either of
    #: its parameters, which is how the component count works.
    MAX_COMPONENTS = 3

    #: Values a component is given when it is switched on.
    DEFAULT_BRIGHTNESS = 2.0
    DEFAULT_OCCUPANCY = 3.0

    def __init__(self, fit: "chisurf.core.fitting.fit.Fit", *args, **kwargs) -> None:
        """Create the model with one active component.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            Fit this model belongs to.
        """
        super().__init__(fit, *args, **kwargs)

        def _p(name, value, label):
            return FittingParameter(
                name=name, label_text=label, value=value, lb=0.0, ub=1.0e6,
                bounds_on=False, fixed=False, registry_id=f"pch.{name}",
            )

        self._eps = [
            _p(f"eps{i}", self.DEFAULT_BRIGHTNESS if i == 1 else 0.0,
               f"&epsilon;<sub>{i}</sub>")
            for i in range(1, self.MAX_COMPONENTS + 1)
        ]
        self._n = [
            _p(f"N{i}", self.DEFAULT_OCCUPANCY if i == 1 else 0.0, f"N<sub>{i}</sub>")
            for i in range(1, self.MAX_COMPONENTS + 1)
        ]
        self.find_parameters()

    # -- editor surface ------------------------------------------------------
    def _species_parameter_rows(self) -> list:
        """Return the parameters as one (brightness, occupancy) pair per row."""
        rows = []
        for eps, n in zip(self._eps, self._n):
            rows.extend((eps, n))
        return rows

    @property
    def n_components(self) -> int:
        """Number of components currently switched on."""
        return sum(
            1 for eps, n in zip(self._eps, self._n)
            if float(eps.value) > 0.0 and float(n.value) > 0.0
        )

    def add_component(self) -> None:
        """Switch on the next component, up to :attr:`MAX_COMPONENTS`.

        Writes the parameters directly. The hand-written version routed these
        writes through the GUI fitting client, so adding a component did nothing at
        all whenever that client was absent -- headless, or before the editor had
        registered the fit -- and the bare ``except`` around it said nothing.
        """
        for eps, n in zip(self._eps, self._n):
            if float(eps.value) > 0.0 and float(n.value) > 0.0:
                continue
            eps.value = self.DEFAULT_BRIGHTNESS
            n.value = self.DEFAULT_OCCUPANCY
            eps.fixed = False
            n.fixed = False
            return
        chisurf.logging.info(
            f"PCH: already at the maximum of {self.MAX_COMPONENTS} components"
        )

    def remove_component(self) -> None:
        """Switch off the last active component, keeping at least one."""
        active = [
            i for i, (eps, n) in enumerate(zip(self._eps, self._n))
            if float(eps.value) > 0.0 and float(n.value) > 0.0
        ]
        if len(active) <= 1:
            chisurf.logging.info("PCH: at least one component is required")
            return
        i = active[-1]
        self._eps[i].value = 0.0
        self._n[i].value = 0.0

    # -- compute -------------------------------------------------------------
    def _update_model(self, **kwargs) -> None:
        """Compute the normalised histogram on the data's photon-count grid."""
        fit = getattr(self.fit, "selected_fit", self.fit)
        data = getattr(fit, "data", None)
        meta = getattr(data, "meta_data", {}) or {}
        k_vals = (meta.get("pch", {}) or {}).get("k_vals", getattr(data, "x", None))
        try:
            k = np.asarray(k_vals, dtype=float)
        except (TypeError, ValueError):
            k = np.array([], dtype=float)

        if k.size == 0:
            y = np.zeros_like(getattr(data, "y", np.zeros(0, dtype=float)), dtype=float)
            self.x = np.arange(y.size, dtype=float)
            self.y = y
            return

        eps = np.array([float(p.value) for p in self._eps], dtype=float)
        ns = np.array([float(p.value) for p in self._n], dtype=float)
        mask = (eps > 0.0) & (ns > 0.0)

        if not np.any(mask):
            y = np.zeros_like(k, dtype=float)
        else:
            try:
                y = np.asarray(pch.pch_mixture(k, eps[mask], ns[mask]), dtype=float)
            except ValueError as e:
                # The count axis comes from the dataset, so it is the user's,
                # and a PCH is only defined on 0, 1, ... k_max. Refusing here
                # costs a flat curve; answering anyway would silently return
                # the histogram of a *different* axis, which looks like a bad
                # fit rather than bad data.
                chisurf.logging.warning("PCH: %s", e)
                self.x = k
                self.y = np.zeros_like(k, dtype=float)
                return
            if y.size != k.size:
                m = min(y.size, k.size)
                y, k = y[:m], k[:m]
            total = float(np.sum(y))
            if total > 0.0 and np.isfinite(total):
                y = y / total

        x_data = getattr(data, "x", None)
        try:
            x_data = np.asarray(x_data, dtype=float)
        except (TypeError, ValueError):
            x_data = None
        self.x = x_data if (x_data is not None and x_data.size == y.size) else k
        self.y = y
