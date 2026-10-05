---
type: Guide
title: Decays and correlation curves straight from a photon file
description: Histogramming the micro times of a TTTR file into a fluorescence decay (Histogram-Microtime, with the inter-photon filter for burst or background photons) and correlating its macro times into an FCS curve (the FCS correlator, with its algorithm choice and splits), how to read the result, and the tttrlib calls underneath.
tags: [guides, tttr, photons, tcspc, decay, correlation, file-formats, fcs]
---

# Decays and correlation curves straight from a photon file

A time-tagged file holds every photon's micro time, macro time and detector.
Two tools turn it into the two curves most analyses start from: a
**fluorescence decay** (a micro-time histogram) and a **correlation curve** (a
correlation of macro times). Both read the file directly, with no burst search
and no staging step, and both hand their curve to ChiSurf's dataset list.

For the theory, see {ref}`concept-tcspc-histogramming` (binning, channel
selection, pile-up, dead time and non-linearity) and
{ref}`concept-fcs-photon-correlation` (multiple-tau correlation, normalization,
and why two detectors remove afterpulsing).

## Open the tools

* **Histogram-Microtime**: **Spectroscopy → Decay → Decay Analysis**, panel
  **4. Histogram-Microtime** (`chisurf/plugins/tttr/microtime_histogram/`).
* **Correlator**: **Spectroscopy → Correlation → FCS**, steps **1. Channel
  Definitions** to **5. FCS Merger** (`chisurf/plugins/fcs/fcs_correlator/`).

Both read any container tttrlib reads: `.pto`, PTU, HT3, Becker & Hickl SPC,
Photon-HDF5 ({doc}`12_handling_tttr_files`). A headerless SPC file needs its
subtype (**TTTR format**, e.g. `SPC-130`).

These two tools replace the retired *TTTR: Generate Decay* and *TTTR:
Correlate* windows; every setting those had is here.

## Generate a decay

```{figure} figures/decay_gap_filter.png
:name: fig-decay-gap-filter
:width: 100%

**Histogram-Microtime** on a Becker & Hickl SPC-132 single-molecule DNA
measurement, detectors 0 (parallel) and 8 (perpendicular), with the
inter-photon filter on (max gap 20 000 ticks, 0.27 ms at the 13.5 ns clock):
only the photons of bursts went into the decays.
```

1. **Photon files** — **Files…**, **Folder…** or **Database…**; tick the files
   to sum. **Burst selections (BID/BUR)** restricts the photons to the bursts a
   burst search wrote.
2. **Detector** or **Parallel** / **Perpendicular** — the routing channels of
   the two polarization channels; untick **Polarization resolved** for one
   decay of all listed channels.
3. **Excitation window** — a micro-time gate from the detector setup (PIE), or
   all windows.
4. **Binning** — micro times are integer-divided by $b$, so the histogram has
   $n_\text{TAC}/b$ channels of width $b\,\Delta t$; **dt [ns]** shows the
   result. Bin until the channels are still several times narrower than the
   IRF ({ref}`concept-tcspc-histogramming`).
5. **Inter-photon filter** with **Max gap [ticks]** — keep a photon only when
   the next selected photon follows within the gap: the photons of bright
   stretches such as single-molecule bursts. **Invert (isolated photons)**
   keeps the opposite, the photons between bursts, which gives a background
   decay from the same measurement. The last selected photon is always dropped,
   because it has no successor to test.
6. **▶ Compute**, then **Save** or **Transfer to ChiSurf** (the decay becomes a
   dataset, ready for a lifetime fit). **G-Factor** and the **VV / VH shifts**
   build the combined VV + 2G·VH curve; **Polarization** picks what is saved.

## Correlate

```{figure} figures/fcs_correlator_step.png
:name: fig-fcs-correlator-step
:width: 100%

The FCS **Correlator** step on the bundled simulated measurement (**Example**
in *2. Files & Steps*; molecules cross the focus in about 0.25 ms):
detectors 0 × 1, three splits, `laurence`. The three split curves agree and
fall to $G = 1$ after the crossing time.
```

In **2. Files & Steps** add the files (or **Example**) and choose the optional
steps; in **4. Correlator**:

1. **Ch A**, **Ch B** — the detectors of the two streams (`0,1` merges two
   detectors into one stream), or a pair from **FCS Preset**. Different
   detectors give a cross-correlation, which carries no afterpulsing and no
   dead-time hole ({ref}`concept-fcs-photon-correlation`). **µt A**, **µt B**
   restrict each stream to micro-time windows (`0-100;200-300`), the PIE way.
2. **Bins** and **Cascades** — bins per cascade $B$ and number of cascades. The
   longest lag is about $B\,2^{\,n_\text{casc}}$ ticks: $9 \times 2^{20}$ ticks of
   13.5 ns is 127 ms. It should stay well below one split's duration.
3. **Splits** — the measurement is cut into this many equal pieces, each is
   correlated; the merger averages them and takes the errors from their spread.
4. **Method** — the tttrlib algorithm:
   * `laurence` — pair counting with the symmetric normalization, which removes
     the long-lag upturn when the intensity drifts {cite}`laurence2006` (the
     default);
   * `wahl` — multiple-tau on the time tags {cite}`wahl2003`;
   * `felekyan` — the variant of {cite}`felekyan2005`, with its own lag axis.
5. **Fine** and **µt bin** — correlate on the combined macro/micro clock, the
   micro times first divided by **µt bin**; the lag step becomes one TAC
   channel. Use it only when the macro clock is the laser period.
6. **Correlate**; **Next** correlates and goes on to **5. FCS Merger**, which
   averages the splits (errors: standard error of the splits, or the Suren noise
   model for a single curve) and writes the curve for fitting.

**Load filters…** switches to lifetime-filtered (FLCS) species correlation
({doc}`17_filtered_fcs`).

## Read the result

**A decay** ({numref}`fig-decay-gap-filter`) should rise over the IRF width,
peak, and fall to a flat background before the end of the range. Check before
fitting:

* **The flat level before the rise** is background and afterglow of the
  previous pulse. If the tail has not decayed by the end of the range, the
  laser period is too short for the lifetime and the fit needs periodic
  convolution ({ref}`concept-tcspc-lifetime`).
* **A spike or a step at the far end** is the non-linear end of the converter.
  Cut it with an **Excitation window** that ends before it.
* **A ripple that repeats across the whole curve** is differential
  non-linearity. It belongs in the fit's linearization table, not in extra
  lifetime components.
* **Photons per laser pulse** — the count rate over the repetition rate
  (a few kHz over tens of MHz, well below 0.01 %) — is what pile-up scales with. In
  single-molecule data use the rate inside bursts, which is far higher than the
  mean. Anything near a per cent needs the pile-up nuisance in the fit.

**A correlation curve** ({numref}`fig-fcs-correlator-step`) plateaus at 1 at long
lag, so its amplitude is $G(0) - 1 \approx 1/N$. Check:

* **A long-lag level above 1**, or a curve that has not flattened by the
  longest lag, means drift, bleaching or aggregates on the timescale of a split.
  Try `laurence`, fewer splits, or a cleaner stretch of the file.
* **A rise at 0.1–10 µs that disappears in the cross-correlation** of two
  detectors is afterpulsing, not triplet.
* **Scatter at short lag** reflects few photon pairs per bin. It averages down
  with measurement time, not with more splits.

## Where the curves go next

A decay is fitted with a lifetime model ({doc}`10_lifetime_anisotropy_fitting`)
after **Transfer to ChiSurf**; a merged correlation curve with an FCS model
({doc}`09_diffusion_fcs`).

## Headless

Both tools sit on tttrlib. The same curves:

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

# Histogram-Microtime: detector 0, binning 16
b = 16
keep = np.flatnonzero(route == 0)
# inter-photon filter (on, not inverted): photons whose next photon follows within 200000 ticks
gaps = np.diff(macro[keep])
keep = keep[:-1][gaps <= 200000]
decay = np.bincount(micro[keep] // b, minlength=-(-n_tac // b)).astype(float)
t_ns = np.arange(decay.size) * dt * b * 1e9     # channel start, ns

# Correlator: detectors 0 x 8, multiple-tau, B = 9, 20 cascades, no splitting
c = tttrlib.Correlator(t, method="wahl", n_bins=9, n_casc=20)
c.set_tttr(
    t.get_tttr_by_selection(t.get_selection_by_channel([0])),
    t.get_tttr_by_selection(t.get_selection_by_channel([8])),
)
tau_ms = np.asarray(c.get_x_axis())[1:] * 1e3   # seconds with a TTTR attached; lag 0 dropped
g = np.asarray(c.get_corr_normalized())[1:]
```

and into ChiSurf curves with the noise models the tools use:

```python
from chisurf.core.data import DataCurve
from chisurf.core.fluorescence.fcs import noise
from chisurf.core.fluorescence.tcspc import counting_noise

decay_curve = DataCurve(x=t_ns, y=decay, ey=counting_noise(decay=decay), name="decay_ch0")

T = (macro[-1] - macro[0]) * h.macro_time_resolution            # s
rate_khz = (np.sum(route == 0) + np.sum(route == 8)) / T / 1e3
sd = noise(tau_ms, g, T, rate_khz, weight_type="suren")          # the merger's single-curve model
fcs_curve = DataCurve(x=tau_ms, y=g, ey=sd, name="ccf_0_8")

fcs_curve.save("ccf_0_8.csv", file_type="csv")                   # or into the .pto
```

A `Correlator` built without a TTTR object reports its lag axis in integer
clock ticks instead; multiply by `h.macro_time_resolution`, or, with
`set_microtimes`, by the micro-time resolution.

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
- Tools: **Histogram-Microtime** (`chisurf/plugins/tttr/microtime_histogram/`;
  the filter is `gui/model.py: gap_selection`), the FCS **Correlator**
  (`chisurf/plugins/fcs/fcs_correlator/`) and its merger
  ({src}`chisurf/core/fluorescence/fcs/merge.py`); implementation
  `tttrlib.Correlator`, {src}`chisurf/core/fluorescence/fcs/__init__.py` (`noise`).
