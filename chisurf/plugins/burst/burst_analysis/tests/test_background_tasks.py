"""BVA and 2CDE computed in a task process give what the step computes itself.

The pipeline computes them in worker processes while the user sets up Burst MLE; the result
travels back as column arrays and is rebuilt into a table -- it must be the same table.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from chisurf.core.datastore import column_names
from chisurf.plugins.burst.burst_analysis.gui import background_tasks as bt

DATA = Path(__file__).resolve().parents[2] / "burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
DETECTORS = {"green": {"chs": [0, 1], "micro_time_ranges": []}, "red": {"chs": [8, 9], "micro_time_ranges": []}}


def _run(tmp_path) -> Path:
    from chisurf.plugins.burst.burst_selection.api.models import AnalysisRequest
    from chisurf.plugins.burst.burst_selection.api.selection import analyze_request
    from chisurf.plugins.burst.burst_selection.tests.test_real_data import real_data_settings

    photons = tmp_path / "m000.spc"
    shutil.copy(DATA, photons)
    settings = real_data_settings()
    settings.output_formats = ["pto"]
    out = tmp_path / "analysis"
    result = analyze_request(
        AnalysisRequest(files=[str(photons)], settings=settings, detectors=DETECTORS,
                        output_dir=str(out), container_dirs={str(photons): str(out)})
    )
    return Path(result.output_paths_by_file[str(photons)]["output_folder"])


def _same(a, b) -> None:
    assert list(column_names(a)) == list(column_names(b))
    for name in column_names(a):
        x, y = np.asarray(a[name]), np.asarray(b[name])
        if x.dtype.kind in "fc":
            np.testing.assert_allclose(x, y, equal_nan=True)
        else:
            assert x.tolist() == y.tolist(), name


def test_bva_and_2cde_tasks_match_the_steps_own_computation(tmp_path):
    from chisurf.plugins.burst.burst_2cde.core import computation as cde
    from chisurf.plugins.burst.burst_2cde.gui.view_model import TwoCdeViewModel
    from chisurf.plugins.burst.burst_bva.core import computation as bva
    from chisurf.plugins.burst.burst_bva.gui.view_model import BvaViewModel

    run = _run(tmp_path)

    bm = BvaViewModel()
    bm.set_folder(run)
    settings = bm.bva_settings()
    columns, note = bt.bva_task(str(run), dict(settings), False, "fp", [], {})
    assert note == ""
    kw = dict(settings)
    file_type = kw.pop("file_type")
    df, tttrs = bva.read_burst_analysis(run, file_type, pattern="bi4_bur")
    _same(bt._store(columns), bva.compute_bva(df, tttrs, **kw))

    cm = TwoCdeViewModel()
    cm.set_folder(run)
    s = dict(cm.settings())
    columns, variant, note = bt.two_cde_task(str(run), s, "fp", [], {})
    assert variant == s["variant"]
    df, tttrs = cde.read_burst_analysis(run, s["file_type"], pattern="bi4_bur")
    own = cde.compute_2cde(
        df, tttrs, donor_channels=s["donor_channels"], acceptor_channels=s["acceptor_channels"],
        donor_micro_time_ranges=s.get("donor_micro_time_ranges", []),
        acceptor_micro_time_ranges=s.get("acceptor_micro_time_ranges", []),
        tau=s["tau_us"] * 1e-6, kernel=s["kernel"], variant=s["variant"],
    )
    _same(bt._store(columns), own)


def test_a_task_runs_in_another_process():
    import os

    assert bt.pool().submit(os.getpid).result(timeout=120) != os.getpid()
