"""The drifting TIFF stack the captures and tests use: blobs on a noisy background, rolled by a known drift per frame."""
import numpy as np


def drifting_stack(n_frames=12, size=128, drift=(2, -1), seed=3):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:size, :size]
    base = np.zeros((size, size))
    for _ in range(14):
        cy, cx, s, a = rng.uniform(10, size - 10), rng.uniform(10, size - 10), rng.uniform(2, 5), rng.uniform(50, 200)
        base += a * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * s * s))
    frames = [np.roll(base, (drift[0] * k, drift[1] * k), axis=(0, 1)) + rng.random((size, size)) * 8 for k in range(n_frames)]
    return np.stack(frames).astype(np.float32)
