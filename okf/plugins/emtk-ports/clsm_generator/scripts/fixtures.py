"""Input maps of the captures: a 64 x 64 brightness image (two Gaussian blobs on a background) and two detector lifetime maps (2 and 3 ns with a gradient)."""
import numpy as np, pathlib
def make(folder):
    folder = pathlib.Path(folder); folder.mkdir(parents=True, exist_ok=True)
    y, x = np.indices((64, 64))
    intensity = 0.1 + np.exp(-0.5 * (((x - 20) / 6) ** 2 + ((y - 24) / 6) ** 2)) + 0.7 * np.exp(-0.5 * (((x - 44) / 5) ** 2 + ((y - 40) / 5) ** 2))
    paths = []
    for name, value in (("intensity", intensity), ("life0", 2.0 + 0.5 * x / 64), ("life1", 3.0 - 0.5 * y / 64)):
        p = folder / f"{name}.npy"; np.save(p, value); paths.append(str(p))
    return paths
