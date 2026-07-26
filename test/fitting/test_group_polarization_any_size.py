"""Polarization assignment across a fit group of any size.

Five test files in this directory were written during one bug hunt and none of
them could fail. They ``logger.error(...)``d on a wrong polarization type
instead of asserting; one took a ``num_datasets`` argument with no fixture and
no ``parametrize``, so pytest errored at collection and the sizes were only ever
passed from a ``__main__`` block; another ended with ``return True``. Between
them they contained zero assertions about polarization. They are consolidated
here, as assertions.

The contract they should have been pinning is stated in
``Anisotropy.set_polarization_by_group_position``
(``chisurf/core/models/tcspc/anisotropy.py``): a group of one fit is
magic-angle; a two-fit group whose data is *stacked* VV/VH is ``vv/vh`` on both;
otherwise every group, of whatever size, alternates ``vv``/``vh`` by index — so
a three-fit group really is vv/vh/vv.
"""
from __future__ import annotations

import numpy as np
import pytest

import chisurf as cs
import chisurf.macros
from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.tcspc.lifetime import LifetimeModel


def _fit_group(num_datasets: int) -> FitGroup:
    """Build a group of *num_datasets* single-channel decays."""
    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 100)
    datasets = [
        DataCurve(
            x=x,
            y=np.exp(-x / (i + 1)) + 0.1 * rng.standard_normal(100),
            name=f"Dataset {i}",
        )
        for i in range(num_datasets)
    ]
    return FitGroup(
        data=ExperimentDataCurveGroup(datasets), model_class=LifetimeModel
    )


@pytest.mark.parametrize("num_datasets", [1, 2, 3, 4, 5])
def test_group_polarization_assignment(num_datasets):
    """Polarizations alternate by index, whatever the group size."""
    group = _fit_group(num_datasets)
    got = [f.model.anisotropy.polarization_type for f in group.grouped_fits]

    if num_datasets == 1:
        # A lone fit has no partner to divide by, so it is magic-angle.
        assert got == ['vm']
    else:
        assert got == ['vv' if i % 2 == 0 else 'vh' for i in range(num_datasets)]


@pytest.mark.parametrize("num_datasets", [2, 3, 4])
def test_every_fit_knows_its_siblings(num_datasets):
    """The polarization rule keys off group position, so the link must exist.

    ``Fit.group`` is the *list* of sibling fits, not the ``FitGroup``: it is
    filled in ``Fit.__init__`` before the group object exists, and the model
    needs it there to read its own index while it is being constructed.
    """
    group = _fit_group(num_datasets)
    siblings = group.grouped_fits
    for fit in siblings:
        assert fit.group is siblings
        assert len(fit.group) == num_datasets


def test_polarization_resync_updates_the_whole_group():
    """Re-running the assignment from one fit re-sets every fit in the group.

    The method is not "set mine" but "set the group's", which is what makes it
    correct to call after a fit has been added to an existing group.
    """
    group = _fit_group(3)
    fits = group.grouped_fits
    for fit in fits:
        fit.model.anisotropy.polarization_type = 'vm'

    first = fits[0]
    first.model.anisotropy.set_polarization_by_group_position(first, first.model)

    got = [f.model.anisotropy.polarization_type for f in fits]
    assert got == ['vv', 'vh', 'vv']


def test_separately_added_fits_are_each_their_own_group():
    """Two fits added one at a time are two groups of one, not one group of two.

    The even/odd rule keys off position *within a group*. The test that used to
    assert this expected ``vv``/``vh`` and merely logged when it got neither —
    the rule never applied here, because ``add_fit`` per dataset makes a group
    per dataset and a lone fit is magic-angle.
    """
    saved_datasets, saved_fits = cs.imported_datasets, cs.fits
    try:
        x = np.linspace(0, 10, 100)
        cs.imported_datasets = [
            DataCurve(x=x, y=np.exp(-x / (i + 1)), name=f"Dataset {i}")
            for i in range(2)
        ]
        cs.fits = []
        for index in range(2):
            # LifetimeModel must be imported for add_fit to resolve its name:
            # the lookup walks Model.__subclasses__(), which only sees classes
            # some module has already imported. It is, at the top of this file.
            chisurf.macros.add_fit(
                model_name=LifetimeModel.name, dataset_indices=[index]
            )

        assert len(cs.fits) == 2
        for fit_group in cs.fits:
            assert len(fit_group.grouped_fits) == 1
            assert fit_group.grouped_fits[0].model.anisotropy.polarization_type == 'vm'
    finally:
        cs.imported_datasets, cs.fits = saved_datasets, saved_fits
