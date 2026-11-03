---
type: Guide
title: Fluorescence lifetime from photon bursts
description: Beyond photon counts, each burst carries the donor and acceptor micro-times — so a fluorescence lifetime can be fitted per burst.
tags: [guides, tcspc, lifetime, bursts, photons, fret]
---

# Fluorescence lifetime from photon bursts

:::{admonition} Theory
:class: seealso
See {ref}`concept-tcspc-lifetime` for the multi-exponential decay model and Poisson-MLE lifetime fitting.
:::

## What it does

Beyond photon *counts*, each burst carries the donor and acceptor **micro-times**
— so a fluorescence **lifetime** can be fitted per burst. The lifetime is an
independent FRET observable (a shorter donor lifetime = higher FRET), and the
lifetime-vs-efficiency relation separates static FRET (on the static-FRET line
$\tau = \tau_0(1-E)$) from dynamic averaging (off the line) — the second axis of
multi-parameter fluorescence detection.

Because a burst has few photons, the fit is done by **Poisson maximum
likelihood** rather than least squares.

## Extracting patterns from non-burst photons

**Spectroscopy ▸ Single-Molecule ▸ Burst IRF & Background** (also a step of the
burst workflow). The window remembers its layout, not its analysis: after a fresh
start, open the measurement, apply its detector definition and **Compute** again.

```{figure} figures/burst_irf_bg_native_primary_window.png
:width: 100%

Extraction on the 130,507-photon known-prompt stream with a clean
reader definition. The histogram peak is near 2 ns; the **Prompt** column
reports rising-edge positions of 1.968 and 1.941 ns. Estimated background
rates near 1.993 kHz do not exactly recover the authored 2.5 kHz input.
```

The **Burst IRF & Background** tool estimates detector patterns from photons
outside the burst-search intervals. Inspect the retained count and detector
selection before sending patterns to Burst MLE: every burst’s first and last
photon are excluded, including intervals at the end of a measurement. The
complement is taken after combining overlapping intervals. Retained photons
are a measured scatter/background sample; they are not automatically a pure,
independently calibrated instrument response.

Micro-time gates select the background inter-photon intervals. The IRF
histogram spans the detector’s full laser period so a gate cannot clip the
prompt. A later MLE-pattern extraction separates a Gaussian prompt from the
slow fluorescence tail; inspect that choice against a measured IRF where one
is available. Use the input’s complete detector and reader definition when
switching files, including LUTs, shifts and timing overrides.

**Micro-time binning** coarsens the exported MLE pattern once. A factor of 2
changes each 4096-bin polarization half to 2048 bins; the full-period display
histogram, raw photon micro-times and physical header clock remain unchanged.
Set binning in the detector definition so every tool reading it
agrees.

For a Qt-free extraction, save the following as `irf_background.py` and run
`pixi run -e test python irf_background.py`:

```python
import tttrlib
from chisurf.core.fluorescence.burst.irf_bg import extract_irf_background

stream = tttrlib.TTTR(
    "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc",
    "SPC-130",
)
detectors = {
    "G|G": {"chs": [0, 8], "micro_time_ranges": [[0, 4095]]},
    "R|G": {"chs": [1, 9], "micro_time_ranges": [[0, 2048]]},
}
results = extract_irf_background(
    stream, detectors, min_photons=60, photon_window=10, time_window=1e-3,
)
for name, result in results.items():
    print(name, result.background_khz, result.prompt_ns, result.n_background_photons)
```

This direct example uses the decoded stream without a setup-owned LUT or shift.
The native reader applies the configured corrections, so compare results only
under the same complete input definition. **Export MLE patterns** writes the
computed per-detector MLE arrays as NPZ. **Send to MLE** hands them to the
workflow’s receiver; standalone use reports when that receiver is unavailable.

## In ChiSurf

The `burst_mle_analysis` plugin fits the selected registered lifetime model per burst per
detector using tttrlib's C++ maximum-likelihood estimator (the Maus-2001 `2I*`
`Fit23`, and `Fit24`/`Fit25` variants), wrapped by one Qt-free harness:

```python
from chisurf.core.fluorescence.mle import Fit2x, Fit2xSettings, assemble_vv_vh

# the IRF and background belong to the *settings* — they are properties of the
# setup, reused across every burst
settings = Fit2xSettings(dt=micro_resolution_ns, period=laser_period_ns,
                         irf=irf_vv_vh, background=background_vv_vh)
fit = Fit2x(settings)                              # Fit23 by default

# one burst: stack the parallel/perpendicular micro-time histograms
data = assemble_vv_vh(burst_vv, burst_vh)
res = fit.fit(data, initial_values=[2.0, 0.02, 0.38, 1.0])

res.as_dict()              # {'tau': ..., 'gamma': ..., 'r0': ..., 'rho': ...}
res.twoIstar               # the 2I* statistic (lower is better; ~1 per d.o.f. is good)
```

`fit.parameter_names` gives the parameter order for the chosen estimator, and
`res.x` holds exactly those free parameters (four for `fit23`). Derived
quantities are named result columns: `res.r_scatter`, `res.r_experimental`,
`res.converged`, or `res.result(name)` for any column in `res.result_names`.
`res.as_dict()` maps names to values.

The estimator variants differ in what they solve for: **Fit23** (`tau`, `gamma`,
`r0`, `rho`) is the single-lifetime + anisotropy workhorse, **Fit24** fits a
two-exponential decay (`tau1`, `gamma`, `tau2`, `A2`, `offset`), and **Fit25**
selects among four fixed lifetimes. Pass `Fit2xModel.FIT24` / `FIT25` as the
second argument to `Fit2x` to switch; `fit.parameter_names` always reports the
matching parameter order, and `fixed=` pins individual parameters.

The IRF and background can come directly from the non-burst photons (see
[Background rates](15_background_rates.md)); the same harness drives the
pixel-wise image MLE. Batch fits run off the UI thread and export per-burst
tables that open in ndxplorer.

### The Burst MLE tool

Step *6. Burst MLE* of **Spectroscopy ▸ Single-Molecule ▸ Burst Analysis** (no menu
entry of its own; `python -m chisurf.emtk --plugin burst_mle_analysis` opens it alone).
Tabs on the left: **Burst MLE** (input files, runs, detector, fit window and the
editable parameter table), **IRF** (pattern settings), **IRF/BG files** (measured
patterns) and **Detector setup** (the shared channel editor). **Save settings**
writes the selected model and its per-model edits; drop the file on ChiSurf and pick it
(a *setup* row) to carry them into another analysis.

The **Decay and fit** plot shows the whole decay of the burst photons: every
micro-time channel, VV then VH, split by a vertical line. That includes the
channels outside the fit window, which the fit leaves out. Two shaded bands mark
the ranges on each half. **Fit window** (green) is where the decay is fitted:
**Window start** / **Window stop** (in bins) inside the detector's gate. The
model is drawn only there. **IRF range** (orange) is where the IRF the fit
convolves with is not zero, inside the IRF clip (**IRF start** / **IRF stop**).
Every edge is a line you can drag, in either half. Letting go of a line writes
its field and fits again. Changing a field moves its line, so the plot always
shows what is fitted.
**Min photons** (default 5) is the fewest photons a burst needs in the fit
window to be fitted.

The **IRF** tab is there in Simple mode too, because the fit is only as good as
the IRF it convolves with. Its first line says where the IRF comes from. By
default it is estimated from the photons outside the bursts, with the shape set
by **IRF model** (Gaussian, skewed, or the experimental histogram). To use a
separate IRF measurement instead, pick it from the workspace under **Measured
IRF** and press **Use selected**; **Use the estimate** switches back. The plot
shows VV and VH over one period, zoomed onto the IRF: thin lines are the IRF as
loaded, thick lines what the fit uses after the cleanup. The cleanup is
**VH shift**, the clip (**IRF start** / **IRF stop**, also draggable in the plot)
and the **VV** / **VH thresholds**, which zero the counts below that fraction of
the peak.

Select **Fit model** before running the preview or batch:

| Model | Inputs in parameter order | Interpretation |
|---|---|---|
| Fit23 | `tau`, `gamma`, `r0`, `rho` | Single lifetime with polarization. |
| Fit24 | `tau1`, `gamma`, `tau2`, `A2`, `offset` | Two-lifetime mixture; `A2` is the effective second-component amplitude. |
| Fit25 | `tau1`, `tau2`, `tau3`, `tau4`, `gamma` | Four editable, fixed candidate lifetimes; the result reports the winning `selected_index` (0-based). |
| Tail fit (multi-exp) | `tail_start`, `tau1`, `tau2` | Sum of exponentials fitted to the tail of the VV+VH decay from channel `tail_start`; no IRF is deconvolved, so it needs only a background. A preview of the current decay: it is not offered for **Fit bursts**. |

**Fit bursts** splits each measurement's bursts into chunks of at least 200 and
fits them on every core but one; the rows come back in burst order, the same
as a fit on one core. The worker processes stay alive between fits. In the
pipeline they start while the IRF and background are being prepared, so the
5231 bursts of a 311 MB PTU fit in about 0.3 s.

Double-click **Start** to edit a value; use **Fixed** to hold a fitted parameter.
Each model retains its own edits when you switch away and back, including in
saved settings. Fit25 candidate lifetimes remain fixed inputs; `r0` is supplied
by its provider and is not a free table parameter. Fit26 needs two reference
patterns and `fit_nexp` needs its array-input workflow, so neither is offered by
this tool.

#### Where the IRF comes from

In the pipeline the IRF of each detector is taken, in this order, from:

1. **A scatter measurement** (a file named `H2O`, `water`, `Ludox`, `scatter`,
   `IRF` or `prompt`) in the data's folder or one folder up. The buffer
   measurement (`buffer`, `blank`, `PBS`, ...), when there is one, is scaled to
   the scatter's acquisition time and subtracted; then the flat floor. This is
   the best IRF.
2. **A reference dye of known lifetime** (Rh110, Rh6G, Fluorescein, Alexa488,
   Alexa647, Cy5; names and lifetimes in `chisurf/core/fio/reference_dyes.yaml`).
   Its decay is the IRF convolved with one exponential, which is inverted
   exactly: on bins of width Δt, IRF[i] = D[i] − exp(−Δt/τ)·D[i−1] after the
   floor is removed. Of several dyes, each detector takes the one with the most
   photons in its gate: Rh110 for the green detectors, Alexa647 for the red
   detectors of a PIE set-up.
3. **The photons outside the bursts**, fitted with a skewed Gaussian. Those
   photons are mostly fluorescence of dim molecules, not scatter, so only their
   prompt is used.
4. **The burst decay itself**, the last resort, when fewer than 500 photons lie
   outside the bursts in the detector's gate: the blind estimate of
   [IRF Estimation](irf_estimation.md) (a truncated exponential fit and
   Richardson-Lucy deconvolution), trimmed to its prompt by a skewed Gaussian.

A detector that a reference file shows nothing (a green dye in the red
detectors after the red pulse) falls back to the next source. The **IRF** tab
names the source of the selected detector. The scatter fraction **gamma** is
fitted, not fixed: on DNA13bp_3.ptu a fixed gamma of 0.1 gave 2I* = 570 and a
free one 133. With the IRF from Rh110, 2I* was 87.

#### Measured IRF and background, Opt, Save fit

The tab **IRF/BG files** replaces the estimate from the non-burst
photons by measurements. An IRF file may be a scatter or a reference dye: a dye
is recognised by its name and its IRF is recovered as above. **Add IRF files** and **Add background files** take any
TTTR measurement; each detector reads its own channels, the histograms of
several files are summed, the IRF is normalised to one per polarisation and the
background to counts per second. With **one for all** the files serve every
detector, without it only the selected one. **Auto IRF/background** keeps a
measured pattern and estimates only the other one; a new binning re-reads the
files. **Save VV/VHs** writes each file's VV|VH histogram beside it
(`<file>_<channels>.dat`). **IRF model** (Skewed Gaussian, the default; Gaussian; Experimental) is the
shape that **Auto IRF/background** estimates; changing it re-estimates.

**Opt** searches the VH shift, the sub-bin shifts, the IRF window and the IRF
thresholds (**Opt iterations** in the **IRF** tab) for the lowest 2I* of the
current decay: a Latin-hypercube exploration, then a coordinate line search,
starting from the current settings, so the result is never worse than them. The
fit window is not searched, because a narrower window lowers 2I* by leaving out
the bins the model describes badly. **Save fit** stores the detector's window,
thresholds, shifts, 2I*/BIFL options and fix flags on the selected detector
setup; selecting that detector applies them again.

For a self-contained walk-through, press **Guide**, then press the highlighted
**Load example** yourself. It replaces working inputs with 16
synthetic bursts of 1000 photons each, a known input lifetime of 2 ns and a
32 ps micro-time clock, stored in the settings cache. It does not fit for you.
Choose a model, press **Auto IRF/background**, inspect the decay, then press
**Fit bursts**. The generated ground truth is not an acquisition calibration;
finite-photon estimates fluctuate. With measured inputs, add your `.bur` files
and use your measured IRF/background wherever available.

A measurement's `.pto` can be added instead of a `.bur` (**Add files**, or drop
it on the window). The **Runs** table under the burst files lists the burst
searches stored in the container; the run you click is the burst table that is
fitted, over the photons stored in the same file (a bare container opens its
newest run). **Save results** then writes the per-detector fits (`mle green`,
`mle red`, ...), the pooled states and the IRF/background curves into the
container instead of `bg4`/`br4` folders; **Export legacy...** in the PTO
inspector makes those folders on request. **Split by H2MM state** still reads
the loose `h2mm` folder and does not apply to a container.

Saved detector definitions carry LUTs and channel shifts to the photon reader.
The file header's timing is used unless a timing value is typed into the
*Detector setup* reading fields, which overrides it; micro-time values there are
in ps, macro-time and period in ns, and binning is applied once. A completed batch
retains its original model/schema when you subsequently change the selector,
so **Save results** cannot relabel earlier results as a different model.

```python
from chisurf.plugins.burst.burst_mle_analysis.demo import SETUP, make_demo
from chisurf.plugins.burst.burst_mle_analysis.engine import MleSession

bur = make_demo("/tmp/burst-mle-demo")
session = MleSession()
session.set_definition(SETUP)
session.add_burst_files([bur])
session.set_model("fit24")
session.auto_extract()
rows = session.run_batch(max_workers=1)
paths = session.export_results()
```

Run the same script headlessly through `pixi run -e test python demo_fit.py`.
Use a fresh dedicated output directory for the demo. Its generated files can
also be loaded through the normal burst-file selector.

```{figure} figures/21_burst_mle.png
:name: fig-21-burst-mle
:width: 100%

Burst MLE on `m000.bur` of the BH SPC-132 sample folder (green = routing
0/8, red = 1/9), after **Auto IRF**: binning 32, window 15–116, and a Fit23 of
all selected green photons at τ = 2.103 ns (γ, r₀, ρ fixed). Right: the VV|VH
decays (white), the Gaussian IRF (red), the non-burst background (blue) and the
model (green); top, the weighted residuals.
```

The status line says what the Auto IRF did and that a measured IRF/background
gives better lifetimes: the Gaussian stand-in leaves the systematic residual on
the rising edge seen here.

```{figure} figures/21_burst_mle_model_selection.png
:name: fig-21-burst-mle-model-selection
:width: 100%

The same `m000.bur` (green = routing 0/8) with **Fit model** switched to Fit24:
the parameter table now holds `tau1`, `gamma`, `tau2`, `A2`, `offset`. `A2`
fits to zero here — no evidence for a second lifetime.
```

```{figure} figures/21_burst_mle_synthetic_demo.png
:name: fig-21-burst-mle-synthetic-demo
:width: 100%

**Load example** (16 synthetic bursts, 2 ns input lifetime), then **Auto
IRF/background** and **Fit bursts** with Fit23: the decay fit gives 1.918 ns,
the per-burst lifetimes (bottom) spread over 1.82–2.06 ns. Finite counts, the fit
window and the estimated IRF keep the recovery from being exact.
```

## Result

A single burst carries only ~10³ photons, so its decay is sparse — which is
exactly why the fit is done by maximum likelihood rather than least squares. Read
against the donor-only lifetime $\tau_0$, the per-burst lifetimes separate static
from dynamic molecules.

```{figure} figures/burst_lifetime.png
:name: fig-burst-lifetime
:width: 95%

**Left:** the VV/VH micro-time histograms of one ~2000-photon burst with the IRF
and the reconvolved MLE model. **Right:** the E–$\tau$ plot. Static populations
sit *on* the static FRET line $E = 1-\tau/\tau_0$; a species exchanging between
two states falls on the **dynamic line**, which bows to the right because the
decay reports the intensity-weighted lifetime while $E$ follows the
species-weighted one.
```

## Splitting a burst by H2MM state

A burst that changes conformation part-way through has no single lifetime: fit
all its photons together and you get a blend that belongs to neither state. On
synthetic bursts holding a 3.6 ns and a 1.0 ns population, the all-photon fit
lands at 2.2 ns — a number nothing in the sample has.

Tick **Split by H2MM state** and each burst is additionally fitted once per
Viterbi state, using the same IRF, background and model as the ordinary fit. It
needs a segmentation in the same analysis folder (step 7, *Burst segmentation
(H2MM)*); without one the option says so and the batch proceeds normally.

In the burst workflow this is step 8, **Burst segment MLE**: the same wizard as
step 6 with the box already ticked, placed *after* the segmentation it consumes.
The control is shown only there — on step 6 it offered an option whose input did
not exist yet. Run standalone, the checkbox is always available.

The results are extra **columns on the same burst row** — `Tau S0 (G|G)`,
`Tau S1 (G|G)`, … beside the all-photon `Tau (G|G)`. That is deliberate and
it is the only shape that works: a burst table has one row per burst, every
companion is merged onto it by position, and the number of dwells varies from
burst to burst. **A sub-population is a column, not a row.** The burst stays the
unit of observation; the state is a label on the photons inside it.

Two practical points:

* A burst split by colour *and* state holds far fewer photons than the whole
  burst, so the per-state passes have their own **min ph.** floor. Below it the
  row is still written, with the photon counts and an empty fit — never omitted,
  because a missing row would shift every later burst against the `.bur` grid.
* Photons H2MM did not assign to any state (outside a burst, or dropped by its
  stream definitions) take part in the all-photon fit only.

## The lifetime of a state, not of a burst

A single burst's state holds tens of photons, so its per-burst lifetime is a
noisy number — useful as a distribution, not as a value to quote. The run
therefore starts by pooling: every burst's photons of state *i*, over the whole
measurement, added into one decay per detector, fitted once with the same model,
IRF and background. That is **the** lifetime of the state, and it is written to
`Info/state_lifetimes.csv` beside the analysis:

| Detector | Colour | State | Photons (parallel) | Photons (perpendicular) | Photons | Tau | 2I* | … |
|---|---|---|---|---|---|---|---|---|

One row per *state* — which is why it is a plain CSV in `Info/` and not a `…4`
companion. A companion carries one row per burst and is merged onto the burst
table by position; this table would misalign every burst after the first.

The pooled fit also runs **first**, and each state's fitted lifetime becomes the
start value for that state's per-burst fits. Started instead from the panel's
single guess, every state is pulled toward the same answer — the thing the split
exists to tell apart.

```{note}
Pooling only helps when the model describes the data. The pooled decay has tens
of thousands of counts, so a systematic mismatch that a 300-photon burst cannot
see — a shifted IRF, a decay that does not wrap into the excitation period —
shows up as a biased τ rather than as noise. If the pooled τ and the median
per-burst τ disagree strongly, look at the IRF before believing either.
```

## See also

- `chisurf/plugins/burst/burst_mle_analysis/`, `chisurf/core/fluorescence/mle/`.
- The ensemble decay fit: [Lifetime & anisotropy](10_lifetime_anisotropy_fitting.md).
- The same estimator per pixel: [confocal scan images](24_scan_images.md).
- Where the IRF and background come from: [background rates](15_background_rates.md).
- Concept: {ref}`concept-tcspc-lifetime`.
