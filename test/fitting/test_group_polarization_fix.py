"""Rotation parameters follow the polarization a lifetime model was given.

The group-assignment test that used to head this file logged errors instead of
asserting and so could never fail; the same contract is now pinned, for every
group size, in ``test_group_polarization_any_size.py``.
"""
from __future__ import annotations

from chisurf.core.fitting.fit import Fit
from chisurf.core.models.tcspc.anisotropy import Anisotropy
from chisurf.core.models.tcspc.lifetime import LifetimeModel


def test_vm_lifetime_model_rotation_parameters_are_fixed():
    """VM lifetime models must not expose rotation parameters to the fit."""
    fit = Fit(
        model_class=LifetimeModel,
        model_kw={'anisotropy': Anisotropy(polarization='vm')}
    )

    fit.model.anisotropy.add_rotation()
    fit.model.find_parameters()

    rotation_names = {'b(1)', 'rho(1)'}
    assert fit.model.anisotropy.polarization_type == 'vm'
    assert fit.model.anisotropy._bs[0].fixed
    assert fit.model.anisotropy._rhos[0].fixed
    assert rotation_names.isdisjoint(fit.model.parameter_names)


def test_non_vm_lifetime_model_rotation_parameters_are_free():
    """VV/VH lifetime models keep rotation parameters available to the fit."""
    fit = Fit(
        model_class=LifetimeModel,
        model_kw={'anisotropy': Anisotropy(polarization='vv')}
    )

    fit.model.anisotropy.add_rotation()
    fit.model.find_parameters()

    rotation_names = {'b(1)', 'rho(1)'}
    assert fit.model.anisotropy.polarization_type == 'vv'
    assert not fit.model.anisotropy._bs[0].fixed
    assert not fit.model.anisotropy._rhos[0].fixed
    assert rotation_names.issubset(fit.model.parameter_names)

