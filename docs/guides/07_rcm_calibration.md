# RCM detection calibration from dye solutions

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the FRET-efficiency corrections that calibration determines.
:::

## What it does

Quantitative multi-parameter fluorescence needs the **detection/routing
correction matrix (RCM)** — the linear map that corrects measured per-channel
count rates for detection efficiencies and cross-talk between the spectral (and,
with a polarising beam-splitter, polarisation) channels. Instead of entering
correction factors by hand, the RCM can be **calibrated from two reference
measurements**: a **donor-only** and an **acceptor-only** dye solution.

From the per-channel count rates of the two solutions, their relative absorbance
$\alpha = A_A/A_D$ and the detector layout (which channels are acceptor/donor,
and their polarisation), a small linear system is solved for the RCM. It supports
a 2-channel setup and a 4-channel setup (a polarising beam splitter, using the
dye anisotropies, or a 50/50 split).

## In ChiSurf

```python
from chisurf.core.fluorescence.fret.calibration import rcm_from_dye_solutions

assignment = [("A", "P"), ("D", "P"), ("A", "S"), ("D", "S")]   # per channel: (species, pol.)
donor    = [0.06, 1.00, 0.05, 0.95]   # background-corrected rate/channel, donor solution
acceptor = [1.00, 0.04, 0.90, 0.03]   # ... acceptor solution

rcm = rcm_from_dye_solutions(
    donor, acceptor,
    absorbance_ratio=1.15,
    detector_assignment=assignment,
    anisotropy=(0.20, 0.15),          # (r_donor, r_acceptor) for a polarising BS
)
```

The returned matrix is the identity on unused channels and normalised so its
first ordered element is 1; apply it to measured channel rates to obtain
corrected, species-resolved signals.

## Result

The correction matrix recovered for a 4-channel polarising-beam-splitter setup
with mild inter-channel leakage. Off-diagonal elements encode the cross-talk the
matrix removes; the block structure reflects the parallel/perpendicular split.

```{figure} figures/rcm.png
:name: fig-rcm
:width: 90%

Routing-correction matrix from dye solutions.
```

## See also

- {src}`chisurf/core/fluorescence/fret/calibration.py` (`rcm_from_dye_solutions`, plus the
  γ/β/leakage/direct-excitation correction helpers).
