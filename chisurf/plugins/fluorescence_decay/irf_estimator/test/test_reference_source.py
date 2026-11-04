"""The window shows the IRF another tool extracted: a reference dye handed over is estimated at once,
the same way (``receive_irf_source``), with its lifetime, rotation and counts in the results."""

from __future__ import annotations

import time

import numpy as np
from emtk.testing import Driver

from chisurf.plugins.fluorescence_decay.irf_estimator.core.extraction import irf_from_reference
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp, receive_irf_source

N, DT, OS = 500, 0.08, 16


def _reference(seed: int = 2):
    t = (np.arange(N * OS) + 0.5) * DT / OS
    irf = np.exp(-0.5 * ((t - 3.0) / 0.2) ** 2)
    r = 0.38 * np.exp(-t / 0.2)
    out, rng = [], np.random.default_rng(seed)
    for pol in (1 + 2 * r, 1 - r):
        d = np.real(np.fft.ifft(np.fft.fft(irf) * np.fft.fft(pol * np.exp(-t / 4.0)))).reshape(N, OS).sum(1)
        out.append(rng.poisson(d / d.sum() * 5e5 + 200.0).astype(float))
    return out


def test_a_reference_dye_handed_over_is_extracted_and_shown():
    vv, vh = _reference()
    app = IRFEstimatorApp()
    drv = Driver(app, (1200, 800))
    try:
        receive_irf_source(
            app,
            {"irf_source": {"kind": "reference", "vv": vv, "vh": vh, "dt_ns": DT, "window": None,
                            "name": "Rh110.ptu", "dye": "Rh110", "listed_tau_ns": 4.0,
                            "detector": "G|G", "origin": "Burst MLE"}},
        )
        assert app.future is not None and app.model.source == "reference" and app.model.vv_vh
        end = time.monotonic() + 60
        while app.future is not None and time.monotonic() < end:
            drv.draw(1)
            time.sleep(0.01)
        painter = drv.draw(3)
        m = app.model
        assert m.extraction is not None and not app.error
        expected = irf_from_reference(vv, vh, DT, listed_tau_ns=4.0, name="Rh110.ptu", dye="Rh110")
        np.testing.assert_allclose(np.asarray(m.result.irf), expected.irf)
        shown = " ".join(painter.strings)
        for label, text in m.result_rows():
            assert text in shown, label
        assert "Reference dye, Rh110: Rh110.ptu" in shown and "from its tail" in shown
        assert "Extracted IRF (scaled)" in shown
    finally:
        app.close()
