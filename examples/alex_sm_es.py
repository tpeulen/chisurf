"""ALEX (alternating laser excitation) analysis of Shimon Weiss lab ``.sm`` files in chisurf.

Runnable, GUI-free demonstration of the smFRET ALEX pipeline on Shimon Weiss lab
single-molecule ``.sm`` data:

1. load the ``.sm`` container through the chisurf ALEX plugin core
   (:func:`chisurf.plugins.tttr.ptu_alex_creator.core.load`);
2. recover the excitation window with ``apply_alex`` — micro-second ALEX encodes
   the green/red laser alternation in the macro-time, which
   ``TTTR.alex_to_microtime`` folds into a synthetic micro-time
   (``micro = (macro - shift) % period``);
3. **auto-detect** the green/red laser windows from the folded-phase
   distribution with ``auto_alex_windows`` — the two laser-on periods show up as
   two plateaus separated by rise/fall gaps; guard bands trim the plateau edges
   so the transition photons are dropped (some photon loss is expected);
4. gate each burst into the DD / DA / AA streams with ``alex_stream_masks`` and
   turn per-burst counts into apparent and corrected ``E``/``S`` with
   :mod:`chisurf.core.fluorescence.burst.es` and a
   :class:`~chisurf.core.fluorescence.fret.calibration.CalibrationParameters`.

A ground-truth two-population ALEX stream with realistic laser windows is
round-tripped through the ``.sm`` container so the recovered efficiencies can be
compared with injected values. Set ``TTTRLIB_DATA`` to also load the real
``sm/data.sm`` reference file.

Run with::

    python examples/alex_sm_es.py
"""

import os
import tempfile

import numpy as np
import tttrlib

from chisurf.core.fluorescence.burst.es import apparent_es, corrected_es
from chisurf.core.fluorescence.fret.calibration import CalibrationParameters
from chisurf.plugins.tttr.ptu_alex_creator.core import (
    alex_stream_masks,
    apply_alex,
    auto_alex_windows,
    load,
)

# .sm container ids, macro-time clock and ALEX alternation (macro units).
SM_CONTAINER, SM_RECORD_TYPE = 7, 11
MACRO_RESOLUTION = 1.25e-8
TY_FLOAT8 = 536870920
ALEX_PERIOD = 8000
# Realistic laser windows: interior plateaus with rise/fall gaps between them.
GREEN_WINDOW = (300, 3700)
RED_WINDOW = (4300, 7700)
CH_DONOR, CH_ACCEPTOR = 0, 1


def simulate_alex_sm(path, populations, seed=1, smear=0.08):
    """Write a synthetic micro-second ALEX stream to an ``.sm`` file."""
    rng = np.random.RandomState(seed)
    macro, chan = [], []
    t = np.uint64(0)

    def place(cnt, det, window):
        lo, hi = window
        base = t + rng.randint(0, 12000, cnt).astype(np.uint64)
        ph = lo + rng.randint(0, hi - lo, cnt)
        n_smear = int(smear * cnt)  # photons bleeding into the rise/fall edges
        if n_smear:
            idx = rng.choice(cnt, n_smear, replace=False)
            edge = rng.choice([lo, hi], n_smear)
            ph[idx] = (edge + rng.randint(-150, 150, n_smear)) % ALEX_PERIOD
        ph = ph.astype(np.uint64)
        cycle = (base // np.uint64(ALEX_PERIOD)) * np.uint64(ALEX_PERIOD)
        return cycle + ph, np.full(cnt, det, np.int8)

    for pop in populations:
        E, S = pop["E"], pop["S"]
        for _ in range(pop["n"]):
            t = t + np.uint64(rng.randint(120_000, 260_000))
            size = 40 + rng.poisson(120)
            n_green = rng.binomial(size, S)
            n_red = size - n_green
            n_da = rng.binomial(n_green, E)
            n_dd = n_green - n_da
            for cnt, det, window in [
                (n_dd, CH_DONOR, GREEN_WINDOW),
                (n_da, CH_ACCEPTOR, GREEN_WINDOW),
                (n_red, CH_ACCEPTOR, RED_WINDOW),
            ]:
                if cnt == 0:
                    continue
                m, c = place(cnt, det, window)
                macro.append(m)
                chan.append(c)
            t = t + np.uint64(12000)
    macro = np.concatenate(macro)
    chan = np.concatenate(chan)
    order = np.argsort(macro, kind="stable")
    macro = macro[order].astype(np.uint64)
    chan = chan[order].astype(np.int8)

    d = tttrlib.TTTR()
    d.append_events(macro, np.zeros(len(macro), np.uint16), chan,
                    np.zeros(len(macro), np.int8))
    d.header.tttr_container_type = SM_CONTAINER
    d.header.tttr_record_type = SM_RECORD_TYPE
    d.header.set_tag("MeasDesc_GlobalResolution", MACRO_RESOLUTION, TY_FLOAT8)
    d.write(path)


def alex_counts_per_burst(tttr, bursts, windows):
    """Count DD/DA/AA per burst using the detected ALEX windows."""
    masks = alex_stream_masks(
        tttr.micro_times, tttr.routing_channels, windows,
        donor_channels=[CH_DONOR], acceptor_channels=[CH_ACCEPTOR])
    dd, da, aa = masks["DD"], masks["DA"], masks["AA"]
    i_dd = np.zeros(len(bursts))
    i_da = np.zeros(len(bursts))
    i_aa = np.zeros(len(bursts))
    for k, (s, e) in enumerate(bursts):
        sl = slice(int(s), int(e) + 1)
        i_dd[k] = np.count_nonzero(dd[sl])
        i_da[k] = np.count_nonzero(da[sl])
        i_aa[k] = np.count_nonzero(aa[sl])
    return i_dd, i_da, i_aa


def main():
    """Run the ALEX ``.sm`` demonstration end-to-end."""
    populations = [dict(E=0.20, S=0.55, n=300), dict(E=0.80, S=0.55, n=300)]
    sm_path = os.path.join(tempfile.mkdtemp(), "alex_demo.sm")
    simulate_alex_sm(sm_path, populations)

    # 1. Load the .sm file through chisurf and fold the alternation.
    tttr = load(sm_path, "SM")
    print(f"Loaded {len(tttr)} photons from {os.path.basename(sm_path)}")
    apply_alex(tttr, ALEX_PERIOD, 0)

    # 2. Auto-detect the green/red laser windows from the phase distribution.
    win = auto_alex_windows(
        tttr.micro_times, tttr.routing_channels,
        donor_channels=[CH_DONOR], acceptor_channels=[CH_ACCEPTOR],
        alex_period=ALEX_PERIOD, guard=0.06)
    print(f"Auto windows: green {tuple(round(x) for x in win['green'])} "
          f"(true {GREEN_WINDOW}), red {tuple(round(x) for x in win['red'])} "
          f"(true {RED_WINDOW})")

    # 3. All-photon burst search, then per-burst ALEX stream counting.
    bursts = np.asarray(
        tttr.burst_search(L=40, m=10, T=1.0e-3, mode="sliding_window")
    ).reshape(-1, 2)
    i_dd, i_da, i_aa = alex_counts_per_burst(tttr, bursts, win)
    print(f"Found {len(bursts)} bursts")

    # 4. Apparent and corrected E/S.
    es = apparent_es(i_dd, i_da, i_aa)
    E, S = np.asarray(es["E"]), np.asarray(es["S"])
    calib = CalibrationParameters()
    ces = corrected_es(i_dd, i_da, i_aa, gamma=calib.gamma, alpha=calib.alpha,
                       beta=calib.beta, delta=calib.delta)
    Ec = np.asarray(ces["E"])

    print("Apparent populations:")
    print(f"  low-E  {E[E < 0.5].mean():.3f} (injected 0.20)")
    print(f"  high-E {E[E >= 0.5].mean():.3f} (injected 0.80)")
    print(f"  S mean {S.mean():.3f} (injected 0.55)")
    print(f"Corrected E (identity calibration) matches apparent: "
          f"{np.allclose(Ec, E)}")

    # Optional: load the real reference file if present.
    data_root = os.environ.get("TTTRLIB_DATA")
    if data_root:
        real = os.path.join(data_root, "sm", "data.sm")
        if os.path.isfile(real):
            ref = load(real, "SM")
            dur = float(ref.macro_times.max()) * ref.header.macro_time_resolution
            print(f"\nsm/data.sm: {len(ref)} photons over {dur:.1f} s "
                  f"(continuous-wave, donor-dominated reference)")


if __name__ == "__main__":
    main()
