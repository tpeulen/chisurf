"""Rotation parameters follow the polarization a lifetime fit was given.

At magic angle a decay carries no anisotropy, so the rotations and r0 must not
be fitted there: the polarised description ties its rotation count to the
polarization (none at VM), which is what the classic model did by fixing them.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.models.description import for_family


def _view(polarization):
    x = np.arange(128) * 0.05
    fit = fitting.Fit(model_class=for_family("tcspc_polarized"),
                      data=chisurf.core.data.DataCurve(x=x, y=np.full(128, 10.0), ey=np.ones(128)))
    model = fit.model
    model.set_scalar("generated_response", 1.0)
    model.set_scalar("polarization", polarization)
    assert model.problem is not None, model.missing
    return model


def _free(model):
    """What the active structure fits: its parameters that activation left free."""
    used = set(model.structure_parameter_ids())
    return {p.canonical_id for p in model.parameters_all if p.canonical_id in used and not p.fixed}


def test_vm_fits_no_rotation():
    model = _view(0.0)
    assert all(key.endswith("rotations.0") for key, _ in model.structure_options())
    assert not {i for i in _free(model) if i.startswith(("rotation.", "anisotropy.r0"))}


@pytest.mark.parametrize("polarization", [1.0, 2.0, 3.0])
def test_polarised_decays_fit_their_rotations(polarization):
    model = _view(polarization)
    free = _free(model)
    # rotation.amplitude.0 is the normalisation of the rotations, never fitted.
    assert {"rotation.time.0", "anisotropy.r0"} <= free
