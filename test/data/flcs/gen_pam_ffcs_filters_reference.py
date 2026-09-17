"""Regenerate ``pam_ffcs_filters_reference.npz``: PAM's fFCS filters, run in Octave.

PAM (https://gitlab.com/PAM-PIE/PAM, commit 7319d15d) computes the filters in two
places that differ only on empty total-decay bins: ``PAM.m`` ``Update_fFCS_GUI``
(lines 13911-13916, 13954-13982; empty bins dropped) and
``functions/BurstBrowser/Calc_fFCS_Filters.m`` (lines 30-32, 54-58, 65-67; empty
bins set to one). Both are copied verbatim into ``pam_ffcs_filters_reference.m``
beside this file, so regeneration needs Octave but no PAM checkout. With
``--pam <checkout root>`` every copied block is first checked line by line
against a checkout (``junk/clone.sh`` re-clones one).

Usage::

    python test/data/flcs/gen_pam_ffcs_filters_reference.py [--pam junk/PAM]

Keys per case: ``decay``, ``patterns``; ``filters``/``reconstruction`` from
``PAM.m``; ``bb_filters``/``bb_reconstruction``/``bb_weighted_residuals`` from
BurstBrowser. Cases (inputs are stored in the fixture, so the test never
re-derives them):

``two_species_bg``
    one channel, 64 bins, a short and a long lifetime plus PAM's flat background
    pattern; the total decay has empty bins before the rise and in the tail where
    the patterns are *not* zero -- the case where the two routines differ.
``stacked_par_perp``
    two channels (parallel, perpendicular) of 32 bins stacked on one micro-time
    axis, two species with different anisotropy, a few empty bins.
``dense``
    one channel, no empty bins.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import loadmat, savemat

HERE = pathlib.Path(__file__).resolve().parent
DRIVER = HERE / "pam_ffcs_filters_reference.m"
FIXTURE = HERE / "pam_ffcs_filters_reference.npz"
#: (file in the checkout, driver label, first line, last line)
BLOCKS = (
    ("PAM.m", "PAM.m", 13911, 13916),
    ("PAM.m", "PAM.m", 13954, 13982),
    ("functions/BurstBrowser/Calc_fFCS_Filters.m", "Calc_fFCS_Filters.m", 30, 32),
    ("functions/BurstBrowser/Calc_fFCS_Filters.m", "Calc_fFCS_Filters.m", 54, 58),
    ("functions/BurstBrowser/Calc_fFCS_Filters.m", "Calc_fFCS_Filters.m", 65, 67),
)


def _decay(n_bins, tau, dt=0.2, t0=1.0, sigma=0.15):
    """Gaussian-IRF-convolved single exponential on a TAC grid (analytic)."""
    from scipy.special import erfc

    t = (np.arange(n_bins) + 0.5) * dt - t0
    arg = (sigma**2 / tau - t) / (np.sqrt(2.0) * sigma)
    return 0.5 * np.exp(sigma**2 / (2.0 * tau**2) - t / tau) * erfc(arg)


def build_cases():
    """Deterministic inputs: ``{name: (decay (n_ch, LEN), patterns (k, n_ch, LEN))}``."""
    rng = np.random.default_rng(20260917)
    cases = {}

    n = 64
    p = np.stack([_decay(n, 0.8), _decay(n, 4.0), np.ones(n)])[:, None, :]
    p_norm = p / p.sum(axis=2, keepdims=True)
    lam = 30000.0 * (0.5 * p_norm[0, 0] + 0.4 * p_norm[1, 0] + 0.1 * p_norm[2, 0])
    decay = rng.poisson(lam).astype(float)
    decay[:5] = 0.0
    decay[[50, 57, 61]] = 0.0
    cases["two_species_bg"] = (decay[None, :], p)

    n = 32
    shapes = np.stack([_decay(n, 1.0), _decay(n, 3.5)])
    r = np.array([0.05, 0.3])  # steady-state anisotropy per species
    par = shapes * ((1.0 + 2.0 * r) / 3.0)[:, None]
    perp = shapes * ((1.0 - r) / 3.0)[:, None]
    p = np.stack([par, perp], axis=1)  # (k, 2, n)
    lam = 20000.0 * (0.6 * p[0] / p[0].sum() + 0.4 * p[1] / p[1].sum())
    decay = rng.poisson(lam).astype(float)
    decay[0, :3] = 0.0
    decay[1, [2, 30]] = 0.0
    cases["stacked_par_perp"] = (decay, p)

    n = 48
    p = np.stack([_decay(n, 1.5, t0=0.5), _decay(n, 5.0, t0=0.5)])[:, None, :]
    lam = 1e6 * (0.3 * p[0, 0] / p[0, 0].sum() + 0.7 * p[1, 0] / p[1, 0].sum()) + 50.0
    decay = rng.poisson(lam).astype(float)
    assert np.all(decay > 0)
    cases["dense"] = (decay[None, :], p)
    return cases


def check_against_checkout(root: pathlib.Path) -> None:
    """Fail unless the verbatim blocks in the driver equal the checkout's lines."""
    drv = DRIVER.read_text().splitlines()
    for rel, label, first, last in BLOCKS:
        src = (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        start = drv.index(f"% --- {label} {first}-{last} (verbatim) ---") + 1
        copy = drv[start : start + (last - first + 1)]
        if copy != src[first - 1 : last]:
            sys.exit(f"driver block {label} {first}-{last} differs from {root / rel}")
    print(f"verbatim blocks match {root}")


def run_octave(decay, patterns):
    """Run the driver on one case; returns ``{name: array}``, filters as (k, n)."""
    octave = shutil.which("octave") or "/opt/homebrew/bin/octave"
    with tempfile.TemporaryDirectory() as d:
        savemat(f"{d}/ab_input.mat", {"decay": decay, "patterns": patterns})
        shutil.copy(DRIVER, f"{d}/ab_driver.m")
        subprocess.run(
            [octave, "--no-gui", "--quiet", "ab_driver.m"],
            cwd=d,
            check=True,
            capture_output=True,
            text=True,
        )
        out = loadmat(f"{d}/ab_output.mat")
    return {
        "filters": out["filters"].T,
        "reconstruction": out["reconstruction"].ravel(),
        "bb_filters": out["filters_bb"].T,
        "bb_reconstruction": out["reconstruction_bb"].ravel(),
        "bb_weighted_residuals": out["weighted_residuals_bb"].ravel(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pam", type=pathlib.Path, help="root of a PAM checkout to verify against")
    args = parser.parse_args()
    if args.pam is not None:
        check_against_checkout(args.pam)
    arrays = {}
    for name, (decay, patterns) in build_cases().items():
        arrays[f"{name}_decay"] = decay
        arrays[f"{name}_patterns"] = patterns
        for key, value in run_octave(decay, patterns).items():
            arrays[f"{name}_{key}"] = value
    np.savez_compressed(FIXTURE, **arrays)
    print(f"wrote {FIXTURE} ({FIXTURE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
