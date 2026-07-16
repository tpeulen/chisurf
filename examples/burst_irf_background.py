"""Extract an IRF and a background rate from a single-molecule measurement.

A confocal single-molecule FRET measurement spends most of its time with *no*
molecule in the focus. The photons detected during those quiet, **non-burst**
periods are not sample fluorescence — they are

* dark counts / after-pulses (flat in micro-time), and
* scattered excitation light (a sharp prompt peak — the instrument response
  function, IRF).

So the measurement carries its own scatter/background reference: we do not need a
separate buffer-only or scatter acquisition. This example runs a burst search,
keeps the photons the search *rejects*, and reads two things straight off them,
per detector:

* the background count rate (kHz), from the interphoton-time tail, and
* a scatter-derived IRF, from the non-burst micro-time histogram.

The core function is :func:`chisurf.core.fluorescence.burst.extract_irf_background`;
the same step is available in the guided burst workflow as
``BurstWorkflow.estimate_irf_background`` / ``Bursts.irf_background``.

Run with a display to see the IRF plot (``python examples/burst_irf_background.py``);
without one it prints the background rates and prompt positions.
"""

from pathlib import Path

import tttrlib

import chisurf
from chisurf.core.fluorescence.burst import extract_irf_background

# A real Becker & Hickl SPC single-molecule DNA measurement shipped with ChiSurf.
SPC = (
    Path(chisurf.__file__).resolve().parent
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)

# Two detectors (colours): green on routing channels 0 & 8, red on 1 & 9.
DETECTORS = {
    "green": {"chs": [0, 8]},
    "red": {"chs": [1, 9]},
}


def main():
    """Run the non-burst IRF/background extraction and report/plot the result."""
    tttr = tttrlib.TTTR(str(SPC))

    # The burst-search parameters define what counts as a burst; everything else
    # is treated as background. min_photons=20 is a permissive sliding-window
    # search suitable for this short demo file.
    result = extract_irf_background(tttr, DETECTORS, min_photons=20)

    print(f"{'detector':>8}  {'background/kHz':>14}  {'prompt/ns':>10}  "
          f"{'non-burst':>10}  {'burst':>8}")
    for name, det in result.items():
        print(f"{name:>8}  {det.background_khz:>14.3f}  {det.prompt_ns:>10.3f}  "
              f"{det.n_background_photons:>10d}  {det.n_burst_photons:>8d}")

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    colors = {"green": "#2ca02c", "red": "#d62728"}
    for name, det in result.items():
        if det.irf.sum() > 0:
            ax.plot(det.time_ns, det.irf, lw=1.5, color=colors.get(name),
                    label=f"{name} (bg {det.background_khz:.2f} kHz)")
    ax.set_xlabel("Micro time (ns)")
    ax.set_ylabel("IRF (normalised)")
    ax.set_title("IRF & background from non-burst photons")
    ax.legend()
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
