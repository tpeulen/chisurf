"""Test input: a VV/VH decay pair with known anisotropy, generated here (seeded Poisson noise), not measured data.

r(t) = r_inf + (r0 - r_inf) exp(-t / rho); VV = I (1 + 2 r) / 3 * g^-1 ... the file stores VV then VH (one column of 2N values).
"""
import numpy as np
from pathlib import Path


def make(path, seed=1, n=256, tau=40.0, rho=18.0, r0=0.36, rinf=0.05, g=1.0, bg_vv=12.0, bg_vh=9.0, shift=0.0):
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=float)
    i = 60000.0 * np.exp(-t / tau)
    r = rinf + (r0 - rinf) * np.exp(-t / rho)
    vv = i * (1 + 2 * r) / 3.0
    vh = g * i * (1 - r) / 3.0
    if shift:
        vh = np.interp(t - shift, t, vh, left=vh[0], right=vh[-1])
    vv = rng.poisson(vv + bg_vv).astype(float)
    vh = rng.poisson(vh + bg_vh).astype(float)
    np.savetxt(path, np.r_[vv, vh], fmt="%d")
    return Path(path)
