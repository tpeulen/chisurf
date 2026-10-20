---
type: Guide
title: 'FCS toolbox: from photon stream to a curve worth fitting'
description: Correlating TTTR photon streams in the Spectroscopy:FCS tool — channel definitions, photon filtering, chunked multi-tau correlation, merging repeats with error bars — and converting correlation files between formats.
tags: [guides, fcs, photons, fitting, tttr, correlation, uncertainty, file-formats]
---

# FCS toolbox: from photon stream to a curve worth fitting

A correlation curve is only as good as three choices made before any fit:
which photons are correlated with which, which stretches of the measurement are
kept, and how the error bars were obtained. The **FCS** tool makes those choices
explicit, one step at a time, and ends with a `.cor` file the FCS fit reads.

For what the curve means and how its error bars are estimated, see
{ref}`concept-fcs-correlation` and in particular
{ref}`concept-fcs-error-bars`. Fitting the result is
{doc}`09_diffusion_fcs`.

## Open the tool

**Spectroscopy → Correlation → FCS**. The window is a left rail holding the
five-step workflow this guide walks through:

* **Correlator** —
  *Channel Definitions → Files & Steps → Photon / Burst Filter → Correlator →
  FCS Merger*. It opens on *Files & Steps* (**Example** there adds a simulated
  measurement whose curve falls near 0.5 ms). Its photon file and JSON
  parameters live in `demos/fcs_correlator` under the ChiSurf settings folder;
  `make_demo()` from `chisurf.plugins.fcs.fcs_correlator.demo` returns the
  primary SPC path (`overwrite=True` regenerates it). The tour first reveals
  this Files page and waits for your **Example** click. **Next** runs the open step where
  it has a run (the Correlator correlates) and then moves on, **Back** goes back,
  and **>>** runs the remaining steps in order (press it again to stop). A step
  switched off in *Files & Steps* is grey and skipped. **Help** and **Guide** at
  the top of the rail open a short help (linking back here) and a guided tour.

The other FCS tools are buttons of their own in the same ribbon group, each in its
own dock with its own **?** help and **Guide**: *2D-FLCS* and *FCS Filter
Calculator* ({doc}`17_filtered_fcs`), *Lifetime-FCS Simulator*, *Burst-wise FCS*
({doc}`16_fret_fcs`) and the *Diffusion/Volume Calculator* (the
$\tau_D \leftrightarrow D$, volume and concentration calculator,
{ref}`concept-fcs-correlation`). A ⚠ marks a tool flagged experimental.

The controls are native emtk/AutoForm surfaces: the shell docks the same `FcsHubApp`
the standalone launcher opens. Closing the window closes its step apps once.

For a desktop with a working GPU/display, launch the workflow directly:

```bash
pixi run -e test python -m chisurf.emtk --plugin fcs_correlator --size 1200x800
```

The same launcher accepts `fcs_merger` for the merger alone,
`fcs_filter_calculator`, `flc-2d`, `fcs-lfcs-sim`, `fcs_calculator` and
`burst_fcs_correlator` for the other FCS tools.
These are manifest IDs, not separate `csg_fcs_*` commands. Native desktop
launch needs a display; offscreen drawing (`emtk.testing.Driver`) is for captures,
not a substitute for the desktop renderer. The Python calculations
below run without a window.

## 1. Channel Definitions

A *detector setup* names groups of routing channels (and micro-time ranges) as
logical detectors — *Green* = channels 0 and 8, *Red* = 1 and 9. This step pairs
those detectors for correlation.

```{figure} figures/fcs_toolbox_channels.png
:name: fig-fcs-toolbox-channels
:width: 100%

Channel definitions for a two-detector setup: the two autocorrelations and the
green × red cross-correlation, each with its own multi-tau settings.
```

* **Detector setup** — the setup to pair. Setups themselves are created in the
  channel-definition wizard; **🔄 Reload** re-reads them.
* **A / B / Add** — pick two logical channels and add the pair. Equal names make
  an autocorrelation (named `<A>_ACF`), different names a cross-correlation
  (`<A>×<B>`); the label is optional.
* **Bins, Cascades, Fine** per pair — seeded from the correlator defaults.
* **Public** — share the setup's pairs with every user of the metadata database;
  only the owner can change it.
* **💾 Save** stores the pairs per setup (in the metadata database, or
  `fcs_channel_setups.json` in the settings folder when none is configured). The
  Burst-wise FCS tool reads the same pairs.

The selected detector setup is handed to the Correlator's **A**/**B** selectors.
Check the actual **Ch A**/**Ch B** routing channels and micro-time gates before
running, especially when changing detector or PIE selections.

## 2. Files & Steps

```{figure} figures/fcs_toolbox_files.png
:name: fig-fcs-toolbox-files
:width: 100%

One photon stream loaded, both optional steps switched on.
```

* **Files** — drop photon streams (`.ptu`, `.ht3`, `.spc`, `.hdf`/`.h5`), a
  folder, or pick from the database; untick a file to leave it out. Several
  checked files are **concatenated** into one stream before correlating, so they
  must come from the same instrument settings. The container type is detected
  per file.
* **Count rate/burst filter** — enables step 3. Off by default: diffusion FCS of
  a homogeneous solution wants every photon. It is disabled when a burst-ID
  (`.bst`) file is selected, because the bursts are already chosen.
* **FCS merger** — enables step 5. On by default.

A disabled step is greyed out in the rail.

### Time regions

```{figure} figures/fcs_toolbox_regions.png
:name: fig-fcs-toolbox-regions
:width: 100%

The example measurement with two drawn regions: 3.5 s of its 5 s are correlated.
```

Below the step switches is the count-rate trace of one file. Which photons
enter the correlator is drawn on it, per file:

* **The file table** — one row per added file or folder, a folder's files under
  it; **Use** ticks a row in or out, **Regions** counts the time regions drawn
  on each file (a folder: on its files; 0 is the whole file). The selected row
  is the file whose trace is drawn, one file at a time — a folder row shows
  its first file.
* **✏ Draw** — drag across the trace to add a region, drag a region's edge to
  move it, right-click a region to remove it. Off, the trace pans and zooms as
  any plot; drawing keeps the view you left it at.
* **Clear regions** — the file is used whole again. **To all files** gives
  every other file the regions of this one (repeats of one measurement series).

A photon is kept when its macro time lies inside one of its file's regions
(start inclusive, stop exclusive, seconds from macro time 0). A file without
regions is used whole, so drawing nothing changes nothing. The regions cut the
stream *before* the photon filter of step 3 and after it alike: neither
**invert** nor gap filling there reaches outside them. Use them to drop what the
burst filter cannot judge: an aggregate crossing, a bubble, the first seconds
of photobleaching, a stretch where the focus drifted.

## 3. Photon / Burst Filter

Selects which photons reach the correlator. Every change recomputes the
selection and the "*kept / total*" line at once.

```{figure} figures/fcs_native_bh132_filter.png
:name: fig-fcs-toolbox-filter
:width: 100%

The complete measured BH132 stream (183 657 photons) in the native filter:
burst mode, minimum ten photons, photon window five, maximum inter-photon time
1.5 ms. The selection keeps 96 774 photons (52.7%). The upper plot shows
selected and removed photon intervals; the lower plot shows the count-rate
traces. No photon-index truncation was used for this render.
```

* **Channels / µt range** — routing channels and micro-time windows to keep;
  empty channels means all.
* **min / max dMT** with **use min / use max** — thresholds on the time between
  consecutive photons. *max dMT* is also the time window of the burst and
  count-rate modes.
* **Mode**
  * *burst* — keep runs of at least **Min photons** whose local rate, over a
    **Photon window** of photons, beats *max dMT*: FCS inside bursts.
  * *count_rate* — reject windows with more than **Min photons** photons in
    *max dMT*: removes aggregates and bright spikes, the usual reason to filter a
    solution measurement.
  * *bocpd*, *kalman*, *cusum* — change-point burst detection on a binned trace;
    their parameters appear when selected. CUSUM defaults: background 1000 photons/s
    (Hz, not kHz; set it near the measured background), s/b ratio 0 (estimated
    from the data), alpha = beta = 0.05 (false-alarm and missed-detection
    probabilities). **Fill gaps** bridges short
    rejections.
* **enable** switches the burst/count-rate part off while keeping the channel,
  µt and dMT selections. **invert** keeps the rejected photons — note that it
  inverts the whole selection, channel and dMT cuts included.
* **Plot settings** — the count-rate trace bin (*MCS bin*) and the photon range
  of the inter-photon-time plot.

With the filter on, step 4 correlates only the kept photons of every file.

## 4. Correlator

```{figure} figures/fcs_native_bh132_correlator.png
:name: fig-fcs-toolbox-correlator
:width: 100%

The native FCS workflow displays two measured BH132 chunk curves, with channels
0, 1 × 8, 9, nine bins and twenty cascades, Laurence normalization. The current
workflow selection contains 96 774 of the fixture's 183 657 photons; the plot
retains the earlier computed curves until **Correlate** is pressed again.
The lag axis is in ms; these are measured photons, not the **Example** simulation.
```

* **Ch A / Ch B** — routing channels of the two streams, comma- or
  space-separated. Equal channels give an autocorrelation. Empty fields mean all
  channels.
* **µt A / µt B** — micro-time windows per stream, `start-end;start-end`, in
  micro-time bins. This is how PIE/ALEX windows are selected, and how a
  cross-correlation between two halves of one detector's decay is set up.
* **Bins** — lag channels per cascade; **Cascades** — number of multi-tau
  cascades (each doubles the lag spacing). The longest lag is about
  $\text{Bins}\times 2^{\text{Cascades}}$ macro-time ticks; set it past the
  slowest process but not past a chunk.
* **Splits** — cut the stream into this many equal-photon chunks and correlate
  each. This is what gives the merger repeats to average and to reject; one split
  means one curve and no error bars.
* **Fine** / **µt bin** — correlate on the micro-time grid for ns-FCS
  (antibunching, rotation; {doc}`06_nsfcs_second_order`); **µt bin** coarsens the
  micro-time axis first.
* **Load filters… / Unload / Filter Calc…** — switch to lifetime-filtered
  correlation: load a Filter-Calculator `.json` (or a `.npy`/`.npz`
  `(n_species, n_bins)` matrix) and **A**/**B** pick *species* instead of
  channels. Equal species give that species' autocorrelation, different ones
  the species cross-correlation ({doc}`17_filtered_fcs`). *Filter Calc…* opens
  the FCS Filter Calculator in its own dock with the checked files as its mixed
  decay, on the correlator's micro-time binning (a mixed decay loaded there by
  hand is kept). It is greyed when no ChiSurf window is open to host it.

Press **Correlate**. Each chunk is normalized per lag by the count rates in the
overlapping stretches of the two streams rather than by the global mean
{cite}`laurence2006`, which removes the upturn at lags approaching the chunk
length. Lags longer than the chunk's own duration carry no photon pairs worth
the name and are set to $G = 1$, so all chunks keep one lag grid and stay
averageable. The curves plateau at $G = 1$ (the $\langle II\rangle/\langle
I\rangle^2$ convention), lags are in ms.

## 5. FCS Merger

The chunks arrive here directly; **Browse… / Open** instead loads a folder of
`.cor` (or legacy `.json.gz`) chunk files.

```{figure} figures/fcs_native_bh132_merger.png
:name: fig-fcs-toolbox-merger
:width: 100%

Six repeats produced from the measured BH132 fixture, with the third excluded;
the native merger averages the remaining five. Both standalone merger plots
and the workflow's Correlator view label lag time in ms.
```

* The table lists each curve with the count rate of both streams and its
  duration. **Use** includes or excludes it; selecting a row highlights its
  curve. A chunk whose count rate stands out is where an aggregate or a
  focus jump went through — untick it.
* The merged curve is the point-by-point **mean** of the ticked curves, with the
  standard error of the mean as its uncertainty; acquisition times add and the
  count rate is duration-weighted (see {ref}`concept-fcs-error-bars`). The first
  lag point is dropped. With a single curve there is no spread and no
  uncertainty column is written; the fit then falls back to the photon-noise
  model.
* **Save** writes `<folder>.cor` next to the chunk folder (**Save as…** elsewhere) — for a
  correlated stream, `cr5.cor` beside the data file.
* **Add to ChiSurf** saves (if needed) and loads that file as an FCS dataset,
  ready for {doc}`09_diffusion_fcs`.

### The settings file beside every `.cor`

Every saved `.cor` gets `<name>.cor.json` beside it: what computes the same
curve again from the raw photon streams.

| Key | What it holds |
|---|---|
| `inputs` | each raw file: path, size, SHA-256 and its time regions |
| `reading` | container type, detector setup and channel definitions |
| `photon_filter` | the step-3 settings, `null` when the raw photons were correlated |
| `correlator` | bins, cascades, splits, method, channels, micro-time ranges, lifetime filters (path and checksum) |
| `merge` | which correlated pieces (`chunks`) the mean averaged |
| `output` | the `.cor` file name and its SHA-256 |

The settings are those at **Correlate**: changing a field afterwards does not
change what the record says was used. A `.cor` merged from a folder of
correlation files names those files instead (`"source": "correlations"`); it can
be re-merged, not re-correlated.

Reproduce a curve headlessly:

```bash
python -m chisurf.plugins.fcs.fcs_correlator.provenance merged.cor.json -o again.cor
```

It refuses a raw file whose checksum differs from the record's, prints the
largest difference to the recorded `.cor` (`max |ΔG|`, 0 when nothing changed)
and writes `again.cor` with its own settings file. From Python:

```python
from chisurf.plugins.fcs.fcs_correlator.provenance import reproduce

merged, pieces = reproduce("merged.cor.json")  # merged["x"] in ms, merged["y"] = G
```

ChiSurf's Kristine `.cor` writer, reader and FCS fitter use lag time in
milliseconds. For this BH132 fixture, the header's raw macro-time tick is
13.5 ns, or 0.0000135 ms; the measured-repeat producer converts its
TTTR-aware correlator's seconds axis to ms before writing. An earlier
seconds-based diagnostic fixture was corrected at its producer. That fixture
is not evidence that existing user `.cor` files need a factor-of-1000 conversion.

The standalone **FCS-Merger** window (`chisurf/plugins/fcs/fcs_merger/`) has the
same table for a folder of chunks you already have: drop the folder (or one of
its files) on the window, or **📂 Open folder…**. A click on **Use** or a double
click on a row includes or excludes a curve, and **Delete** removes it from the
list (not from disk). **Target** is the file **💾 Save** writes, `<folder>.cor`
beside the folder by default; **Save as…** writes elsewhere.

On first use, the standalone native merger opens at **1100 × 720** pixels;
saved window and dock geometry takes precedence on reopening. Reopen the curve
folder and check the **Use** selections before saving a merge. Native window
preferences are not a saved analysis session. Resizing does not change the
screened curves, the averaging calculation or the exported lag-time units.

```{figure} figures/fcs_merger_primary_window.png
:name: fig-fcs-merger-primary-window
:width: 100%

The standalone native merger at its declared first-use size: six measured
BH132 repeats, with the third excluded and the remaining five averaged.
```

Averaging assumes every ticked curve measures the same thing: the same
concentration (the mean of $1/N$ is not $1/\bar N$), the same focus (a drifting
$\tau_D$ broadens the mean) and no bleaching trend (a slow component every chunk
shares survives the average).

## The `.cor` file

The merger writes the Kristine layout, one row per lag, tab-separated:

| Column | Content |
|---|---|
| 1 | lag time $\tau$ in ms |
| 2 | $G(\tau)$ |
| 3 | row 1: acquisition time in s; row 2: mean count rate per stream in kHz; zeros below |
| 4 | uncertainty $\sigma(\tau)$ (optional) |
| 5 | mask (optional; needs column 4) |

On reading, rows with $\tau \le 0$ are skipped, and a missing column 4 — or a
zero, negative or non-finite entry in it — is replaced by the Koppel
photon-noise estimate computed from columns 1–3 {cite}`koppel1974`. That is why
the acquisition time and count rate travel in the file.

## Converting correlation files

Curves from other correlators and fitting programs convert headlessly with
`fcs-convert` (a `csc` subcommand; there is no GUI):

```bash
csc fcs-convert -i ALV-7004USB_ac01_cc01_10.ASC -it alv -o alv.cor -ot kristine
csc fcs-convert -i PyCorrFit_CC_A488.csv -it pycorrfit -o a488.yaml -ot yaml
```

| Readers (`-it`) | Writers (`-ot`) |
|---|---|
| `alv` (ALV `.ASC`), `confocor3` (Zeiss `.fcs`), `pqres` (SymPhoTime), `pq.dat` (PicoQuant `.dat`), `pycorrfit` (`.csv`), `china-mat` and `ries-mat` (MATLAB `.mat`; the latter from Ries' scanning-FCS tools), `sin` (correlator.com), `kristine` (`.cor`), `csv`, `yaml` | `kristine`, `yaml` |

What survives:

* **Lag, $G$, uncertainty, mask** — exactly, in both writers (checked by
  round-tripping the test files through `kristine`).
* **Several curves per file** (ALV auto + cross, SymPhoTime groups) —
  `kristine` holds one curve per file and writes `<name>_00.cor`, `_01`, …;
  `yaml` keeps them together.
* **Acquisition time and count rate** — kept if the source has them. If not
  (`.pqres` lacks the count rate, `pq.dat` both), `kristine` writes $1$ in their
  place with a warning, and any later fallback noise estimate is then wrong.
* **Intensity traces, headers, measurement names** — dropped by `kristine`
  (the file name becomes the curve name); `yaml` keeps the metadata.
* **The offset convention is not harmonized.** The ALV reader adds 1, so ALV
  curves plateau at 1 like ChiSurf's own; PyCorrFit, SymPhoTime and PicoQuant
  `.dat` curves plateau at 0 and stay that way. Fit the offset (`b`) or know
  which convention you compare.
* **Uncertainties** — taken from the file where it has them; otherwise the
  photon-noise model fills them in on reading, and that model then travels into
  the written file as if measured.

:::{admonition} Known issues
:class: warning
The `yaml` reader is not implemented, so a `yaml` file cannot be read back
(convert *to* `yaml` only for archiving). `-v` turns verbose output on but
`--verbose` turns it off (a flag-pair spelling slip).
:::

## Headless

The workflow in Python — correlate ten chunks of a stream, merge, write the
`.cor` the GUI would:

This example uses ten chunks, four bins and twenty-six cascades; it illustrates
the same normalization and averaging API with different settings from the
two-chunk screenshot above.

```python
import numpy as np
import tttrlib
from chisurf.core.fluorescence.fcs.merge import (
    compute_average_correlations, save_mean_correlation)

tttr = tttrlib.TTTR("test/data/tttr/BH/132/BH_SPC132.spc")
green, red, n_chunks = [0, 8], [1, 9], 10
size = len(tttr) // n_chunks
curves = []
for k in range(n_chunks):
    t = tttr[k * size:(k + 1) * size]
    w_a = np.isin(t.routing_channels, green).astype(float)
    w_b = np.isin(t.routing_channels, red).astype(float)
    corr = tttrlib.Correlator(n_bins=4, n_casc=26, make_fine=False)
    corr.method = "laurence"                 # per-lag normalization
    corr.set_macrotimes(t.macro_times, t.macro_times)
    corr.set_weights(w_a, w_b)
    dt_ms = t.header.macro_time_resolution * 1e3
    x = corr.x_axis * dt_ms
    y = np.asarray(corr.correlation, dtype=float)
    mt = t.macro_times
    duration_ms = (np.percentile(mt, 99.9) - np.percentile(mt, 0.1)) * dt_ms
    y[x > duration_ms] = 1.0                 # lags longer than the chunk
    curves.append({"x": x, "y": y, "duration": duration_ms / 1e3,
                   "channel_a": {"counts": w_a.sum()},
                   "channel_b": {"counts": w_b.sum()}})

merged = compute_average_correlations(curves)   # mean, SEM, summed duration
save_mean_correlation(merged, "cr5.cor")
```

Merging a folder of chunk files, and converting, are one call each:

```python
from chisurf.core.fluorescence.fcs.merge import merge_folder
from chisurf.plugins.fcs.fcs_convert.cli import convert_fcs

merge_folder("path/to/cr5", output="path/to/cr5.cor")
convert_fcs(input_filename="scan.ASC", input_type="alv",
            output_filename="scan.cor", output_type="kristine")
```

Reading any supported file, with a chosen noise model for curves that carry no
uncertainty (`"file"` keeps what the file has; `"suren"` is the Koppel-type
photon-noise model, `"starchev"` the empirical one {cite}`starchev2001`,
`"spline5"` a spline-residual estimate {cite}`mueller2014`, `"uniform"` unit
weights):

```python
from chisurf.core.fio.fluorescence.fcs import read_fcs

curves = read_fcs("scan.cor", reader_name="kristine", weight_mode="file")
```

:::{admonition} Known deviation
:class: warning
The `suren` model departs from Koppel's formula
({ref}`concept-fcs-error-bars`) in two places: the middle, shot-noise-times-signal
term is divided by $M^2$ instead of $M\langle n\rangle$, and above
`time_upper` (10 ms) the variance is additionally scaled by $10\,\text{ms}/\tau$.
Error bars from repeats (the merger's column 4) are unaffected.
:::

## Using it well

**Split, then look.** Ten chunks cost nothing and turn one curve into a mean
with an honest error bar and a list of repeats to inspect. Keep each chunk long
compared with the slowest correlation time you want to fit.

**Filter for aggregates, not for signal.** A count-rate filter that removes rare
bright spikes rescues a solution measurement; a burst filter changes what is
measured (only molecules bright enough to make a burst) and belongs to
burst-wise FCS.

**Carry the metadata.** A curve without acquisition time and count rate cannot
get model error bars later. Prefer the merger's `.cor` or `yaml` to exports that
strip them.

**Check the convention before comparing amplitudes.** $G(0)-1$ and $G(0)$
differ by one; $N = 1/(G(0)-1)$ on one and $N = 1/G(0)$ on the other.

## See also

- Concept: {ref}`concept-fcs-correlation` · error bars:
  {ref}`concept-fcs-error-bars` · filtered FCS: {ref}`concept-filtered-fcs`.
- Guides: {doc}`09_diffusion_fcs` (fitting the curve) ·
  {doc}`73_tttr_decay_and_correlation` (quick one-file correlation) · {doc}`17_filtered_fcs`
  · {doc}`06_nsfcs_second_order` · {doc}`12_handling_tttr_files` ·
  {doc}`35_combining_repeats`.
- Tools: **FCS** (`chisurf/plugins/fcs/fcs_correlator/`); channel pairs
  (`chisurf/plugins/fcs/fcs_channel_preset/`); converter
  (`chisurf/plugins/fcs/fcs_convert/`).
