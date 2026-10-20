"""The photon-counting stacks the captures and tests use: a structured object, independent Poisson noise in every frame."""
import numpy as np


def object_image(size=96, seed=5):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:size, :size]
    base = np.zeros((size, size))
    for _ in range(40):
        cy, cx, s, a = rng.uniform(6, size - 6), rng.uniform(6, size - 6), rng.uniform(1.2, 3.0), rng.uniform(0.3, 1.0)
        base += a * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * s * s))
    return base / base.max()


def noisy_stack(n_frames=40, size=96, seed=0, brightness=3.0):
    """``n_frames`` independent Poisson realisations of one object (peak ``brightness`` photons per pixel and frame)."""
    rng = np.random.default_rng(seed)
    base = object_image(size)
    return np.stack([rng.poisson(base * brightness) for _ in range(n_frames)]).astype(np.float32)
