"""Default parameter linking in a fit group, and the global-fit dataset guard.

Every test in this file used to read *source text* and grep it for the presence
of a function definition or a decorator line:

    src = Path("cs/macros/core_data.py").read_text(...)
    assert "def _is_global_fit_dataset(" in src

That pins the spelling, not the behaviour — and the paths were stale (``cs/``
was renamed ``chisurf/``, and one of them was relative to the working
directory), so all four raised ``FileNotFoundError``. A test that asserts a
substring appears in a file it cannot open tells you nothing twice over. They
are replaced here with tests of what the functions do.

The polarization copy that also lived in this file is consolidated into
``test_group_polarization_any_size.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

import chisurf as cs
import chisurf.core.actions
import chisurf.core.actions.dataset_actions  # noqa: F401 - registers the actions
from chisurf.core.data import DataCurve, ExperimentDataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.description import tcspc_lifetime as LifetimeModel
from chisurf.macros.core_data import _is_global_fit_dataset
from chisurf.macros.core_fit import (
    _auto_link_non_nuisance_group_parameters,
    _collect_group_nuisance_parameter_names,
)


def _two_fit_group() -> FitGroup:
    """A two-dataset lifetime group with its parameters discovered."""
    x = np.linspace(0, 10, 100)
    group = FitGroup(
        data=ExperimentDataCurveGroup(
            [DataCurve(x=x, y=np.exp(-x / (i + 1)), name=f"Dataset {i}") for i in range(2)]
        ),
        model_class=LifetimeModel,
    )
    for fit in group.grouped_fits:
        fit.model.find_parameters()
    return group


def test_nuisance_parameters_are_the_instrument_group():
    """Instrument parameters count as nuisance, physics does not."""
    model = _two_fit_group().grouped_fits[0].model
    nuisance = _collect_group_nuisance_parameter_names(model)
    assert {"background", "scatter", "n0", "timeshift"} <= nuisance
    assert (
        not {p.name for p in model.parameters_all if p.canonical_id.startswith("lifetime.")}
        & nuisance
    )


def test_grouped_fits_auto_link_non_nuisance_parameters():
    """Grouping links the physics across fits and leaves the nuisances local."""
    group = _two_fit_group()
    masters, followers = _auto_link_non_nuisance_group_parameters(group)
    assert masters > 0 and followers > 0

    first, second = (f.model.parameters_all_dict for f in group.grouped_fits)
    nuisance = _collect_group_nuisance_parameter_names(group.grouped_fits[0].model)

    linked = {n for n, p in second.items() if getattr(p, "is_linked", False)}
    assert linked, "grouping linked nothing at all"
    assert linked.isdisjoint(nuisance)
    for name in linked:
        # A follower points at the *first* fit's parameter of the same name.
        assert second[name].link is first[name]
        assert first[name].is_link_master


def test_a_single_fit_group_links_nothing():
    """With no second fit there is no follower, so the pass is a no-op."""
    x = np.linspace(0, 10, 100)
    group = FitGroup(
        data=ExperimentDataCurveGroup([DataCurve(x=x, y=np.exp(-x), name="one")]),
        model_class=LifetimeModel,
    )
    group.grouped_fits[0].model.find_parameters()
    assert _auto_link_non_nuisance_group_parameters(group) == (0, 0)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Global-fit", True),
        ("global-fit", True),
        ("  Global Dataset ", True),
        ("Global-fit dataset", True),
        ("Dataset 0", False),
        ("", False),
    ],
)
def test_global_fit_dataset_is_recognised_by_name(name, expected):
    """The guard matches on the dataset's name, case- and space-insensitively."""
    assert _is_global_fit_dataset(DataCurve(name=name)) is expected
    # It must accept the server-side dict form as well as the object.
    assert _is_global_fit_dataset({"name": name}) is expected


def test_the_global_fit_dataset_cannot_be_removed():
    """`remove_datasets` skips it, which is the point of the guard."""
    from chisurf.macros import core_data

    saved = cs.imported_datasets
    try:
        keep = DataCurve(name="Global-fit")
        drop = DataCurve(name="Dataset 0")
        cs.imported_datasets = [keep, drop]
        core_data.remove_datasets([0, 1], _from_controller=True)
        assert cs.imported_datasets == [keep]
    finally:
        cs.imported_datasets = saved


def test_restore_global_fit_is_a_registered_action():
    """The GUI reaches the restore through the action registry, by this name."""
    catalog = chisurf.core.actions.get_action_catalog()
    names = set(catalog) if isinstance(catalog, dict) else {a.get("name", a) for a in catalog}
    assert "dataset.restore_global_fit" in names
