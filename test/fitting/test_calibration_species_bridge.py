"""Species-specific gamma through the ndX calibration bridge, into vector constants.

tttrlib's calibration decides (by BIC) whether each FRET species needs its own
gamma; the bridge turns a species result into ndX vector constants
(``set_vector`` arguments) with the per-burst population and probability
columns they are evaluated on.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("ndxplorer")

from ndxplorer.analysis.fret_calibration import apply_result  # noqa: E402
from ndxplorer.core.data_source import DataSource  # noqa: E402

from chisurf.core.fluorescence.fret.lines import static_fret_line  # noqa: E402
from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx  # noqa: E402

TAU_D0, ALPHA, DELTA, BETA = 4.0, 0.07, 0.05, 0.9


def _bursts(species_gamma, seed=5):
    """Donor-only, acceptor-only and two FRET species with their own gamma."""
    rng = np.random.default_rng(seed)
    cols = {k: [] for k in ("green", "red", "yellow", "tau")}

    def add(dd, da, aa, tau):
        cols["green"].append(rng.poisson(dd))
        cols["red"].append(rng.poisson(da))
        cols["yellow"].append(rng.poisson(aa))
        cols["tau"].append(tau + rng.normal(0, 0.15, len(dd)))

    tot = rng.uniform(60, 200, 500)
    add(tot, ALPHA * tot, np.full(500, 0.3), np.full(500, TAU_D0))
    tot = rng.uniform(60, 200, 400)
    add(np.full(400, 0.3), DELTA * tot * BETA, tot * BETA, np.full(400, np.nan))
    # static species: their lifetimes lie on the static line the bridge builds
    line = static_fret_line(TAU_D0, r0=52.0, sigma=6.0)
    for e, g in zip((0.3, 0.7), species_gamma):
        tot = rng.uniform(60, 200, 2000)
        f_dd, f_da, f_aa = tot * (1 - e) / g, tot * e, tot * BETA
        tau = float(line.lifetime_at(e))
        add(f_dd, f_da + ALPHA * f_dd + DELTA * f_aa, f_aa, np.full(2000, tau))
    return {k: np.concatenate(v).astype(float) for k, v in cols.items()}


def _calibrate(species_gamma):
    columns = _bursts(species_gamma)
    window = SimpleNamespace(
        data_source=DataSource.from_columns(columns), constants={"tauD0": TAU_D0}
    )
    mapping = {"i_dd": "green", "i_da": "red", "i_aa": "yellow", "tau_f": "tau"}
    return window, optimize_calibration_from_ndx(
        window, columns=mapping, background="none", n_bootstrap=0, recompute=False, use_priors=False
    )


def test_species_gamma_becomes_a_vector_constant():
    window, result = _calibrate((0.6, 1.2))
    assert result["ok"]
    species = result["species"]
    assert species["model_selection"]["selected"] == "species"
    gamma = result["vectors"]["gamma"]
    assert gamma["populations"] == species["names"] == ["FRET 1", "FRET 2"]
    np.testing.assert_allclose(gamma["values"], [0.6, 1.2], rtol=0.1)
    assert gamma["column"] == "Population" and gamma["codes"] == {"FRET 1": 0.0, "FRET 2": 1.0}
    for name, column in gamma["probabilities"].items():
        assert column in result["injected"]
        values = np.asarray(window.data_source.column_values(column))
        assert np.all((values >= 0) & (values <= 1))

    written = {}
    apply_result(
        result,
        write_constants=lambda values: None,
        write_vector=lambda name, vector: written.setdefault(name, vector),
    )
    assert set(written) == {"gamma"} and written["gamma"]["default"] == gamma["default"]


def test_shared_gamma_stays_scalar():
    _, result = _calibrate((1.0, 1.0))
    assert result["species"]["model_selection"]["selected"] == "shared"
    assert result["vectors"] == {}
