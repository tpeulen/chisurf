"""The docs figure of guide `irf_estimation`: the emtk IRF estimator on a simulated decay whose answer is known.

tau = 4.0 ns single exponential reconvolved with a Gaussian IRF (FWHM 1.18 ns at 5.0 ns), 50 ns range, 8 counts of
background, Poisson noise (seed 5) -- the case where the truncated-exponential assumption holds.
usage: capture_docs_figure.py <out.png>   (repo root; temp HOME / settings from the caller)
"""
import pathlib, sys, time
import numpy as np
sys.path.insert(0, str(pathlib.Path.cwd()))
import test.gui.emtk_port_parity as pp
from emtk.testing import RecordingPainter
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp

n, dt = 500, 0.1002
t = np.arange(n) * dt
irf = np.exp(-0.5 * ((t - 5.0) / 0.5) ** 2)
irf /= irf.sum()
conv = np.convolve(np.exp(-t / 4.0), irf)[:n]
decay = np.random.default_rng(5).poisson(4.0e4 * conv / conv.max() + 8.0).astype(float)
size = (1200, 800)
a = IRFEstimatorApp()
a.model.load_data(decay, dt=dt, time_axis=t, source="simulated decay: tau = 4.0 ns, IRF FWHM 1.18 ns at 5.0 ns")
a.model.source_text = "simulated decay: tau = 4.0 ns, IRF FWHM 1.18 ns at 5.0 ns"
a.start_estimate()
while True:
    a.draw(RecordingPainter(), 0, 0, *size)
    if a.future is None:
        break
    time.sleep(0.02)
for _ in range(4):
    a.draw(RecordingPainter(), 0, 0, *size)
pp.emtk_screenshot(a, pathlib.Path(sys.argv[1]), size)
print(a.model.result_rows())
a.close()
