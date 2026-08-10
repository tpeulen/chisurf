"""Build the mixture test set: one PTU of blobs, one PTU of the IRF.

Four blobs, four lifetimes, two detection channels, and the IRF measurement
that belongs to them. Deterministic: same seed, same file.

The per-blob brightness is **compensated**, and the reason is a simulator
defect rather than physics. tttrlib's SimEngine gives each fluorophore a photon
yield that depends on its *index* in the system — 659, 32336, 169099, 97421 for
indices 0..3, identical whatever their positions are and however many molecules
exist (see okf/references/known-issues.md). Left alone, the first blob is 250x
dimmer than the third and falls below any threshold, so a segmentation test on
this field would be measuring the defect rather than the detector. The
compensation is linear and exact, and it is written here rather than hidden in
the simulator so that removing it is a one-line change once the engine is fixed.
"""
import pathlib
import sys

import numpy as np

from chisurf.core.fluorescence.imaging.simulate import (
    Blob, simulate_irf_measurement, simulate_molecule_mixture, write_mixture_ptu)

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)

#: (ix, iy, tau) — four objects, four lifetimes, well separated on a 48x48 scan.
BLOBS = ((14, 14, 1.0), (34, 14, 3.6), (14, 34, 2.2), (34, 34, 0.6))
#: Photons the same molecule yields at each index, measured at equal brightness.
INDEX_YIELD = np.array([659.0, 32336.0, 169099.0, 97421.0])
TARGET = 60000.0
SEED, DWELL, PSF, N_PIXEL = 7, 2.0, 0.5, 48

brightness = 20000.0 * TARGET / INDEX_YIELD
blobs = [Blob(ix, iy, tau, brightness=float(q))
         for (ix, iy, tau), q in zip(BLOBS, brightness)]

sim = simulate_molecule_mixture(blobs, n_pixel=N_PIXEL, seed=SEED, dwell=DWELL,
                                psf_w0=PSF)
irf = simulate_irf_measurement(n_pixel=16, dwell=DWELL, psf_w0=PSF,
                               brightness=20000.0, seed=11)

print(write_mixture_ptu(sim, OUT / "mixture.ptu"))
print(write_mixture_ptu(irf, OUT / "mixture_irf.ptu"))

img = sim.intensity
print("photons per blob:",
      [int(img[iy - 3:iy + 4, ix - 3:ix + 4].sum()) for ix, iy, _ in BLOBS])
