---
type: Guide
title: 'FCS toolbox: from photon stream to a curve worth fitting'
description: Correlating TTTR photon streams in the Spectroscopy:FCS tool — channel definitions, photon filtering, chunked multi-tau correlation, merging repeats with error bars — and converting correlation files between formats.
tags: [guides, fcs, correlation, tttr]
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

**Spectroscopy → FCS**. The window is a left rail with two groups:

* **Correlator** — the five-step workflow this guide walks through:
  *Channel Definitions → Files & Steps → Photon / Burst Filter → Correlator →
  FCS Merger*. It opens on *Files & Steps*; **Next ▶** / **◀ Back** move along
  the rail and **⏩** runs the remaining steps. **?** (top right) opens a short
  help that links back here.
* **Tools** — independent FCS tools hosted in the same window, each with its own
  **?** help: *2D-FLCS* and *Filter Calc* ({doc}`17_filtered_fcs`), *Lifetime-FCS
  Sim*, *Burst-wise FCS*, and *Diffusion Calc* (the $\tau_D \leftrightarrow D$,
  volume and concentration calculator, {ref}`concept-fcs-correlation`). A ⚠
  marks a tool flagged experimental.

The standalone correlator, channel-definition editor and merger that older
versions listed separately are the same code, now reachable only from here.

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

:::{admonition} Known issue
:class: warning
Since the channel-definition editor moved to a declarative form, the correlator
step no longer receives its selection: the **FCS Preset** list and the **A**/**B**
selectors in step 4 stay empty, and per-pair *Bins/Cascades/Fine* are not applied.
Until that is fixed, type the routing channels into **Ch A**/**Ch B** directly
(step 4).
:::

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

## 3. Photon / Burst Filter

Selects which photons reach the correlator. Every change recomputes the
selection and the "*kept / total*" line at once.

```{figure} figures/fcs_toolbox_filter.png
:name: fig-fcs-toolbox-filter
:width: 100%

A burst filter on the SPC-132 test stream: photons in stretches with at least 30
photons and inter-photon times ≤ 0.5 ms are kept (52.7 %).
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
    their parameters appear when selected. **Fill gaps** bridges short
    rejections.
* **enable** switches the burst/count-rate part off while keeping the channel,
  µt and dMT selections. **invert** keeps the rejected photons — note that it
  inverts the whole selection, channel and dMT cuts included.
* **Plot settings** — the count-rate trace bin (*MCS bin*) and the photon range
  of the inter-photon-time plot. That plot is not drawn by the default (emtk)
  plot backend yet; start ChiSurf with `CHISURF_PLOT_BACKEND=pyqtgraph` to see
  it.

With the filter on, step 4 correlates only the kept photons of every file.

## 4. Correlator

```{figure} figures/fcs_toolbox_correlator.png
:name: fig-fcs-toolbox-correlator
:width: 100%

Green (0, 8) × red (1, 9) cross-correlation of the SPC-132 stream in ten
chunks. The test stream is a dilute single-molecule sample at 3 kHz, so the
short-lag points are dominated by counting noise — exactly what the merger's
error bars will say.
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
  the species cross-correlation ({doc}`17_filtered_fcs`). *Filter Calc…* jumps
  to the calculator in the rail.

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

```{figure} figures/fcs_toolbox_merger.png
:name: fig-fcs-toolbox-merger
:width: 100%

Ten chunks with their count rates and durations; chunk 3 is unticked (its curve
is drawn dashed in *Individual*). The merged curve averages the nine that
remain. The plot docks are resizable — drag the splitter down to enlarge them.
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
* **Save Merged** writes `<folder>.cor` next to the chunk folder — for a
  correlated stream, `cr5.cor` beside the data file.
* **Add to ChiSurf** saves (if needed) and loads that file as an FCS dataset,
  ready for {doc}`09_diffusion_fcs`.

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
- Tools: **FCS** (`chisurf/plugins/fcs/fcs_toolbox/`), built on
  `chisurf/plugins/fcs/fcs_correlator/`; channel pairs
  (`chisurf/plugins/fcs/fcs_channel_preset/`); converter
  (`chisurf/plugins/fcs/fcs_convert/`).
