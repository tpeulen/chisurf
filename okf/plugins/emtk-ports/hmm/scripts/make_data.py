"""A binned two-channel trace with a known 3-state kinetic scheme (means (20,5), (60,15), (110,40) counts per bin, mean dwell 60/40/80 bins)."""
import numpy as np, pathlib

def make_trace(n=1500, seed=11):
    rng = np.random.default_rng(seed)
    means = np.array([[20.0, 5.0], [60.0, 15.0], [110.0, 40.0]])
    stay = np.array([1 - 1 / 60, 1 - 1 / 40, 1 - 1 / 80])
    state, path = 0, np.empty(n, int)
    for i in range(n):
        path[i] = state
        if rng.random() > stay[state]:
            state = int(rng.choice([s for s in range(3) if s != state]))
    return rng.poisson(means[path]).astype(float), path

def write_trace(folder, name="trace.csv", **kw):
    folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True)
    data, _ = make_trace(**kw); path = folder / name
    np.savetxt(path, data, delimiter=","); return str(path)
