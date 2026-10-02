"""A synthetic bead stack with a known answer: five Gaussian beads, sigma (x, y, z) = (1.8, 1.8, 3.0) pixels / slices, pixel 100 nm, z step 300 nm
(FWHM 424 nm lateral, 2120 nm axial), a flat background of 5 counts and Poisson noise."""
import numpy as np, pathlib

BEADS = [(10, 20, 20), (10, 22, 60), (10, 50, 30), (11, 55, 80), (9, 90, 50)]     # z, y, x

def make_stack(shape=(21, 110, 100), seed=4):
    rng = np.random.default_rng(seed)
    z, y, x = np.indices(shape)
    img = np.full(shape, 5.0)
    for bz, by, bx in BEADS:
        img += 800 * np.exp(-0.5 * (((x - bx) / 1.8) ** 2 + ((y - by) / 1.8) ** 2 + ((z - bz) / 3.0) ** 2))
    return rng.poisson(img).astype(np.float32)

def write_stack(folder, name="beads.tif"):
    import tifffile
    folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True)
    path = folder / name; tifffile.imwrite(path, make_stack()); return str(path)
