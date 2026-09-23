---
type: Guide
title: 'Decays and correlation curves straight from a photon file'
description: Histogramming the micro times of a TTTR file into a fluorescence decay (TTTR — Generate Decay) and correlating its macro times into an FCS curve (TTTR — Correlate), with the settings of both tools, how to read their output, and the tttrlib calls they wrap.
tags: [guides, tttr, tcspc, fcs, correlation, photons]
---

# Decays and correlation curves straight from a photon file

A time-tagged file holds every photon's micro time, macro time and detector.
Two small tools turn it into the two curves most analyses start from: a
**fluorescence decay** (a micro-time histogram) and a **correlation curve** (a
correlation of macro times). Both read the file directly, with no burst search
and no staging step.

For the theory, see {ref}`concept-tcspc-histogramming` (binning, channel
selection, pile-up, dead time and non-linearity) and
{ref}`concept-fcs-photon-correlation` (multiple-tau correlation, normalization,
and why two detectors remove afterpulsing).

## Open the tools

Both are in **Plugins → TTTR**:

* **Generate Decay** (`chisurf/plugins/tttr/tttr_histogram/`)
* **Correlate** (`chisurf/plugins/tttr/tttr_correlate/`)

Each window has a **File** box on the left, the tool's settings under it, a list
of the curves made so far, and a plot on the right. **load** opens any container
tttrlib reads: `.pto`, PTU, HT3, Becker & Hickl SPC, Photon-HDF5
({doc}`12_handling_tttr_files`). Once a file is loaded the box shows what is in
it:

| Field | Meaning |
|---|---|
| **rep.[MHz]** | Laser repetition rate |
| **dt [ns]** | Width of one micro-time (TAC) channel |
| **nROUT** | Routing channels (detectors) that recorded photons, e.g. `0, 1, 8, 9` |
| **nTAC** | Number of micro-time channels |
| **Ph** | Photons in the file |
| **time [s] / kHz** | Measurement duration and mean count rate |

**nROUT** lists the detector numbers the settings below ask for.

## Generate a decay

```{figure} figures/tttr_generate_decay.png
:name: fig-tttr-generate-decay
:width: 100%

**TTTR: Generate Decay** on the Becker & Hickl SPC-132 test file (62 s,
184 k photons, 3.3 ps channels). Two decays were made, one for detector 0 and
one for detector 8. The plot is logarithmic in counts; its time axis is in
seconds, not nanoseconds (see *Known defects*).
```

Under **Channel Select**:

1. **Selection** — which photons go into the histogram, as an expression over
   the photon columns `ROUT` (detector), `TAC` (micro time), `MT` (macro time)
   and `EVENT`. Operators are `&`, `|`, `~`, the comparisons and arithmetic.
   The default `(ROUT==0)&(TAC<3000)` takes detector 0 and drops the end of the
   converter range. `(ROUT==0)|(ROUT==8)` sums two detectors; a parallel and a
   perpendicular decay for anisotropy are two separate runs.
2. **TAC div** — the binning factor $b$: micro times are integer-divided by
   it, so the histogram has $n_\text{TAC}/b$ channels of width $b\,\Delta t$.
   **nTAC** and **dt[ns]** under it show the result. Bin until the channels are
   still several times narrower than the IRF (see
   {ref}`concept-tcspc-histogramming`).
3. **dMTmin** with **on/off** — the inter-photon filter, in macro-time ticks.
   When on, a photon is kept only if the next selected photon follows within
   **dMTmin** ticks: the photons of bright stretches, such as single-molecule
   bursts. **invert** keeps the opposite, the isolated photons between bursts,
   which gives a background decay from the same measurement. The default
   200 000 ticks is 2.7 ms at a 13.5 ns macro clock.
4. Press **make decay**.

**Ch** echoes the detectors the expression selected (from its `ROUT==n`
terms), and **nPh** the photons that went into the histogram. The last selected
photon is always dropped, because it has no successor for the filter to test.

Each press adds a curve to the plot, named after the file and the detector
list (`BH_SPC132.spc_[0]`); the **Decay histograms** list should hold them too,
but does not (see *Known defects*).

## Correlate

```{figure} figures/tttr_correlate.png
:name: fig-tttr-correlate
:width: 100%

**TTTR: Correlate** after cross-correlating detectors 0 and 8 of the same file:
multiple-tau (`wahl`), $B = 9$, 20 cascades, 6 splits, Koppel error model. The
lag axis is in milliseconds, from 13.5 ns (one macro-time tick) to 127 ms; the
curve plateaus at $G = 1$. At lags below a microsecond this 3 kHz
single-molecule measurement has few photon pairs per bin, hence the scatter.
```

Under **Parameters**:

1. **Ch1**, **Ch2** — the detectors of the two streams, space-separated
   (`0 1` merges detectors 0 and 1 into one stream). Different detectors give a
   cross-correlation, which carries no afterpulsing and no dead-time hole; the
   same detector in both gives an autocorrelation, which has both
   ({ref}`concept-fcs-photon-correlation`). The defaults are `0` and `8`.
2. **Type** — the correlation algorithm, from tttrlib:
   * `wahl` — multiple-tau on the time tags {cite}`wahl2003`, the default;
   * `felekyan` — the variant of {cite}`felekyan2005`, with its own lag axis;
   * `laurence` — pair counting with the symmetric normalization, which removes
     the long-lag upturn when the intensity drifts {cite}`laurence2006`;
   * `default` — not a tttrlib method; it silently runs `wahl`.
3. **B** and **nCasc** — bins per cascade and number of cascades. The longest
   lag is about $B\,2^{\,n_\text{casc}}$ ticks: $9 \times 2^{20}$ ticks of
   13.5 ns is 127 ms. Raise **nCasc** to reach longer lags, **B** for a denser
   axis. The longest lag should stay well below one split's duration.
4. **Fine** and **bin.** — correlate on the combined macro/micro clock
   ($t = t_\text{macro}\,n_\text{TAC} + \mu$), with the micro times first
   divided by **bin.**. The lag step then becomes one TAC channel, and
   **nCasc** must grow by about $\log_2 n_\text{TAC}$ (12 for 4096 channels) to
   reach the same longest lag. Use it only when the macro clock is the laser
   period. See *Known defects* before using it.
5. **splits** — the measurement is cut into this many equal-time pieces, each
   is correlated, and the curves are averaged. Both streams are cut at the same
   times.
6. **w.res** — the error model: `Koppel` computes each point's standard
   deviation from the lag, the split duration, the count rate and the curve's
   own amplitude {cite}`koppel1974`; `none` gives uniform errors.
7. Press **correlate**. The bar shows the splits done; the curve appears in
   **Correlation-Curves** and in the plot when the last split finishes.

Each run replaces the previous curve.

## Read the result

**A decay** ({numref}`fig-tttr-generate-decay`) should rise over the IRF width,
peak, and fall to a flat background before the end of the range. Check before
fitting:

* **The flat level before the rise** is background and afterglow of the
  previous pulse. If the tail has not decayed by the end of the range, the
  laser period is too short for the lifetime and the fit needs periodic
  convolution ({ref}`concept-tcspc-lifetime`).
* **A spike or a step at the far end** is the non-linear end of the converter.
  Cut it with `TAC < …` in **Selection**.
* **A ripple that repeats across the whole curve** is differential
  non-linearity. It belongs in the fit's linearization table, not in extra
  lifetime components.
* **Photons per laser pulse** — the File box's count rate over the repetition
  rate (here 2.95 kHz / 73.55 MHz, 0.004 %) — is what pile-up scales with. In
  single-molecule data use the rate inside bursts, which is far higher than the
  mean. Anything near a per cent needs the pile-up nuisance in the fit.

**A correlation curve** ({numref}`fig-tttr-correlate`) plateaus at 1 at long
lag, so its amplitude is $G(0) - 1 \approx 1/N$. Check:

* **A long-lag level above 1**, or a curve that has not flattened by the
  longest lag, means drift, bleaching or aggregates on the timescale of a split.
  Try `laurence`, fewer splits, or a cleaner stretch of the file.
* **A rise at 0.1–10 µs that disappears in the cross-correlation** of two
  detectors is afterpulsing, not triplet.
* **Scatter at short lag** reflects few photon pairs per bin. It averages down
  with measurement time, not with more splits.

## Where the curves go next

A decay is fitted with a lifetime model ({doc}`10_lifetime_anisotropy_fitting`),
a correlation curve with an FCS model ({doc}`09_diffusion_fcs`). From these two
windows there is currently no working way to hand a curve on (see *Known
defects*), so compute it headlessly as below and save it, or use the
maintained tools that deliver into ChiSurf's dataset list: the FCS
**Correlator** (*Spectroscopy → Fluorescence Correlation Spectroscopy →
Correlator*, `chisurf/plugins/fcs/fcs_correlator/`) and **Histogram-Microtime**
(*Spectroscopy → Fluorescence decay*, `chisurf/plugins/tttr/microtime_histogram/`).

## Headless

Both tools are thin wrappers around tttrlib. The same curves:

```python
import numpy as np
import tttrlib

t = tttrlib.TTTR("measurement.spc", "SPC-130")   # or "PTU", "HT3", a .pto
h = t.header
dt = h.micro_time_resolution                     # s per TAC channel
n_tac = h.number_of_micro_time_channels
route = np.asarray(t.routing_channels)
micro = np.asarray(t.micro_times)
macro = np.asarray(t.macro_times)                # ticks of h.macro_time_resolution

# Generate Decay: detector 0, TAC div 16
b = 16
keep = np.flatnonzero(route == 0)
# dMTmin filter (on, not inverted): photons whose next photon follows within 200000 ticks
gaps = np.diff(macro[keep])
keep = keep[:-1][gaps <= 200000]
decay = np.bincount(micro[keep] // b, minlength=-(-n_tac // b)).astype(float)
t_ns = np.arange(decay.size) * dt * b * 1e9     # channel start, ns

# Correlate: detectors 0 x 8, multiple-tau, B = 9, 20 cascades, no splitting
c = tttrlib.Correlator(t, method="wahl", n_bins=9, n_casc=20)
c.set_tttr(
    t.get_tttr_by_selection(t.get_selection_by_channel([0])),
    t.get_tttr_by_selection(t.get_selection_by_channel([8])),
)
tau_ms = np.asarray(c.get_x_axis())[1:] * 1e3   # seconds with a TTTR attached; lag 0 dropped
g = np.asarray(c.get_corr_normalized())[1:]
```

and into ChiSurf curves with the tools' noise models:

```python
from chisurf.core.data import DataCurve
from chisurf.core.fluorescence.fcs import noise
from chisurf.core.fluorescence.tcspc import counting_noise

decay_curve = DataCurve(x=t_ns, y=decay, ey=counting_noise(decay=decay), name="decay_ch0")

T = (macro[-1] - macro[0]) * h.macro_time_resolution            # s
rate_khz = (np.sum(route == 0) + np.sum(route == 8)) / T / 1e3
sd = noise(tau_ms, g, T, rate_khz, weight_type="suren")          # the "Koppel" model
fcs_curve = DataCurve(x=tau_ms, y=g, ey=sd, name="ccf_0_8")

fcs_curve.save("ccf_0_8.csv", file_type="csv")                   # or into the .pto
```

A `Correlator` built without a TTTR object reports its lag axis in integer
clock ticks instead; multiply by `h.macro_time_resolution`, or, with
`set_microtimes`, by the micro-time resolution.

## Known defects

Found while writing this page (2026-09-23), in the tools, not in tttrlib. They
are why the headless route above is the reliable one.

* **Generate Decay: the time axis is in seconds**, labelled as if nanoseconds
  (the plot shows `0.000000002` for 2 ns). ChiSurf's lifetime models expect
  nanoseconds.
* **Generate Decay: TAC div is not applied to the axis.** The micro times are
  divided, but the histogram keeps $n_\text{TAC}$ channels of the undivided
  width, so with **TAC div** $= 16$ a 12 ns decay is drawn over 0.8 ns followed
  by empty channels. The displayed **nTAC** reads $(n_\text{TAC}+1)/b$ (4097 at
  $b = 1$). Use **TAC div** $= 1$ in the window.
* **Generate Decay: the Decay histograms list stays empty.** The list shows only
  curves tagged as TCSPC data, and the tool's curves are not, so nothing can be
  selected, saved or removed from it. The list and plot are also refreshed
  before the new curve is added, so the plot lags one press behind.
* **Correlate: the error bars are inverted.** The tool stores the reciprocal of
  the modelled standard deviation as the error, so the noisy short lags get
  small error bars and the long lags errors larger than $G$ itself (15 on a
  curve at 1.05 in {numref}`fig-tttr-correlate`). A fit weighted with them
  follows the noise.
* **Correlate: Fine mislabels the lag axis** by the number of TAC channels. The
  lags are micro-time ticks but are scaled by the macro-time clock, so a curve
  that ends at 31 µs is labelled 127 ms.
* **Both: Save in the curve list's context menu writes nothing.** It asks for a
  `.pkl` file, which the curve's save routine does not support, and returns
  without an error.
* **Neither tool has a `?` help page or a guided tour** (`gui/guide.json`); both
  are legacy Qt windows without an AutoForm spec.

## Using it well

**Select, then bin.** A decay is only as clean as its photon selection: one
detector, a micro-time window that excludes the converter's ends, and — for
single molecules — the burst filter. Binning afterwards costs nothing in
statistics.

**Cross-correlate two detectors** whenever the setup has them, even for one
colour. An autocorrelation carries the detector's afterpulsing and dead time
into exactly the lags where triplet and fast dynamics are fitted.

**Look at the splits before trusting the average.** A split that differs from
the others is a transient event in the file, and the average hides it.

## See also

- Theory: {ref}`concept-tcspc-histogramming` · {ref}`concept-fcs-photon-correlation`
  · {ref}`fundamentals-photon-counting`.
- Reading photon files: {doc}`12_handling_tttr_files`.
- Fitting what comes out: {doc}`10_lifetime_anisotropy_fitting` (decays) ·
  {doc}`09_diffusion_fcs` (correlation curves) · {doc}`17_filtered_fcs`
  (weighted, lifetime-filtered correlation).
- Tools: **TTTR: Generate Decay** (`chisurf/plugins/tttr/tttr_histogram/`),
  **TTTR: Correlate** (`chisurf/plugins/tttr/tttr_correlate/`); implementation
  `tttrlib.Correlator`, `chisurf.core.fio.fluorescence.photons.Photons.where`,
  {src}`chisurf/core/fluorescence/fcs/__init__.py` (`noise`).
