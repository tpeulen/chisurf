"""A burst-analysis folder on the simulated PIE measurement of Excitation Windows.

The demo of :mod:`chisurf.core.fluorescence.simulation.pie_demo` (32 ps, 3125 channels, pulses at 2
and 52 ns; routing 0 donor, 1 acceptor) written beside ``burstwise/bi4_bur/<stem>.bur`` -- a
zero-interleaved burst table of consecutive photon blocks, as the burst reader expects. The
windows that hold its pulses are prompt ``[50, 1613)`` and delayed ``[1613, 3125)``.
"""

from __future__ import annotations

import pathlib

import numpy as np

#: Inclusive micro-time ranges of the demo's excitations (what BVA / 2CDE apply).
PROMPT = (50, 1612)
DELAYED = (1613, 3124)
#: Ranges of an instrument with another TAC range: the donor gate misses the donor pulse.
WRONG_DONOR = (2048, 4094)


def build(root: pathlib.Path, n_bursts: int = 40, photons: int = 200) -> pathlib.Path:
    """Write the measurement and its burst table under *root*; return the analysis folder."""
    from chisurf.core.fluorescence.simulation.pie_demo import make_demo

    root.mkdir(parents=True, exist_ok=True)
    ptu = pathlib.Path(make_demo(root))
    folder = root / "burstwise"
    (folder / "bi4_bur").mkdir(parents=True, exist_ok=True)
    lines = ["First Photon\tLast Photon\tNumber of Photons\tFirst File"]
    for first in np.arange(n_bursts) * photons:
        last = int(first) + photons - 1
        lines += ["0\t0\t0\t", f"{int(first)}\t{last}\t{photons}\t{ptu.name}"]
    (folder / "bi4_bur" / f"{ptu.stem}.bur").write_text("\n".join(lines))
    return folder


def donor_only(root: pathlib.Path) -> pathlib.Path:
    """The demo without its acceptor-excitation pulse (one pulse: donor-only or not PIE)."""
    from chisurf.core.fluorescence.simulation import pie_demo as d
    path = root / "donor_only.ptu"
    d.make_demo(path.parent, donor_only=True, name=path.name, n_photons=100_000)
    return path
