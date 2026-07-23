# ChiSurf single-molecule tutorials

A set of short, self-contained tutorials for the single-molecule fluorescence
analyses in ChiSurf.  Each tutorial is runnable headlessly and its figure is
produced by [`make_figures.py`](make_figures.py) from synthetic data using the
very functions the tutorial describes — so the plots are real output, not
sketches.

| # | Tutorial | ChiSurf entry point |
|---|----------|---------------------|
| 1 | [FRET-2CDE / ALEX-2CDE burst dynamics](01_fret_2cde.md) | `tttrlib.TwoCDE`, `burst_2cde` plugin |
| 2 | [Recurrence analysis (RASP)](02_recurrence_rasp.md) | `core.fluorescence.burst.recurrence` |
| 3 | [Polymer inter-dye distance distributions](03_polymer_distance_distributions.md) | `rdf.saw_nu`, `rdf.ising_chain` |
| 4 | [FIDA — photon-counting histograms](04_fida_pch.md) | `core.models.pch.fida` |
| 5 | [Enderlein MDF & two-focus FCS](05_enderlein_mdf_two_focus_fcs.md) | `core.fluorescence.fcs.enderlein` |
| 6 | [ns-FCS second-order correlation](06_nsfcs_second_order.md) | `core.fluorescence.fcs.correlate.second_order_correlation` |
| 7 | [RCM detection calibration](07_rcm_calibration.md) | `core.fluorescence.fret.calibration.rcm_from_dye_solutions` |

## Running

```bash
pixi run -e docs python docs/tutorials/make_figures.py   # regenerate all figures
```

or, outside pixi, with the project on the path:

```bash
PYTHONPATH=. python docs/tutorials/make_figures.py
```

All lengths in the polymer tutorials are in Ångström, FCS lag times in seconds
(displayed in ms), and diffusion coefficients in µm²/s.
