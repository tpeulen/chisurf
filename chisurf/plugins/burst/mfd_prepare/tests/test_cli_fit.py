"""`csc mfd-prepare fit` runs end to end on the bundled burst folder.

The command read ``reader.data`` (the reader returns a group, it has no such
attribute), fitted without a window or the Poisson score, and asked a model that
refuses covariance uncertainties for them — so it never produced a result. A
one-state fit additionally evaluated with a 100 Hz exchange between the single
state and one that does not exist, because the shared rate-matrix group never
holds fewer than two states.
"""

import json
from pathlib import Path

import numpy as np
from click.testing import CliRunner

from chisurf.plugins.burst.mfd_prepare.cli.main import cli

FOLDER = (
    Path(__file__).resolve().parents[2]
    / "burst_selection/tests/data/bh_spc132_sm_dna/burstwise_All 0.1000#15"
)


def test_a_one_state_model_has_no_exchange():
    """The root of the one-state failure: no rate scheme may reach the evaluation."""
    from chisurf.core.experiments.mfd.reader import MfdReader
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.mfd import Mfd2DModel

    data = MfdReader(n_ratio_bins=21, n_micro_time_bins=21).read(str(FOLDER))[0]
    fit = Fit(
        model_class=Mfd2DModel,
        data=data,
        xmin=0,
        xmax=int(data.y.size),
        model_kw={"n_states": 1},
        noise_model="poisson",
    )
    model = fit.model
    assert model.n_states == 1
    assert model.exchange_rate_matrix() is None
    assert not np.any(np.asarray(model.kinetics.rate_matrix()) > 0.0)
    model.update()
    assert np.all(np.isfinite(model.y))


def test_cli_fit_returns_parameters_for_the_bundled_folder():
    """One state on a coarse grid: the fit runs and lands near the known optimum."""
    result = CliRunner().invoke(
        cli,
        [
            "fit",
            str(FOLDER),
            "--n-states",
            "1",
            "--n-ratio-bins",
            "21",
            "--n-micro-time-bins",
            "21",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output[result.output.index("{") :])
    params = payload["parameters"]
    assert payload["n_states"] == 1
    assert set(params) == {"tauD0", "alpha", "R1", "donorOnly"}
    # The 41x41 optimum is tauD0 2.81 ns, R1 54.0 A, donor-only 0.39.
    assert 45.0 < params["R1"] < 62.0
    assert 2.0 < params["tauD0"] < 3.6
    assert 0.25 < params["donorOnly"] < 0.55
    assert payload["uncertainties"] is None
    assert np.isfinite(payload["chi2r"])
