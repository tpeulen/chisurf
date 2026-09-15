"""Unit tests for the public model API exercised by the example scripts (PRD-46).

Covers the properties the ``protein_unfolding_*`` scripts drive directly:
``WormLikeChainModel.chain_length`` / ``.persistence_length`` and the
``LifetimeMixtureModel.fractions`` setter. Models are built the same headless
way the scripts build them — ``Fit(model_class=..., data=DataCurve(...))`` — so
no GUI or experiment registry is required.
"""
from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.fitting.fit as fit_mod
from chisurf.core.data import DataCurve
from chisurf.core.models.description import tcspc_fret_gaussian as GaussianModel, tcspc_fret_worm_like_chain as WormLikeChainModel
from chisurf.core.models.description import tcspc_mixture as LifetimeMixtureModel


def _dummy_data() -> DataCurve:
    x = np.linspace(0.0, 25.0, 4096)
    return DataCurve(x=x, y=np.ones_like(x))


def _model(model_class):
    return fit_mod.Fit(model_class=model_class, data=_dummy_data()).model


def test_chain_length_property() -> None:
    wm = _model(WormLikeChainModel)
    wm.chain_length = 80.0
    assert wm.chain_length == pytest.approx(80.0)


def test_persistence_length_property() -> None:
    wm = _model(WormLikeChainModel)
    wm.persistence_length = 60.0
    assert wm.persistence_length == pytest.approx(60.0)


def test_mixture_fractions_setter() -> None:
    mm = _model(LifetimeMixtureModel)
    mm.append_model(_model(GaussianModel), name="folded")
    mm.append_model(_model(WormLikeChainModel), name="unfolded")

    mm.fractions = [0.3, 0.7]
    np.testing.assert_allclose(np.asarray(mm.fractions, dtype=float), [0.3, 0.7])
