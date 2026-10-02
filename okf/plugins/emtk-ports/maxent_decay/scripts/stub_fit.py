"""The stub live fit both tools are fed: a two-lifetime decay (1.1 / 3.6 ns, 256 channels) with its IRF."""
from types import SimpleNamespace
import numpy as np

def stub_fit():
    from chisurf.plugins.fluorescence_decay.maxent_decay.test.test_solver_contract import _problem
    y, lamp, dt, t = _problem(n=256)
    data = SimpleNamespace(x=t, y=y, name="two_lifetimes.dat", dx=np.array([dt]))
    irf = SimpleNamespace(x=t, y=lamp, name="IRF.dat")
    return SimpleNamespace(data=data, xmin=20, xmax=255, model=SimpleNamespace(
        convolve=SimpleNamespace(irf=irf, unnormalized_irf=irf, timeshift=0.0, lamp_background=0.0),
        generic=SimpleNamespace(background=5.0, scatter=0.0)))
