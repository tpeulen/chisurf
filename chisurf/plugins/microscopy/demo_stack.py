"""The synthetic image stacks shared by the microscopy tools' demos.

One generator per question a tool answers: a bead frame with a known linear
drift (drift correction), one band-limited object seen through independent noise
(FRC), a movie of diffusing particles (tracking) and a bead z-stack with a known
FWHM (PSF determination). Every generator is seeded, so the demos and their
tests agree on the answer the tool must find.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

#: The per-frame shift ``(dy, dx)`` the drift demo injects: two pixels up and one
#: left per frame, as the plugin's own parity fixture uses.
DRIFT_STEP = (2, -1)


def beads_frame(
    shape: tuple[int, int] = (128, 128),
    beads: tuple = ((34, 30), (70, 84), (96, 44), (52, 108)),
    sigma_px: float = 2.5,
    amplitude: float = 400.0,
    background: float = 8.0,
) -> np.ndarray:
    """A noise-free frame of Gaussian beads on a flat background."""
    y, x = np.indices(shape)
    frame = np.full(shape, float(background))
    for by, bx in beads:
        frame += amplitude * np.exp(
            -0.5 * (((y - by) / sigma_px) ** 2 + ((x - bx) / sigma_px) ** 2)
        )
    return frame


def drift_stack(n_frames: int = 6, seed: int = 7, **frame_kwargs) -> np.ndarray:
    """A bead stack drifting by :data:`DRIFT_STEP` per frame (frame 0 is the reference).

    The truth the drift tool must measure: the shift of frame *k* against frame
    0 is ``k * DRIFT_STEP``, applied by :func:`numpy.roll` exactly as the
    plugin's own tests do.
    """
    rng = np.random.default_rng(seed)
    base = beads_frame(**frame_kwargs)
    frames = [
        np.roll(base, (k * DRIFT_STEP[0], k * DRIFT_STEP[1]), axis=(0, 1))
        for k in range(n_frames)
    ]
    return rng.poisson(np.stack(frames)).astype(np.float32)


def frc_stack(n_frames: int = 8, size: int = 128, cutoff: float = 0.15,
              noise: float = 1.0, seed: int = 3, object_seed: int = 1) -> np.ndarray:
    """One band-limited object seen through independent noise (the FRC demo)."""
    rng = np.random.default_rng(seed)
    field = np.random.default_rng(object_seed).normal(size=(size, size))
    fx = np.fft.fftfreq(size)[:, None]
    fy = np.fft.fftfreq(size)[None, :]
    truth = np.real(np.fft.ifft2(np.fft.fft2(field) * (np.sqrt(fx**2 + fy**2) <= cutoff)))
    truth = truth / truth.std()
    return np.stack([truth + noise * rng.normal(size=truth.shape) for _ in range(n_frames)])


def tracking_stack(n_frames: int = 40, shape: tuple[int, int] = (160, 160),
                   n_particles: int = 6, diffusion: float = 0.5, seed: int = 1) -> np.ndarray:
    """A movie of particles diffusing with a known coefficient (the tracking demo)."""
    from chisurf.core.fluorescence.imaging import tracking as tk

    frames, _positions = tk.simulate_particle_movie(
        n_frames=n_frames,
        shape=shape,
        n_particles=n_particles,
        diffusion_coefficient=diffusion,
        sigma_psf=1.5,
        amplitude=250.0,
        background=10.0,
        seed=seed,
    )
    return np.asarray(frames, dtype=np.float32)


def psf_stack() -> np.ndarray:
    """A 3-D bead stack with a known answer: five beads, FWHM 424 nm lateral, 2120 nm axial.

    The same generated stack the PSF tool's own *Load demo* shows (sigma
    ``(x, y, z)`` = (1.8, 1.8, 3.0) px/slices on a background of 5, Poisson
    noise, seed 4; 100 nm pixels, 300 nm z step).
    """
    rng = np.random.default_rng(4)
    z, y, x = np.indices((21, 110, 100))
    image = np.full(z.shape, 5.0)
    for bz, by, bx in ((10, 20, 20), (10, 22, 60), (10, 50, 30), (11, 55, 80), (9, 90, 50)):
        image += 800 * np.exp(
            -0.5 * (((x - bx) / 1.8) ** 2 + ((y - by) / 1.8) ** 2 + ((z - bz) / 3.0) ** 2)
        )
    return rng.poisson(image).astype(np.float32)


def write_tif(path: Path, stack: np.ndarray) -> Path:
    """Write *stack* as a multi-page TIFF (the seam the tools read back through)."""
    from chisurf.core.fio.image import imwrite

    path = Path(path)
    imwrite(str(path), np.asarray(stack, dtype=np.float32))
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not write the demo stack to {path}")
    return path


__all__ = [
    "DRIFT_STEP",
    "beads_frame",
    "drift_stack",
    "frc_stack",
    "psf_stack",
    "tracking_stack",
    "write_tif",
]
