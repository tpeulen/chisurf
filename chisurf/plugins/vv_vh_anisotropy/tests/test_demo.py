"""The anisotropy demonstration decays carry a known r(t) = r0·exp(-t/ρ).

``make_demo`` reuses the ``vv_vh_g_factor`` generator: four stacked VV/VH decays
(one 4 ns lifetime, r0 0.38, Gaussian pulse, mixing l1/l2, constant background,
Poisson noise). The slow protein's decay (ρ = 16 ns) is the example the Load
example action opens; all four go to the batch queue.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.vv_vh_anisotropy.demo import PRIMARY, make_demo, paths
from chisurf.plugins.vv_vh_anisotropy.gui.model import AnisotropyModel


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Generate the decays and load the slow protein's into a model."""
    folder = tmp_path_factory.mktemp("anisotropy-demo")
    primary = make_demo(folder)
    model = AnisotropyModel()
    model.add_batch_paths([str(path) for path in paths(folder).values()])
    model.load(str(primary))
    return model


def test_the_example_loads_the_slow_protein_decay(example):
    """The primary file is the ρ = 16 ns decay and the region defaults to its tail."""
    assert example.has_data
    assert example.loaded_file.endswith(PRIMARY + ".dat") or example.loaded_file.endswith(
        "gfactor_slow.dat"
    )
    assert example.region_min < example.region_max
    assert np.isfinite(example.r_infty)


def test_r_inf_of_the_slow_decay_is_physical(example):
    """The tail anisotropy of the 16 ns decay is small but not zero."""
    assert 0.05 < example.r_infty < 0.25


def test_the_batch_reports_r_inf_for_all_four_files(example):
    """Every queued file processes without error and yields a finite r∞."""
    rows = example.run_batch()
    assert len(rows) == 4
    assert all(not row[-1] for row in rows)
    assert all(np.isfinite(row[1]) for row in rows)
