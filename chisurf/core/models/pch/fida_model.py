"""FIDA fit model for the PCH experiment (fluorescence-intensity distribution analysis).

A photon-counting-histogram model that, unlike `PchMultiComponentModel`, computes
the histogram through the FIDA probability generating function with an explicit
spatial brightness profile (see :mod:`chisurf.core.models.pch.fida`). It recovers
per-species molecular brightness ``q`` and mean number ``N``.

References
----------
Kask P, Palo K, Ullmann D, Gall K (1999) Fluorescence-intensity distribution
analysis and its application in biomolecular detection technology. *PNAS*
96(24):13756-13761. https://doi.org/10.1073/pnas.96.24.13756
"""

from __future__ import annotations

from chisurf import typing

import numpy as np

import chisurf.core.fitting
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.models.pch import fida


class FidaModel(ModelCurve):
    """FIDA photon-counting-histogram model (up to three species plus background)."""

    name = "FIDA"
    view_spec_file = "fida.view.json"

    #: Species whose brightness and occupancy are fitted. Three is what the model
    #: has always offered; a species is switched off by leaving ``q`` or ``N`` at 0.
    N_SPECIES = 3

    def __init__(self, fit: "chisurf.core.fitting.fit.Fit", *args, **kwargs) -> None:
        """Create the FIDA model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            Fit this model belongs to.
        """
        super().__init__(fit, *args, **kwargs)

        def _p(name, value, label, fixed=False, lb=0.0, ub=1.0e6):
            return FittingParameter(
                name=name, label_text=label, value=value, lb=lb, ub=ub,
                bounds_on=False, fixed=fixed, registry_id=f"fida.{name}",
            )

        self._q = [
            _p(f"q{i}", 2.0 if i == 1 else 0.0, f"q<sub>{i}</sub>")
            for i in range(1, self.N_SPECIES + 1)
        ]
        self._n = [
            _p(f"N{i}", 2.0 if i == 1 else 0.0, f"N<sub>{i}</sub>")
            for i in range(1, self.N_SPECIES + 1)
        ]
        self._bg = _p("bg", 0.0, "bg")
        #: Total mean count per bin; computed, so it is an output.
        self._mean = FittingParameter(
            name="mean", label_text="mean", value=float("nan"),
            fixed=True, is_output=True,
        )
        self.find_parameters()

    def _species_parameter_rows(self) -> list:
        """Return the species parameters as one (q, N) pair per row.

        Consumed by a `parameter_group_table` with ``row_width: 2``: a species is
        a brightness *and* an occupancy, and a flat list of six hides which q goes
        with which N.

        Returns
        -------
        list
            Six parameters, as three q/N pairs.
        """
        rows = []
        for q, n in zip(self._q, self._n):
            rows.extend((q, n))
        return rows

    def _scalar_parameter_rows(self) -> list:
        """Return the non-species parameters (background, and the computed mean)."""
        return [self._bg, self._mean]

    @property
    def species(self) -> typing.List[typing.Tuple[float, float]]:
        """The (brightness, occupancy) pairs that are switched on.

        A species with a zero or negative ``q`` or ``N`` contributes nothing and is
        dropped, which is how the editor switches one off without a separate flag.
        """
        q = np.array([p.value for p in self._q], dtype=float)
        n = np.array([p.value for p in self._n], dtype=float)
        mask = (q > 0.0) & (n > 0.0)
        return list(zip(q[mask], n[mask]))

    def update_model(self, **kwargs) -> None:
        """Compute the photon-counting histogram on the data's k grid."""
        fit = getattr(self.fit, "selected_fit", self.fit)
        data = getattr(fit, "data", None)
        meta = getattr(data, "meta_data", {}) or {}
        k_vals = (meta.get("pch", {}) or {}).get("k_vals", getattr(data, "x", None))
        try:
            k = np.asarray(k_vals, dtype=float)
        except (TypeError, ValueError):
            k = np.array([], dtype=float)

        if k.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            return

        species = self.species
        bg = float(self._bg.value)
        k_max = int(round(float(k.max())))
        if not species and bg <= 0.0:
            # No emitters and no background: every bin is empty, which is P(0)=1.
            y = np.zeros(k_max + 1, dtype=float)
            y[0] = 1.0
        else:
            y = fida.fida_pch(k_max, species, background=max(bg, 0.0))

        # ``k_vals`` are integer photon counts, so index rather than interpolate.
        idx = np.clip(np.round(k).astype(int), 0, y.size - 1)
        self._mean.value = float((np.arange(y.size) * y).sum())
        self.x = k
        self.y = y[idx]
