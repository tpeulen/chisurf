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

## Measured IRF and buffer from Data Selection

Files assigned to an **IRF** or **reference dye** row of *1. Data Selection* (per colour) are
Burst MLE's IRF sources for that colour's detectors (`irf_files`); **IRF from** chooses among
them (Auto: the reference dye first). A colour without its own files reads the other IRF files
on its channels, and a detector they show nothing keeps the estimate below. In the pipeline
there is no file list in Burst MLE: the files are Data Selection's. Files in the
**Buffer** row are the buffer (`bg_files`): they correct a scatter IRF for its background and are
the fit's background -- its histogram the shape, its rate `B_<detector>` the rate -- named in the IRF
source line ("G|G: IRF from the IRF measurement water_irf.ptu (buffer-corrected); background: the
buffer (buffer buffer.ptu: B_G|G = 1.40 kHz)"). Without a buffer the background is selected from the
measurement itself (see *The background* below). Without files in these rows the IRF and background are estimated as below
and the line says so. See {ref}`concept-reference-dye-calibration`.

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
**Window start** / **Window stop**, in bins of the setup's micro-time binning
(**Detector setup**; Burst MLE has no binning of its own). Until you set it,
the window is picked from the decay inside the detector's gate; what you set is
what is fitted, also past the gate. The model is drawn only there. **IRF range** (orange) is where the IRF the fit
convolves with is not zero, inside the IRF clip (**IRF start** / **IRF stop**).
Every edge is a line you can drag, in either half. Letting go of a line writes
its field and fits again. Changing a field moves its line, so the plot always
shows what is fitted. The window is a window for the fit too: the model is
normalised over its bins (`Fit2xSettings.fit_window`). The `fit2x` estimators
normalise over every bin they are given, and with the bins outside the window
merely zeroed they read them as observed zeros, pushed the model's tail (1.5 %
of a 4 ns decay cut at 18 ns) into the window and bent the fit: a reference dye
fitted at χ²ᵣ 3.6 instead of 1.5, the DNA13bp_3 bursts at 14.6 instead of 5.9.
**Min photons** (default 5) is the fewest photons a burst needs in the fit
window to be fitted.

Under the decay, on the same x axis (zoom or pan either and both follow), are the
**weighted residuals** of the fit window of each half,
w.res. = (data − model) / σ, with the Poisson σ the model expects, σ = √model
(√data in a bin where the model is zero, before a tail). A good fit scatters them
about the zero line within about ±2; a wave or a slope is a model, IRF or
background that does not describe the decay. The plot's title gives the reduced
chi-square of the fit windows, χ²ᵣ = Σ w.res.² / (bins − free parameters),
about 1 for a fit at the noise. Burst MLE minimises 2I*, not χ², so χ²ᵣ is the
check, not what is fitted.

```{figure} figures/21_burst_mle_residuals.png
:name: fig-21-burst-mle-residuals
:width: 100%

Burst MLE on DNA13bp_3 (RVZMT150, G|G, IRF from Rh110, G 1.436 from Data
Selection): a single lifetime (Fit23) on the summed decay of a FRET sample. The
background (grey, flat) is the flat + scatter model: no stretch of this
measurement is at the background level. χ²ᵣ = 14.8: one lifetime does not
describe a donor-only + FRET mix (below).
```

#### One lifetime and the summed decay

The decay shown is the sum of every burst of the file. Fitting it with one
lifetime checks the IRF, the shifts, G and the background only where the sample
has one lifetime -- a reference dye. A FRET sample is a mix: on DNA13bp_3 the
summed G|G decay needs two lifetimes (1.24 ns, 49 %, and 3.74 ns, a diagnostic
fit with shared VV/VH amplitudes and ρ 0.6 ns: χ²ᵣ 2.9, against 14.8 for Fit23),
and it needs no IRF shift (0 bins best; ±0.5 bin raise χ²ᵣ to 4). Burst-wise
the model is still one lifetime per burst; the summed decay's single-lifetime
χ²ᵣ is not the check of the instrument, the reference fit is.

```{figure} figures/21_burst_fit_steps.png
:name: fig-21-burst-fit-steps
:width: 100%

DNA13bp_3, G|G: Fit23 on the summed decay as shipped (χ²ᵣ 27.7: G 1.000, the IRF
cut at 2 % of its peak, the decay-shaped background, the window as zeroed bins),
with G 1.436 (14.6), the window honoured (5.9), the IRF kept whole (6.2), and the
flat + scatter background (14.9) -- the decay-shaped background had been a second
lifetime (gamma 0.21). Last: the two-lifetime diagnostic (2.9).
```

The **IRF** tab is there in Simple mode too, because the fit is only as good as
the IRF it convolves with. It holds one choice, **IRF from**, and for a typical
run nothing needs to be set: **Auto** takes the best there is, in this order --
the reference dye of Data Selection, the IRF measurement (water, Ludox), the
photons outside the bursts, an estimate from the burst decay itself. The other
choices take one of them; a choice whose measurement is missing is greyed, its
tooltip says why. Under it one short line says what the IRF is ("Rh110 ·
reference dye"; the files, lifetime and rotation in its tooltip), then the IRF
(thin: as extracted; thick: as the fit uses it) and **IRF tool**.

**IRF tool** opens the IRF in the IRF Estimation tool, which made it: the same
data, how it was extracted, and every setting of it (under **Advanced** there).
Whatever you estimate there comes back to Burst MLE for that detector and is
fitted at once; **IRF from** then says **IRF tool (tuned)**. Picking another
source afterwards asks once before the tuned IRF is discarded. The IRF's shape,
VH shift, clip and background levels are the tool's: Burst MLE has no fields for
them (it takes no background level off the IRF -- every source is already free
of it, and 0.02 of the peak cut a deconvolved IRF's tail -- and Opt can still
search the shifts).

With a reference dye in Data Selection the IRF's time shift is calibrated
before any fit, VV and VH on their own: the dye's decay is fitted with the IRF,
the shift free and the dye's lifetime fixed (from the dye database: Rh110
4.0 ns, Alexa 647 1.0 ns; fitted when it has none). A dye measured at
single-molecule conditions is preferred -- a SPAD's timing moves with the
count rate, so only a reference at the bursts' rates has their timing offset --
else the bulk one; a bulk reference at a much higher rate than the bursts is
marked ⚠ (its rate and the bursts' in the tooltip and the report). The status line then says **shift calibrated
(Rh110)**; the shifts, the dye, the files and the lifetime's source are in its
tooltip and in the calibration report. There is nothing to set; the IRF tool
shows the shifts under **Advanced** and takes your own.

Then the reference dye is fitted with that IRF and **the burst model**: one
amplitude for VV and VH, a flat background each, the shifts free, the lifetime
fixed, the rotation read from the dye and the detector's G, l1, l2
(`reference_fit`). A dye of one lifetime must fit at χ²ᵣ ≈ 1 -- if not, the IRF,
G or the rotation is wrong, and every burst fit inherits it. The status line
shows **reference fit χ²ᵣ**, the tooltip the same fit with G free (the G the
reference asks for); ⚠ when the two disagree: apply Data Selection's G. On
Rh110_thick_1 (bulk, 61 kHz) with the setup's G 1.000 it is 309 (G free: 1.428,
χ²ᵣ 1.40); with Data Selection's G 1.436 it is 1.45. The IRF tool's **Reference
fit** view draws it with its residuals; the calibration report keeps its χ²ᵣ,
G and residuals.

```{figure} figures/21_irf_tool_reference_fit.png
:name: fig-21-irf-tool-reference-fit
:width: 100%

The IRF tool opened from Burst MLE's **IRF tool** on Rh110_thick_1: the
**Reference fit** view, the dye fitted with the IRF deconvolved from it, the
lifetime fixed at 4.00 ns and G 1.436, χ²ᵣ 1.45 (G free: 1.428, 1.40).
```

```{figure} figures/21_reference_fit_steps.png
:name: fig-21-reference-fit-steps
:width: 100%

Rh110_thick_1 fitted with Fit23 itself, τ 4.00 ns fixed: as shipped χ²ᵣ 269
(G 1.000), with G 1.436 6.1, the window honoured 3.6, the IRF kept whole (no
2 % level taken off it) 1.49; last, the reference fit Burst MLE now shows, 1.45.
What is left: a slight rise of VV late in the window (the dye's 4.02 ns from its
tail against the database's 4.0 ns) and a bulk measurement at 61 kHz.
```

```{figure} figures/21_burst_mle_irf_auto.png
:name: fig-21-burst-mle-irf-auto
:width: 100%

The **IRF** tab on DNA13bp_3 with Rh110_thick_1.ptu in Data Selection's
reference-dye row: **IRF from** Auto took the reference dye (τ 4.02 ns from its
tail, rotation 0.17 ns, deconvolved -- in the tooltip) and calibrated the IRF's
time shift against it (VV +0.04, VH +0.06 bins, Rh110's 4.0 ns fixed). No IRF
measurement was made, so that choice is greyed. Thin: the IRF as extracted;
thick: as fitted.
```

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

In the pipeline the IRF of each detector is taken, in this order (Auto), from:

1. **A reference dye of known lifetime** (Rh110, Rh6G, Fluorescein, Alexa488,
   Alexa647, Cy5; names and lifetimes in `chisurf/core/fio/reference_dyes.yaml`),
   Data Selection's reference-dye row of the detector's colour. It comes first
   (the owner's choice): it is measured in the same conditions as the sample.
   Each polarisation of its decay is the IRF convolved with the dye's rotating
   exponential, (1 + 2r(t))·exp(−t/τ) in VV and (1 − r(t))·exp(−t/τ) in VH; the IRF is recovered by Richardson–Lucy
   deconvolution of that kernel, τ fitted to the tail of VV + 2VH and the
   rotation read from VV and VH ([extracting the instrument
   response](../concepts/irf_extraction.md)). The exact difference used before,
   IRF[i] = D[i] − exp(−Δt/τ)·D[i−1], gave the noisy, broad hump of a single
   polarisation's rotation; on a simulated Rh110 its VV IRF was 0.12 ns early
   and a 2.5 ns sample came out 2.63 ns (now 2.50 ns). Of several dyes, each
   detector takes the one with the most photons in its gate: Rh110 for the
   green detectors, Alexa647 for the red detectors of a PIE set-up. A colour
   without a reference dye falls through to the next source for that colour only.
2. **A scatter measurement** (Data Selection's IRF row, or a file named `H2O`,
   `water`, `Ludox`, `scatter`, `IRF` or `prompt` beside the data). The buffer
   measurement, when there is one, is scaled to the scatter's acquisition time
   and subtracted; then the flat floor. **IRF from › IRF measurement** takes it
   when a dye is there too.
3. **The photons outside the bursts**, fitted with a skewed Gaussian. Those
   photons are mostly fluorescence of dim molecules, not scatter, so only their
   prompt is used.
4. **The burst decay itself**, the last resort, when fewer than 500 photons lie
   outside the bursts in the detector's gate: the blind estimate of
   [IRF Estimation](irf_estimation.md) (a truncated exponential fit and
   Richardson-Lucy deconvolution), trimmed to its prompt by a skewed Gaussian.

Every one of these is extracted by the **IRF Estimation** tool, the one
implementation in ChiSurf (`irf_estimator/core/extraction.py`); Burst MLE only
histograms the files with its reader settings, channels and binning. **IRF tool**
in the **IRF** tab opens that tool with what the current detector's IRF was
extracted from -- the same histograms, gate and source -- so it shows the same
IRF with its lifetime, rotation and counts, and its settings can be tried there.

```{figure} figures/21_burst_mle_irf_tuned.png
:name: fig-21-burst-mle-irf-tuned
:width: 100%

After **IRF tool**: an IRF estimated there (here with another rotation of the
dye, to show the round trip) came back; **IRF from** says **IRF tool (tuned)**
and the decay was fitted with it.
```

```{figure} figures/21_burst_mle_irf_difference.png
:name: fig-21-burst-mle-irf-difference
:width: 100%

The same IRF by the exact difference used before (and the tab's former
fields): a noisy hump, cut off where the difference sank into its noise.
```

A detector that a reference file shows nothing (a green dye in the red
detectors after the red pulse) falls back to the next source. The **IRF** tab
names the source of the selected detector. The scatter fraction **gamma** is
fitted, not fixed: on DNA13bp_3.ptu a fixed gamma of 0.1 gave 2I* = 570 and a
free one 133. With the IRF from Rh110, 2I* was 87.

#### Measured IRF, buffer, Opt, Save fit

#### The background

The photons outside the bursts are not a buffer. Molecules too dim to make a
burst pass the focus, and every burst has flanks (the molecule entering and
leaving) the search left out: their histogram is a fluorescence decay, and as
the fit's background it gave a single-lifetime fit a second lifetime through
gamma. The background of the fit is therefore, in this order:

1. the **buffer** of Data Selection: its histogram is the shape, its rate the rate;
2. the **strict background selection** of the measurement
   (`strict_background_mask`, shared with Burst IRF & Background): every burst
   widened by 2 ms plus half its duration on both sides, then the local count
   rate over 10 photons (as in the burst search) and every stretch faster than a
   Poisson background reaches with 1 % probability (≈ 2.5 × its rate) dropped;
   the rate starts as the exponential tail of the inter-photon times and is
   re-estimated from the stretches kept until it holds still; when the kept
   photons' histogram still holds fluorescence (more than 10 % of it, by a fit of
   flat + scatter + exponentials) the threshold is lowered until it does not or
   too little is left. Kept when it is a background's histogram: its photons over
   its time (corrected for the background's own fluctuations the cut drops);
3. else a **flat + scatter model** (`flat_scatter_background`): the flat level
   before the prompt (and in the gate's last tenth, the lower), a scatter of the
   IRF's shape from that same fit -- never the decay.

Its rate times the time in the bursts is the count the plot draws. The fit text
names which it is ("Background: 1.9% of the photons in the window (flat +
scatter model)"); the detector line gives its rate, the rate of all photons
outside the bursts and the share of the time the strict selection kept, or ⚠
when no stretch is at the background level; the status line says why
(`MleSession.background_info`, `strict_background`). On a simulation (1 kHz flat + scatter, dim molecules
and bursts) the strict selection keeps 80 % of the time at 1.04 kHz with the
buffer's shape, where the photons outside the bursts give 1.81 kHz and a decay.
On DNA13bp_3 no stretch is at the background level: the sub-threshold molecules
are in the focus nearly all the time (their own long gaps give a 3.5 kHz
"background"); at a local rate below 2.6 kHz, 3 % of the time, the flat floor
falls to a fifth of the non-burst one -- that floor is the molecules'
afterpulsing, not dark counts -- but the prompt still decays, so the model is
used.

```{figure} figures/21_background_selection.png
:name: fig-21-background-selection
:width: 100%

Left, simulated: the photons outside the bursts (blue) against the strict
selection (orange) and the buffer that made them (dashed). Right, DNA13bp_3 G|G
VV (no buffer measured): outside the bursts, the strict selection at its own
rate, a stricter one (3 % of the time) and the flat + scatter model the fit uses.
```

The tab **IRF/BG files** replaces the IRF estimate from the non-burst
photons by measurements; background (buffer) files correct a scatter IRF
for its background and are the fit's background. An IRF file may be a scatter or a reference dye: a dye
is recognised by its name and its IRF is recovered as above. **Add IRF files** and **Add background files** take any
TTTR measurement; each detector reads its own channels, the histograms of
several files are summed, the IRF is normalised to one per polarisation and the
buffer to counts per second. With **one for all** the files serve every
detector, without it only the selected one. **Auto IRF/background** keeps a
measured IRF; a new binning in the setup re-reads the files. **Save VV/VHs** writes each file's VV|VH histogram beside it
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
newest run). Every finished **Fit bursts** writes the per-detector fits at once
-- in the pipeline, which has no Save button, too -- as members of the run they
were fitted from (`<run>/mle G|G`, `<run>/mle R|G`, ...: one row per burst,
skipped bursts included, derived from that run's burst table, as its 2CDE is),
with the pooled states and the IRF/background curves (`<run>/irf G|G`). So ndX
opens the run with `Tau (G|G)`, `Tau (R|G)`, `Tau (R|R)`, `gamma`, `r0`, `2I*`
... beside the burst columns, the workspace lists them under that run, and a new
search (another run) does not inherit them; a refit replaces them. **Save
results** writes them again. **Export legacy...** in the PTO inspector makes
`bg4`/`br4` folders on request. **Split by H2MM state** still reads
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
the per-burst lifetimes spread over 1.82–2.06 ns. Finite counts, the fit
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
