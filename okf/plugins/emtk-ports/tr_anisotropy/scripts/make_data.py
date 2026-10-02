"""Synthetic polarised IRF/decay files (known answer: tau 4 ns, rho 1.5 ns, r0 0.35) in a folder. Usage: make_data(folder)."""
import numpy as np, pathlib

def make_data(folder, n=256, dt=0.1, seed=3):
    folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    x = np.arange(n) * dt
    irf = np.exp(-0.5 * ((x - 2.0) / 0.25) ** 2)
    tau, rho, r0, g = 4.0, 1.5, 0.35, 1.0
    r = r0 * np.exp(-x / rho)
    ivv = np.exp(-x / tau) * (1 + 2 * r)
    ivh = g * np.exp(-x / tau) * (1 - r)
    def conv(d):
        return np.convolve(irf, d)[:n]
    out = {}
    for key, y in {"irf_vv": irf * 3000, "irf_vh": irf * 2500,
                   "data_vv": conv(ivv) * 400, "data_vh": conv(ivh) * 400}.items():
        y = rng.poisson(y + 4.0).astype(float)           # a flat background of 4 counts per channel
        path = folder / f"{key}.txt"
        np.savetxt(path, np.column_stack((x, y)), header="time_ns counts")
        out[key] = str(path)
    return out
