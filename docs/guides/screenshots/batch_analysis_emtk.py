"""Figures of the Batch Analysis wizard (the native emtk app) for guide 78, on real fits of the ibh decays.

Usage (repository root, ``QT_QPA_PLATFORM=offscreen``, ``PYTHONPATH`` with the repository and emtk)::

    python docs/guides/screenshots/batch_analysis_emtk.py

Writes ``batch_analysis_loaded.png``, ``batch_analysis_files.png``, ``batch_analysis_run.png`` and ``batch_analysis_results.png`` into
``docs/guides/figures``. The template is the two-exponential fit of the donor-only decay; the batch runs it over the donor-only and the
donor-acceptor decay (real fits, nothing typed in). Settings, MMFDB and the results folder are temporary.
"""
import os
import sys
import tempfile
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FIG = REPO / "docs" / "guides" / "figures"
tmp = Path(tempfile.mkdtemp(prefix="guide_batch_"))
os.environ["CHISURF_SETTINGS_DIR"] = str(tmp / "s")
os.environ["MMFDB_SETTINGS_DIR"] = str(tmp / "m")
os.environ["MMFDB_DATABASE_PATH"] = str(tmp / "m" / "db.sqlite")
(tmp / "s").mkdir()
(tmp / "m").mkdir()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import numpy as np  # noqa: E402
from emtk.testing import RecordingPainter  # noqa: E402

from test.gui.emtk_port_parity import emtk_screenshot  # noqa: E402

import chisurf as cs  # noqa: E402
import chisurf.core.actions  # noqa: E402,F401  (run_batch dispatches fit.set_dataset / fit.run)
import chisurf.gui.widgets.fitting.fitting_client as fitting_client  # noqa: E402
from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit  # noqa: E402
from chisurf.plugins.core.batch_analysis.gui.app import make_app  # noqa: E402

IBH = REPO / "test/data/tcspc/ibh_sample"
DT = 0.0141 * 8  # ns per channel after 8x rebinning (4096 -> 512)
SIZE = (1000, 640)


def decay(name):
    """An ibh .txt decay (8 header lines + 'Chan Data'), rebinned 8x."""
    y = np.loadtxt(IBH / name, skiprows=9)[:, 1]
    return y.reshape(-1, 8).sum(1)


def irf():
    """The shared prompt, its constant background removed, rebinned 8x."""
    y = np.loadtxt(IBH / "Prompt.txt", skiprows=9)[:, 1]
    return np.clip(y - np.median(y[-800:]), 0, None).reshape(-1, 8).sum(1)


def two_exponential_fit(counts):
    warnings.simplefilter("ignore")
    return build_lifetime_fit(counts, bin_width=DT, irf=irf(), n_components=2, initial_lifetimes=[2.0, 4.5],
                              fit_background=True, start_bin=55, stop_bin=480)


class DirectClient:
    """The fitting client without the server: writes parameters of ``chisurf.fits`` directly."""

    def get_fit_objects(self):
        return list(cs.fits)

    def _param(self, name, fit_index):
        return next((p for p in cs.fits[fit_index].model.parameters_all if p.name == name), None)

    def set_parameter_value(self, parameter_name, value, fit_index):
        p = self._param(parameter_name, fit_index)
        if p is not None and not p.fixed:
            p.value = value

    def set_parameter_fixed(self, parameter_name, fixed, fit_index):
        p = self._param(parameter_name, fit_index)
        if p is not None:
            p.fixed = fixed


def shot(app, name):
    app.pointer_move(-20.0, -20.0)
    for _ in range(4):
        app.draw(RecordingPainter(), 0.0, 0.0, *SIZE)
    emtk_screenshot(app, FIG / name, SIZE)
    print("wrote", name)


template = two_exponential_fit(decay("Decay_577D.txt"))
template.run()
d0 = template.data
da = two_exponential_fit(decay("Decay_577D+577A+GTPgS.txt")).data
d0.name, da.name = "Decay_577D", "Decay_577D+577A+GTPgS"
cs.fits[:] = [template]
cs.imported_datasets[:] = [d0, da]
fitting_client._FITTING_CLIENT = DirectClient()

app = make_app()
model = app.model
model.reload_datasets()
model.go_to(1)
model.set_dataset_use(model.dataset_rows()[0], "use", True)
model.set_dataset_use(model.dataset_rows()[1], "use", True)
shot(app, "batch_analysis_loaded.png")
model.go_to(3)
model.save_path = str(tmp / "batch_results.csv")
model.run()
model.wait(300)
shot(app, "batch_analysis_run.png")
model.go_to(4)
shot(app, "batch_analysis_results.png")
model.add_paths([str(IBH / "Decay_577D.txt"), str(IBH / "Decay_577D+577A+GTPgS.txt")])
model.go_to(2)
shot(app, "batch_analysis_files.png")
for row in model.result_rows():
    print("batch", row["Run"], row["Filename"], row["Parameter"], row["Fixed"], row["Value"], row["Chi2r"])
