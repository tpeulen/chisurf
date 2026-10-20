"""A flow stack with a known answer, without the 18 s photon simulation: blobs drifting at *velocity* px/frame (the plugin's own test stack)."""
import numpy as np

#: The scanner the stack is taken to be recorded with (the plugin tests' ``timing_for``): a 48-line scan, 0.32 ms per line, 100 nm pixels.
TIMING = dict(pixel_duration_us=0.32e3 / 48, line_duration_ms=0.32, frame_duration_ms=48 * 0.32, pixel_size_nm=100.0)


def drifting_stack(velocity=0.5, n=48, n_frames=80, n_molecules=60, width=1.6, brightness=30.0, seed=11, axis="x"):
    """``(n_frames, n, n)`` Poisson stack of blobs drifting at *velocity* px/frame along *axis*."""
    rng = np.random.default_rng(seed)
    molecules = rng.uniform(0, n, size=(n_molecules, 2))
    ys, xs = np.indices((n, n))
    frames = []
    for f in range(n_frames):
        image = np.zeros((n, n))
        for cy, cx in molecules:
            if axis == "x":
                cx = (cx + velocity * f) % n
            else:
                cy = (cy + velocity * f) % n
            dx = np.minimum(np.abs(xs - cx), n - np.abs(xs - cx))
            dy = np.minimum(np.abs(ys - cy), n - np.abs(ys - cy))
            image += np.exp(-(dx**2 + dy**2) / (2.0 * width**2))
        frames.append(image)
    return rng.poisson(np.asarray(frames) * brightness).astype(np.float32)


def expected_speed_um_s(velocity_px_per_frame=0.5):
    """The truth: px/frame -> um/s with the TIMING above."""
    return velocity_px_per_frame * TIMING["pixel_size_nm"] * 1e-3 / (TIMING["frame_duration_ms"] * 1e-3)
