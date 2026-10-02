"""Synthetic fast-dye / slow-protein VV/VH files and two batch files (known answer: tau 4 ns, dye rho 0.2 ns, protein rho 16 ns, G 1.2, 3 background counts)."""
import numpy as np, pathlib
from chisurf.core.fio import write_vv_vh

def make_data(folder, n=512, dt=0.05, seed=5):
    folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed); t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - 5.0) / 0.1) ** 2)
    def pair(rho, r0=0.38, g=1.2, scale=2000.0):
        r = r0 * np.exp(-t / rho); i = np.convolve(irf, np.exp(-t / 4.0))[:n]
        vv = rng.poisson(i * (1 + 2 * r) * scale + 3.0).astype(float)
        vh = rng.poisson(i * (1 - r) / g * scale + 3.0).astype(float)
        return vv, vh
    out = {}
    for name, rho, scale in (("fast", 0.2, 2000), ("slow", 16.0, 2000), ("batch1", 8.0, 1500), ("batch2", 30.0, 1500)):
        vv, vh = pair(rho, scale=scale); path = folder / f"{name}.dat"
        write_vv_vh(path, vv=vv, vh=vh, metadata={"dt": dt}); out[name] = str(path)
    return out
