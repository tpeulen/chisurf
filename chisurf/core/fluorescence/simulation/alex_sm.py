"""A synthetic microsecond-ALEX stream, written as an ``.sm`` file.

Microsecond ALEX alternates two lasers on the *macro*-time clock, so which laser
excited a photon is read from where in the alternation cycle it landed. Anything
that detects those windows, or corrects an E/S histogram built from them, needs a
stream whose windows are known — including their **edges**, because a real
alternation has rise and fall ramps and a window detector that only ever sees
clean plateaus has not been tested on the case that matters.

This is deliberately *not* the confocal photon simulator. There are no molecules
here and no diffusion: bursts are placed directly with a chosen size, E and S, so
the answer is arithmetic rather than a simulation to be trusted. What makes it
belong beside the simulator is the other half — the ``.sm`` container layout,
which is a ChiSurf format concern the TTTR library has no opinion about.

It lived in two places before this, an example and a test, with the constants
copied between them.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "ALEX_PERIOD",
    "CH_ACCEPTOR",
    "CH_DONOR",
    "GREEN_WINDOW",
    "MACRO_RESOLUTION",
    "RED_WINDOW",
    "simulate_alex_sm",
]

#: ``.sm`` container and record ids, and the tag type of a float header value.
SM_CONTAINER, SM_RECORD_TYPE = 7, 11
TY_FLOAT8 = 536870920

#: Macro-time clock (s) and the full two-laser alternation cycle (macro units).
MACRO_RESOLUTION = 1.25e-8
ALEX_PERIOD = 8000

#: Interior plateaus of the two laser windows, with rise/fall gaps between them.
#: A detector that only meets these edges cleanly has not been exercised.
GREEN_WINDOW = (300, 3700)
RED_WINDOW = (4300, 7700)

#: Routing channels of the two detectors.
CH_DONOR, CH_ACCEPTOR = 0, 1


def simulate_alex_sm(path, populations, *, seed: int = 1, smear: float = 0.08):
    """Write a synthetic microsecond-ALEX photon stream to an ``.sm`` file.

    Parameters
    ----------
    path : path-like
        Destination file.
    populations : sequence of mapping
        One entry per population, ``{"E": ..., "S": ..., "n": ...}`` — apparent
        FRET efficiency, apparent stoichiometry, and how many bursts to place.
    seed : int
        Deterministic output.
    smear : float
        Fraction of each burst's photons moved onto the *edges* of their laser
        window, standing in for the rise and fall of a real alternation. Zero
        gives perfect plateaus, which is the case a window detector passes
        trivially.

    Returns
    -------
    int
        Number of bursts written.
    """
    import tttrlib

    rng = np.random.RandomState(int(seed))
    macro, chan = [], []
    t = np.uint64(0)
    n_bursts = 0
    span = 12000

    def place(count, detector, window, start):
        """Return macro times and channels for *count* photons in one window."""
        lo, hi = window
        base = start + rng.randint(0, span, count).astype(np.uint64)
        phase = lo + rng.randint(0, hi - lo, count)
        n_smear = int(smear * count)
        if n_smear:
            index = rng.choice(count, n_smear, replace=False)
            edge = rng.choice([lo, hi], n_smear)
            phase[index] = (edge + rng.randint(-150, 150, n_smear)) % ALEX_PERIOD
        phase = phase.astype(np.uint64)
        cycle = (base // np.uint64(ALEX_PERIOD)) * np.uint64(ALEX_PERIOD)
        return cycle + phase, np.full(count, detector, np.int8)

    for population in populations:
        efficiency, stoichiometry = population["E"], population["S"]
        for _ in range(int(population["n"])):
            t = t + np.uint64(rng.randint(120_000, 260_000))
            n_bursts += 1
            size = 40 + rng.poisson(120)
            n_green = rng.binomial(size, stoichiometry)
            n_red = size - n_green
            n_da = rng.binomial(n_green, efficiency)
            n_dd = n_green - n_da
            for count, detector, window in (
                (n_dd, CH_DONOR, GREEN_WINDOW),
                (n_da, CH_ACCEPTOR, GREEN_WINDOW),
                (n_red, CH_ACCEPTOR, RED_WINDOW),
            ):
                if count == 0:
                    continue
                times, channels = place(count, detector, window, t)
                macro.append(times)
                chan.append(channels)
            t = t + np.uint64(span)

    macro = np.concatenate(macro)
    chan = np.concatenate(chan)
    order = np.argsort(macro, kind="stable")
    macro = macro[order].astype(np.uint64)
    chan = chan[order].astype(np.int8)

    data = tttrlib.TTTR()
    data.append_events(
        macro, np.zeros(macro.size, np.uint16), chan, np.zeros(macro.size, np.int8)
    )
    data.header.tttr_container_type = SM_CONTAINER
    data.header.tttr_record_type = SM_RECORD_TYPE
    data.header.set_tag("MeasDesc_GlobalResolution", MACRO_RESOLUTION, TY_FLOAT8)
    data.write(str(path))
    return n_bursts
