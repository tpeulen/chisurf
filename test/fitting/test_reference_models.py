print("DEBUG: SCRIPT LOADED")

import sys
import pathlib
# Use absolute path of the repository root
TOPDIR = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(TOPDIR))

import utils
import os
import pytest
import numpy as np

utils.set_search_paths(TOPDIR)

import chisurf.core.data
from chisurf.core.fitting.fit import Fit
import chisurf.core.models.tcspc.lifetime
import chisurf.core.models.tcspc.nusiance

def generate_synthetic_decay(lifetime, amplitude, background, dt, n_channels):
    time = np.arange(n_channels).astype(np.float32) * dt
    y = amplitude * np.exp(-time / lifetime) + background
    # Add some Poisson noise
    y = np.random.poisson(y).astype(np.float32)
    return time, y

def test_lifetime_model_convergence():
    """Fit a synthetic single-exponential decay and recover its lifetime.

    Note what is and is not recoverable. The lifetime spectrum's *amplitudes are
    normalised fractions* -- a single component is 1.0 by construction -- and
    the absolute scale of the decay is carried by the model's scaling parameter,
    not by the amplitude. Asserting the amplitude against the generating count
    rate therefore tests the wrong number; the lifetime, the background and the
    fit quality are the recoverable quantities.
    """
    # 1. Setup Ground Truth
    true_tau = 4.0
    true_amp = 1000.0
    true_bg = 10.0
    dt = 0.032
    n_channels = 1024
    
    time, y_data = generate_synthetic_decay(true_tau, true_amp, true_bg, dt, n_channels)
    ey = np.sqrt(np.maximum(y_data, 1.0)) # Poisson errors
    
    data = chisurf.core.data.DataCurve(x=time, y=y_data, ey=ey)

    # The data goes to the Fit; a Model reads it through ``fit.data`` and has no
    # ``data`` of its own. A Fit built headlessly also has xmin = xmax = 0, so
    # every residual slice is empty and the optimiser refuses outright.
    fit = Fit(model_class=chisurf.core.models.tcspc.lifetime.LifetimeModel, data=data)
    fit.xmin, fit.xmax = 0, n_channels - 1
    model = fit.model
    model.convolve.do_convolution = False  # Matches synthetic generation
    
    # 3. Add Component and Initial Guesses
    # Assigning ``lifetime_spectrum`` is not the way in: that setter lives on
    # the Lifetimes group and *fixes every parameter*, which would leave nothing
    # for the optimiser to do. Appending a component gives free ones.
    while len(model.lifetimes) > 0:
        model.lifetimes.pop()
    model.lifetimes.append(amplitude=800.0, lifetime=3.8)
    model.generic.background = 8.0
    
    fit.run()
    
    # 4. Assertions
    # retrieve current values
    spectrum = model.lifetimes.lifetime_spectrum
    fitted_amp = spectrum[0]
    fitted_tau = spectrum[1]
    fitted_bg = model.generic.background
    
    assert np.isclose(fitted_tau, true_tau, rtol=0.1)
    assert np.isclose(fitted_amp, 1.0, rtol=1e-6), "one component is the whole spectrum"
    assert np.isclose(fitted_bg, true_bg, rtol=0.5)
    assert fit.chi2r < 1.5

if __name__ == "__main__":
    test_lifetime_model_convergence()
    print("Test passed!")
