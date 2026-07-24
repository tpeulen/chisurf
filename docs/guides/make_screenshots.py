#!/usr/bin/env python
"""Generate GUI screenshots for the TTTR-LUT tutorial (headless, offscreen).

Grabs real ChiSurf widgets via ``QWidget.grab()`` under the offscreen Qt platform
so the tutorial shows the actual UI, not mockups. Run with the project on the
path and an offscreen platform::

    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python docs/tutorials/make_screenshots.py

Requires the full GUI environment (the arm64 conda env), unlike
``make_figures.py`` which only needs matplotlib.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from qtpy.QtWidgets import QApplication  # noqa: E402

import chisurf.core.settings  # noqa: E402,F401

FIG = pathlib.Path(__file__).parent / "figures"
FIG.mkdir(exist_ok=True)


def _grab(widget, name):
    """Show *widget*, process events, and save a PNG grab into ``figures/``."""
    widget.show()
    QApplication.instance().processEvents()
    widget.grab().save(str(FIG / name))
    print("wrote", name)


def _grab_fcs_model_editor():
    """Grab the composable FCS model editor (AutoForm) for the FCS guide."""
    import numpy as np

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.fcs.general import GeneralFCSModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    x = np.logspace(-3, 3, 60)  # 1 us .. 1 s, in ms
    data = DataCurve(name="synthetic-fcs", load_filename_on_init=False,
                     y=np.zeros_like(x), x=x)
    fit = fit_mod.Fit(model_class=GeneralFCSModel, data=data)
    editor = build_model_editor(fit.model)
    editor.resize(560, 760)
    _grab(editor, "fcs_model_editor.png")


def _grab_tcspc_lifetime_editor():
    """Grab the TCSPC multi-exponential lifetime model editor for the TCSPC guide."""
    import numpy as np

    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.tcspc.lifetime import LifetimeModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    x = np.linspace(0, 25, 256)  # ns
    data = DataCurve(x=x, y=np.exp(-x / 4.0) + 1.0)
    fit = fit_mod.Fit(model_class=LifetimeModel, data=data)
    editor = build_model_editor(fit.model)
    editor.resize(560, 760)
    _grab(editor, "tcspc_lifetime_editor.png")


def _grab_pda_editor():
    """Grab the PDA (Gaussian-distance) model editor for the PDA guide."""
    import numpy as np
    from scipy import stats

    import chisurf.core.fitting.fit as fit_mod
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.data import DataCurve
    from chisurf.core.models.pda.pdagauss import PdaGaussianDistanceModel
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    nmax, nmin = 60, 5
    n = np.arange(nmax + 1)
    ps = stats.poisson.pmf(n, mu=20.0).astype(float)
    ps /= ps.sum()
    s1s2 = np.zeros((nmax + 1, nmax + 1), dtype=float)
    for N in range(nmin, nmax + 1):
        g = np.arange(N + 1)
        s1s2[g, N - g] += ps[N] * stats.binom.pmf(g, N, 0.6) * 1000.0
    ny, nx = s1s2.shape
    rr, cc = np.indices((ny, nx))
    y = s1s2.ravel(order="C")
    pda = {"maximum_number_of_photons": nmax, "minimum_number_of_photons": nmin,
           "minimum_time_window_length": 2e-3, "channels": ([0], [1]), "s1s2": s1s2,
           "ps": ps, "row_indices": rr.ravel().tolist(), "col_indices": cc.ravel().tolist(),
           "ndim": 2, "shape": (ny, nx), "size": int(y.size), "tttr_indices": None}
    data = DataCurve(name="synthetic-pda", load_filename_on_init=False, pda=pda,
                     y=y, x=np.arange(y.size), ey=tcspc.counting_noise(y))
    fit = fit_mod.Fit(model_class=PdaGaussianDistanceModel, data=data)
    editor = build_model_editor(fit.model)
    editor.resize(560, 760)
    _grab(editor, "pda_model_editor.png")


def main():
    """Generate all guide screenshots."""
    app = QApplication.instance() or QApplication([])  # keep a ref alive  # noqa: F841

    for grab in (_grab_fcs_model_editor, _grab_tcspc_lifetime_editor, _grab_pda_editor):
        try:
            grab()
        except Exception as exc:  # keep going; report which grab failed
            print(f"SKIP {grab.__name__}: {exc}")

    # ① Compute LUT — the AutoForm panel with a real flat-light file loaded, so
    # the interactive raw/after plots + draggable region are shown.
    from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import TTRLutToolsWidget

    spc = pathlib.Path("test/data/tttr/BH/132/BH_SPC132.spc")
    tool = TTRLutToolsWidget()
    tool.resize(1120, 760)
    if spc.is_file():
        tool.tac_panel.model.load_files([str(spc)])
        QApplication.instance().processEvents()
    tool.dock_area.setCurrentWidget(tool.tac_panel)
    _grab(tool, "lut_tools_workspace.png")

    # Channel-definition editor with the LUT-handling box.
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_channel_definition import (
        DetectorWizardPage,
    )

    data = {
        "windows": {"prompt": [0, 2048]},
        "detectors": {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}},
        "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 1.0,
                         "micro_time_resolution": 0.032, "micro_time_binning": 1},
        "apply_lut": True,
        "channel_luts": {"0": np.linspace(0, 4096, 4096).tolist()},
        "channel_shifts": {"8": 3},
        "channel_lut_sources": {"0": "uniform.spc"},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(data, fh)
        setup_json = fh.name
    page = DetectorWizardPage(json_file=setup_json, show_setup_selection=False)
    page.resize(680, 900)
    for box in (page._box_reading, page._box_windows, page._box_detectors, page._box_lut):
        box.set_expanded(box is page._box_detectors or box is page._box_lut)
    _grab(page, "lut_channel_box.png")
    os.unlink(setup_json)

    print("screenshots written to", FIG)


if __name__ == "__main__":
    main()
