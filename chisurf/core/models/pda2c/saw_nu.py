"""SAW-ν polymer-distance PDA model.

Photon-distribution analysis with a self-avoiding-walk (SAW-ν) inter-dye
distance distribution instead of a sum of Gaussians — the polymer model for
disordered/unfolded chains (see
:func:`chisurf.core.math.functions.rdf.saw_nu`).  It reuses the whole
:class:`~chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel` machinery
(tttrlib ``Pda`` S1S2 histogram, FRET/nuisance corrections, 1-D residuals) and
only swaps the distance-distribution source.
"""

from __future__ import annotations

import numpy as np

import chisurf as cs
import chisurf.core.fluorescence
import chisurf.core.math.functions.rdf as rdf
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.pda2c.pdagauss import Pda2cGaussianDistanceModel


class Pda2cSawNuDistances(FittingParameterGroup):
    """SAW-ν distance distribution for a PDA model (parameters: ``Rrms``, ``nu``)."""

    @property
    def distribution(self) -> np.ndarray:
        """Return the SAW-ν distance distribution as a 2xN ``(r, p(r))`` array."""
        r = cs.core.fluorescence.rda_axis
        p = rdf.saw_nu(r, self._r_rms.value, self._nu.value)
        s = p.sum()
        if s > 0.0:
            p = p / s
        return np.vstack((r, p))

    @property
    def r_rms(self) -> float:
        """Root-mean-square inter-dye distance (Å)."""
        return self._r_rms.value

    @property
    def nu(self) -> float:
        """Flory scaling exponent."""
        return self._nu.value

    # The SAW-ν distribution is a single continuous component; the append/pop
    # hooks are no-ops so the model's bootstrap and the editor stay happy.
    def __len__(self) -> int:
        return 1

    def append(self, **kwargs) -> None:
        pass

    def pop(self) -> None:
        pass

    def finalize(self) -> None:
        pass

    def __init__(self, name: str = "pda_saw_nu", **kwargs):
        self._r_rms = FittingParameter(
            value=55.0,
            name="Rrms",
            label_text="R<sub>rms</sub>",
            lb=1.0,
            ub=1000.0,
            bounds_on=True,
            description="Root-mean-square inter-dye distance (Angstrom).",
        )
        self._nu = FittingParameter(
            value=0.588,
            name="nu",
            label_text="&nu;",
            lb=0.30,
            ub=0.95,
            bounds_on=True,
            description="Flory scaling exponent nu (~0.588 expanded, 0.5 theta, <0.4 collapsed).",
        )
        super().__init__(name=name, parameters=[self._r_rms, self._nu], **kwargs)


class Pda2cSawNuModel(Pda2cGaussianDistanceModel):
    """PDA model with a SAW-ν polymer inter-dye distance distribution."""

    name = "PDA2c-SAW-ν-distance"
    view_spec_file = "saw_nu.view.json"

    def __init__(
        self,
        fit: cs.core.fitting.fit.Fit,
        nuisance=None,
        distances: Pda2cSawNuDistances | None = None,
        kw_hist: dict | None = None,
        **kwargs,
    ):
        """Initialize the SAW-ν PDA model (reuses the Gaussian-model machinery)."""
        if distances is None:
            distances = Pda2cSawNuDistances(name="pda_saw_nu", fit=fit, **kwargs)
        super().__init__(fit, nuisance=nuisance, distances=distances, kw_hist=kw_hist, **kwargs)
