---
type: Guide
title: 'Intensity traces and file tools'
description: Binning a TTTR file into per-detector intensity traces, decoding them with a hidden Markov model, and the File tools hub that splits, converts, packs, inspects and windows the same files.
tags: [guides, photons, tttr, kinetics, hmm]
---

# Intensity traces and file tools

Two tools that work on the photon stream before any model is fitted.
**Intensity trace** bins a TTTR file into counts per detector and per time
window, shows the count histogram beside each trace, and fits a hidden Markov
model (HMM) to find the levels. **File tools** is the hub for operations on the
*file*: splitting and converting it, packing it into a `.pto`, reading one back,
editing the header, and cutting it into fixed time windows.

For what a binned trace can and cannot show — Poisson counting noise, the
bin-width trade-off, blinking and bleaching steps — see
{ref}`concept-intensity-traces`. For the HMM itself, see
{ref}`concept-hidden-markov-models`.

## Intensity trace

### Open the tool

**Spectroscopy → Single-Molecule → Intensity trace**. It reads every container
tttrlib reads (PTU, HT3, SPC, Photon-HDF5, `.pto`).

```{figure} figures/intensity_trace.png
:name: fig-intensity-trace
:width: 100%

The intensity trace of an smFRET measurement on freely diffusing molecules
(`test/data/tttr/BH/132/BH_SPC132.spc`), binned at 5 ms, zoomed to 6 s. Rows,
top to bottom: red detector, green detector, their sum, each with its count
histogram on the right; the decoded two-state HMM path with its occupancy; the
per-bin fraction $n_\mathrm{red}/(n_\mathrm{red}+n_\mathrm{green})$ with its
histogram per state. The bursts are the bright state.
```

### Load and bin

1. **Setup** — define the detectors: which routing channels (and, optionally,
   which micro-time ranges, for PIE) make up each one. The tool uses the setup
   you last used in any detector wizard. Each detector becomes one trace.
2. **Load TTTR** — pick the file. It is binned at once.
3. **Time Window → ms** — the bin width $\Delta t$ (0.1–999 ms, default 10 ms).
   Changing it re-bins the file. Pick it from the dwell you want to see: about
   1 ms resolves single bursts of diffusing molecules, 10–100 ms suits
   immobilised molecules ({ref}`concept-intensity-traces`).
4. **Detector Selection** — tick the detectors to show. The order is the order
   in the setup, and it matters for the ratio row (below).
5. **Histogram Settings** — **Bins** (10–500) divides the count axis of the
   histograms; **Min Counts** / **Max Counts** restrict which bins enter them.
   Empty bins (zero counts) are always left out of the histograms. These three
   change only the histograms, never the trace.

**Save Traces** writes `time_s`, one column per detector and, once an HMM has
run, `HMM_State` to a CSV you name.

Without a detector setup the tool offers **Routing Channel 0–7** check boxes,
but it then bins **only the first ticked channel** (and shows nothing if that
channel is not in the file). Define a setup for more than one trace.

### Find the levels (HMM tab)

1. **HMM Components** — the number of states (1–15). **BIC Elbow** fits one
   to 15 states and plots the Bayesian information criterion; take the
   minimum, which is the number of states the data supports. Expect the curve
   to keep falling on a trace with bleaching or drift — that is an assumption
   failing, not more states ({ref}`concept-hidden-markov-models`).
2. **Compute HMM** — fits a Gaussian HMM with full covariances to all ticked
   detectors jointly and decodes the most probable path (Viterbi). States are
   numbered from dimmest (0) to brightest.
3. **HMM Matrix** — the transition matrix per bin, *from* state on the x axis.
   Divide an off-diagonal element by $\Delta t$ for a rate; that holds only
   while it is small ({ref}`concept-hidden-markov-models`).
4. **Dwell Times** — the dwell-time histogram of each state with a single
   exponential fitted and its $\tau$ printed. **Min Bin** / **Max Bin** set the
   range (ms), **Number of Bins** the resolution, **Normalize Histogram** scales
   each to unit sum, and **Save Histograms and Fits** writes both to CSV. A
   curved histogram on a log axis is two states drawn as one.
5. **FRET Distributions** — the histogram of the per-bin ratio (below) for
   each state.

**Compute HMM also writes files**, without asking, into a folder beside the
TTTR file named `<stem>_HMM#<n>_<w>ms/`:

| Path | Content |
| --- | --- |
| `bst/<stem>_state_<k>.bst` | one row per contiguous run of state $k$: first and end photon index |
| `traces/<stem>_traces.csv` | `time_s`, one column per detector, `HMM_State` |
| `traces/<stem>_state_traj.csv` | `time_s`, `HMM_State` |
| `traces/<stem>_fret_traj.csv` | `time_s`, `FRET_efficiency` (two or more detectors) |
| `hist/<stem>_hist_<detector>.csv`, `_hist_sum.csv` | count histograms with the current histogram settings |
| `hist/<stem>_fret_hist.csv` | ratio histogram, 50 bins on [0, 1] |

The `.bst` files are burst-ID files: **BID → Analysis** in File tools turns
them into a burst table, so the bursts of one HMM state can go on to lifetime or
FRET analysis. Their second column is the index of the first photon *after*
the run, while burst-ID readers take it as the last photon *in* it — each run
gains one photon when read back.

### Read the result

* **The trace** is counts per bin, not a rate: divide by $\Delta t$ for Hz. The
  y label says which $\Delta t$.
* **The histogram** beside each trace is the distribution of those counts. A
  steady emitter gives one Poisson peak of width $\sqrt{\langle n\rangle}$;
  a long tail to high counts is bursts or a bright state; two peaks are two
  levels that $\Delta t$ is coarse enough to separate.
* **The ratio row** is labelled *FRET efficiency* but is
  $n_0/\sum_c n_c$ for the **first** ticked detector — the proximity ratio when
  the acceptor detector comes first, its complement when the donor does. It is
  not corrected for background, crosstalk or $\gamma$, and in background bins
  it is noise. Read it only inside the bright state.
* **The state row** is the decoded path. On diffusing molecules the two states
  are simply *background* and *burst*; on an immobilised molecule they are the
  levels of blinking, binding or conformational change, and a final drop to the
  dimmest state that never returns is bleaching.

On the figure's file, the summed 5 ms counts have mean 14.7 and variance 663
(Fano factor 45), and the two-state fit puts about 5 % of bins in the bright state
with a mean dwell of 12 ms — about one transit through the focus.

## File tools

### Open the hub

**Tools → File tools**. A list on the left, one panel per tool on the right;
panels load when first selected, so a tool whose dependencies are missing shows
an error panel and the rest still work. **Guide** walks through the hub.

```{figure} figures/file_tools.png
:name: fig-file-tools
:width: 100%

File tools on **TTTR → Time Windows**, after *Process* on the same smFRET file
with 1000 ms windows: the preview shows the intensity trace with a boundary at
every window edge; each window becomes one row of the `.bst` file.
```

### The panels

**TTTR Split / Convert** — rewrite a recording in pieces or in another
container.

```{figure} figures/file_tools_split.png
:name: fig-file-tools-split
:width: 100%

TTTR Split / Convert with an SPC file loaded, to be written as PTU.
```

* *Input / Output*: **Input file**, **Output folder** (default: the input's
  folder), **Input format** (*Auto* detects it) and **Output format** — any
  container tttrlib writes; a format different from the input transcodes.
* *Split options*: **Split into files** cuts the stream into files of
  **Photons/file** × 1000 photons (off: one file, `<stem>_all.<ext>`);
  **Reset macro times** starts each output at zero; **Keep original** — off
  deletes the input after writing. The **µ-time binning** choice is currently
  not applied to the written files.
* *Batch*: drop `.ptu` files or folders (scanned recursively) and **▶ Start
  batch** with the options above; **Use file's parent as output folder** writes
  each beside its source.
* **Convert / Split** writes into `<output folder>/<stem>/`, pieces named
  `<stem>_00000.<ext>`, `<stem>_00001.<ext>`, …

**⇄ .pto** — drop a vendor file to pack it into a `.pto` beside it, or a `.pto`
to unpack the vendor files it embeds. Both directions keep what was dropped.
See {doc}`12_handling_tttr_files` and {ref}`concept-photon-container`.

**PTO Inspector** — read what a `.pto` holds. See {doc}`63_pto_inspector`.

**TTTR header** — the header tags of any file tttrlib reads, as a table (Name,
Type, Value, Idx) with a live JSON view. **Open**, **Add**, **Remove** and
**Save as PTU**. Saving always writes a new PTU with the source's photons copied
and the edited tags, because PTU is the one container that keeps arbitrary
tags; the source file is not changed.

**TTTR → Time Windows** — cut each file into consecutive windows of fixed
duration. **Time window** (ms, default 10) sets the width; **Output folder**
left empty writes to `<stem>_TW_<w>ms/` beside the first file. Add files in the
*Files* tab, press **Process**, and read counts per file in *Summary*. Each file
gives one `<stem>.bst` with one row per window: first photon index, and the
index of the first photon of the next window (the same end convention as the
HMM `.bst` files above). *Preview* shows the trace with the window edges; with
short windows on a long file that is one line per window, so preview with a
coarse window.

**BID → Analysis** — turn `.bst` / `.bid` files into a burst table. Define the
detectors and PIE windows in *Setup* (or leave the defaults: one detector per
routing channel, full micro-time range), add files in *Files* and press
**Process**. For each file the matching TTTR file is found by name — same stem,
or a stem the BID name starts with (so `<stem>_state_1.bst` finds `<stem>.spc`)
— in the file's folder or up to three folders above. The burst table and the
BID file are written into the measurement's `.pto`; an info folder
`<bid stem>/` is created beside the TTTR file.

## Headless

The intensity trace and its HMM, in tttrlib and the shared HMM core — the same
calls the tool makes:

```python
import numpy as np
import tttrlib

from chisurf.plugins.core.hmm.api import HmmSettings
from chisurf.plugins.core.hmm.core import dwell_times, fit_traces

t = tttrlib.TTTR("measurement.ptu")
route = np.asarray(t.routing_channels)
bin_s = 5e-3                                   # seconds

detectors = {"red": [1, 9], "green": [0, 8]}   # acceptor first
traces = [
    np.asarray(t[np.flatnonzero(np.isin(route, chs))].get_intensity_trace(bin_s))
    for chs in detectors.values()
]
counts = np.zeros((max(map(len, traces)), len(traces)))
for i, c in enumerate(traces):
    counts[: len(c), i] = c
time_s = np.arange(len(counts)) * bin_s

total = counts.sum(axis=1)
fano = total.var() / total.mean()              # 1 for pure shot noise

fit = fit_traces(counts, HmmSettings(n_states=2, time_step=bin_s))
states = fit.state_array                       # 0 = dimmest
ratio = counts[:, 0] / np.clip(total, 1e-12, None)
dwell = dwell_times(states, bin_s)             # state -> dwell times in s
```

`get_intensity_trace` takes the window in **seconds**. The HMM is also a
command-line tool and an RPC service in its own right: see
{doc}`54_hidden_markov_models`.

The file operations:

```python
from chisurf.plugins.core.tttr_to_pto import api as pto
from chisurf.plugins.tttr.tttr_time_windows.api.io import compute_and_save
from chisurf.plugins.burst.bid_to_analysis import convert_bid_file

container = pto.convert("measurement.ptu")                 # pack -> .pto
n, bst = compute_and_save("measurement.ptu", 1.0, "tw/")   # 1 s windows -> tw/measurement.bst
convert_bid_file("tw/measurement.bst")                     # bursts into the .pto
```

```bash
csc tttr-time-windows analyze measurement.ptu --time-window-ms 1000 --output-dir tw/
```

It prints the window count per file and a JSON summary.

## Using it well

**Choose $\Delta t$ for the question, then check it.** Re-bin at half and
double the width: a level or a dwell time that moves with $\Delta t$ is a
property of the binning, not of the molecule.

**Keep the output folders in mind.** *Compute HMM* writes a new
`<stem>_HMM#<n>_<w>ms/` folder beside the data on every run with new settings,
and overwrites the one with the same settings.

**Leave bins behind when the photons allow.** For rates faster than any
sensible bin, use the photon-by-photon HMM ({doc}`19_h2mm_hidden_markov`); for
many short traces, ebFRET ({doc}`20_ebfret_binned_hmm`).

## See also

- Theory: {ref}`concept-intensity-traces` · {ref}`concept-hidden-markov-models`
  · {ref}`concept-photon-container`.
- Binning by hand and the trace browser: {doc}`22_binned_photon_traces` · the
  data model behind `.bst` indices: {doc}`33_timestamps_and_bursts` · TTTR
  formats: {doc}`12_handling_tttr_files`.
- Tools: **Intensity trace** (`chisurf/plugins/tttr/intensity_trace/`);
  **File tools** (`chisurf/plugins/tttr/filetools/`) hosting
  `tttr_splitter`, `tttr_to_pto`, `pto_inspector`, `tttr_header_edit`,
  `tttr_time_windows` and `bid_to_analysis`.
