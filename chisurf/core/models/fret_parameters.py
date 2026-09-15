"""The FRET constants a model holds as parameters: tau0, R0, kappa^2 and the donor-only fraction.

Used by the photon-distribution models (``pda2c``). TCSPC FRET fits carry the
same quantities as BFF description parameters (``fret.tau0``,
``fret.forster_radius``, ``fret.kappa2``, ``fret.x_donly``); this group is the
classic-model form for the models that are not descriptions.
"""
from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup

__all__ = ["FRETParameters", "set_forster_radius_from_probes"]


class FRETParameters(FittingParameterGroup):
    """tau0, R0, kappa^2 and the donor-only fraction of a FRET model."""

    name = "FRET-parameters"

    @property
    def forster_radius(self) -> float:
        """Foerster radius in Angstrom."""
        return self._forster_radius.value

    @forster_radius.setter
    def forster_radius(self, v: float):
        self._forster_radius.value = v

    @property
    def tauD0(self) -> float:
        """Donor lifetime in the absence of FRET (ns)."""
        return self._tauD0.value

    @tauD0.setter
    def tauD0(self, v: float):
        self._tauD0.value = v

    @property
    def kappa2(self) -> float:
        """Orientation factor kappa^2."""
        return self._kappa2.value

    @kappa2.setter
    def kappa2(self, v: float):
        self._kappa2.value = v

    @property
    def xDOnly(self) -> float:
        """Donor-only fraction (molecules without acceptor)."""
        return np.sqrt(self._xDonly.value ** 2)

    @xDOnly.setter
    def xDOnly(self, v: float):
        self._xDonly.value = v

    def __init__(
            self,
            forster_radius: float = cs.core.settings.fret['forster_radius'],
            tau0: float = cs.core.settings.fret['tau0'],
            xDOnly: float = 0.0,
            kappa2: float = 0.66667,
            **kwargs
    ):
        model = kwargs.get('models', None)
        self._tauD0 = FittingParameter(
            name='t0', label_text='&tau;<sub>0</sub>', value=tau0, fixed=True, model=model,
            description='Donor lifetime in the absence of the acceptor (ns).')
        self._forster_radius = FittingParameter(
            name='R0', label_text='R<sub>0</sub>', value=forster_radius, fixed=True, model=model,
            description='Forster radius R0 of the donor-acceptor pair (Angstrom).')
        self._kappa2 = FittingParameter(
            name='k2', label_text='&kappa;<sup>2</sup>', value=kappa2, fixed=True, lb=0.0, ub=4.0,
            bounds_on=False, models=model,
            description='Orientation factor kappa-squared governing dipole-dipole coupling in FRET (0–4).')
        self._xDonly = FittingParameter(
            name='xDOnly', label_text='x<sub>D,0</sub>', value=xDOnly, fixed=False, lb=0.0, ub=1.0,
            bounds_on=True, model=model,
            description='Fraction of donor-only molecules (no active acceptor) in the sample.')
        super().__init__(parameters=[self._tauD0, self._forster_radius, self._kappa2, self._xDonly], **kwargs)


def set_forster_radius_from_probes(fret_params: FRETParameters, donor_name: str, acceptor_name: str,
                                   db=None) -> bool:
    r"""Look up *R*\ :sub:`0` in the MMFDB fluorophore database and set it; ``True`` when found."""
    from chisurf.core.fluorescence.fret.forster import lookup_forster_radius

    r0 = lookup_forster_radius(donor_name, acceptor_name, db=db)
    if r0 is not None:
        fret_params.forster_radius = float(r0)
        return True
    return False
