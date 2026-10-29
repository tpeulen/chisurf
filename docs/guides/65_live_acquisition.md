---
type: Guide
title: 'Live acquisition: watching a measurement while it happens'
description: Run a measurement from a TCSPC card or the built-in photon simulator, read the live plots, and drive the same pipeline from Python without a GUI.
tags: [guides, tcspc, photons, python, gui]
---

# Live acquisition: watching a measurement while it happens

**Tools → Views → Acquisition** opens the **Record** tool. `python -m chisurf --app acq`
starts ChiSurf in Acquisition mode: the tool is the only thing in the window, as on an
instrument PC, with ChiSurf running underneath. It streams photons
from TCSPC hardware, from the built-in photon simulator or from a replayed
photon stream, and analyses them *while they arrive*: bursts, the histograms of
the measurement type (E–S for PIE), a decay per detector, an FCS correlation,
count rates, an MCS trace and inter-photon times, all updated per chunk. Nothing
here re-reads the photons it has already seen, so the display costs the same at
minute 30 as at minute 1 (see
{doc}`Streaming analysis </concepts/live_streaming_analysis>`).

You do not need hardware to follow this guide: the **simulator** is a full
confocal photon simulator — diffusion through a focus, FRET states, anisotropy,
photophysics — and its records take the same path a device's do.

## Devices: phacq

Hardware is driven through **phacq**, a separate C++/Python acquisition library
with native drivers — no vendor libraries — for PicoQuant MultiHarp, PicoHarp
330 and HydraHarp 500, Becker & Hickl SPC cards, and the PicoQuant Sepia II
laser. The vendor-library device session of earlier versions (B&H SPCM-DLL,
PicoQuant and BrickMic wrappers with their *Device Setup* cards) has been
removed; there is one acquisition window, Record.

**On Windows**, PicoQuant's own driver holds PicoQuant units, so phacq reaches
them through PicoQuant's snAPI package (`pip install snAPI`) instead of its
native driver. The device, its settings and the recordings are the same; only
the way in differs. Linux and macOS stay native. The Sepia II needs no such
detour: on Windows phacq opens it through its own WinUSB binding.

**Every setting a device has is offered.** The driver describes its settings
itself — names, units, ranges, choices, which are per input — and Record builds
the device's panel from that description, so nothing is left out and a setting
a newer phacq adds appears without a ChiSurf change.

**Simple or Advanced — one switch for all the hardware.** **Advanced**, under the
settings choice at the top of **Acquisition**, is off by default: the simple view
shows what a measurement needs — the laser's intensity, pulsed switch and soft
lock, the shutters' checkboxes and the power-diode reading, the run. Ticking it
adds, everywhere at once, the settings each phacq driver marks as expert
(``"advanced": true`` in its schema): the TCSPC unit's thresholds, shifts, timing
and markers; the laser's repetition rate, head type and slot; the shutters'
reported state and the diode averaging; the simulator's sample and instrument
realism. A loaded settings file or profile sets them either way, and they stay as
calibrated. With **Advanced** on, the TCSPC device's settings start folded by group — the sync,
each input on its own fold, timing, markers and outputs (for a B&H card its CFD, sync, TAC, timers and FIFO mode).
An edit is sent at once, between runs; a value the device refuses is named in
the status line and nothing of that edit is applied. The values are saved in
the acquisition settings file (``device.settings``, phacq's names).

```{figure} figures/65_record_device.png
:name: fig-65-record-device
:width: 60%

A MultiHarp 150 8N in Record's TCSPC device panel: its settings start folded
by group — sync, timing, markers, outputs, then one fold per input.
```

**The laser.** Under **Laser**, a Sepia II shows its own switches, which act at
once: the **Soft lock** (on: every output off) and, per laser head, **Pulsed**
(off: continuous wave), the **Repetition rate** (the head's own oscillator, 80
MHz / 2ⁿ, or an external trigger edge) and the **Intensity**. Connecting locks
the outputs; **Laser off** always works. An oscillator module (SOM 828
sequencer) is not driven by phacq yet.

```{figure} figures/65_record_laser.png
:name: fig-65-record-laser
:width: 60%

A Sepia II in Record's Laser panel (phacq's simulated unit): soft lock, and the
first laser head's pulsed switch, repetition rate and intensity.
```

## Profiles

The **Settings** list starts with ready-made profiles, marked ★, before the
workspace's own settings files. Each is an ordinary acquisition settings file in
`chisurf/plugins/core/acq/profiles/`.

The MT200 profiles were made from SymPhoTime's own profiles on that microscope
(`Standard.pus`, `PIE.pus`, `CY_PIE.pus`):
* **Standard:** red laser, 40 MHz.
* **PIE:** blue and red laser.
* **CY PIE:** PIE with the red laser delayed 4 ns.

They share one TCSPC setting:
* 32 ps bins;
* sync CFD 350 mV, sync offset 5000 ps;
* detectors on HydraHarp inputs 1 and 3, 250 mV, with their offsets (+130 ps and −40 ps).

They differ only in the lasers. None sets a run length: runs are open-ended until
you press **Stop**. They don't set the Sepia's oscillator
programme yet, because phacq does not drive the SOM 828-D yet. Choose one and press
**Load**.

**Loading connects the hardware.** A settings file says which unit it is for
(`device.driver`, `device.model`, `device.serial` — the MT200 profiles name
HydraHarp 400 1032692). Choosing a file or profile in the list loads it at
once — **Load** does it again — and a progress bar says what is under way
(finding and connecting the unit, the laser, applying the settings): it connects
that unit if it is attached, and the laser the file names, then applies
everything. The settings last loaded are loaded again when Record opens with a
TCSPC device as its source. A unit that is not attached is
named in the notes and nothing else is connected in its place; a file for the
Sepia II never connects the simulated laser instead.

**Shutters and power diode.** A settings file's `shutters` section defines them:
named `buses` (`type` `can` — PEAK PCAN — or `i2c` — Linux `/dev/i2c-N`), and
for every shutter and the power diode its own `endpoint` (`can_bit`: a bit of a
CAN command frame with its state frame; `i2c_bit`: a bit of an I2C device's
register, its state from another; `can_word` / `i2c_word`: a reading). Other
hardware is other endpoints in the file. The MT200 profiles link Excitation,
Detector 1 and 2 to bits 0–2 of the shutter box on the CAN card. Loading the file
connects them. The **Shutters** tab is generated from that section:
a checkbox per shutter, what the hardware reports (it differs while a box's own
buttons have taken over), and the diode. **Start** opens the shutters the file
names; the end of a run closes the excitation shutter. The laser is not touched.

**What a recording's header holds.** Besides the device's settings and the
whole settings file, a recording carries the laser and the diode under the names
SymPhoTime writes: `Sep2_SerialNo`, per laser driver `Sep2_SLM_<slot>_FineIntensity`
(%), `_TriggerIndex`, `_CW_PulseDisable`, `_HeadType`, the heads' names
`UsrHeadName(i)`, and `UsrPowerDiode` (a.u., once the file calibrates the
diode; `ChiSurf_PowerDiodeRaw` always) and the shutters' states. A HydraHarp
400's discriminators are written as CFD levels (`HWSync_CFDLevel`, …) with
`MeasDesc_BinningFactor`; a point measurement carries SymPhoTime's
`ImgHdr_Dimensions` 1, `ImgHdr_Ident` 6 and the point as `ImgHdr_X0/Y0`.

**The scanner.** A settings file's `scanner` section names the sample scanner
(`{"driver": "pi", "address": "", "settings": {"learn_s": 5, "turn_ms": 20}}`):
the MT200 profiles name the PI E-725 piezo stage, the first one on USB (on the
MT200 PC it is bound to PI's own USB driver: write `"tcp:<host>"` there), with
SymPhoTime's "fast" timing; `"sim:"` is libphacq's simulator. Loading the file
connects it like the device, the laser and the shutters; opening it moves
nothing.

**No sync, still recorded.** A T3 run without a sync signal (laser off, cable
out) is recorded anyway and the device is shown as *(no sync)*: the unit still
time-tags its inputs, the macro step is provisionally the unit's start-stop
range, and the file's header takes the sync rate measured when it closes.

## Imaging, picking molecules, measuring them point by point

In **Image** mode Record scans like SymPhoTime does. With the source **TCSPC
device and scanner** the device records while the scanner rasters: the E-725's
line triggers mark each line's start and stop on HydraHarp marker inputs, which
Start switches on, so the image is built from the photon stream alone and the
recording carries SymPhoTime's `ImgHdr_*` tags (no `ImgHdr_Frame`: the E-725
sends no frame marker, a frame is its lines). Which marker inputs and which edge
is the instrument's cabling, declared in the settings file, never assumed:

```json
"scanner": {"driver": "pi", "address": "",
            "line_markers": {"start": 3, "stop": 4, "edge": "falling"},
            "settings": {"learn_s": 5, "turn_ms": 20}}
```

The MT200 profiles carry these values -- what SymPhoTime's image files record
(`ImgHdr_LineStart` 3, `ImgHdr_LineStop` 4, falling edge) and what a phacq
recording on the instrument showed (one marker 3 and one marker 4 per line). A
scanner section without `line_markers` is refused. The raster -- pixels, area, the
corner on the stage, dwell time, frames, bidirectional -- is the **Scan** panel's;
the scanner's own learning time and line turnaround are in **Scan › Scanner**
(Advanced). Without hardware the **Simulator (scan)** scans a simulated sample:
beads on a cell, or single molecules of which a few spots hold two.

On the image, **click** to add a point, or press **Auto-pick**: the spot finder's
single-molecule workflow ({doc}`guide 84 </guides/84_spot_finder>`) finds the
molecules in the intensity image and adds them, brightest first, within
*Max molecules* and *Min/Max photons*. **Measure points** parks the focus on each
point in turn (a settled move) and records it -- for *Time per point*, or until the
molecule has bleached (*Until bleached*: the count rate stays near the background).

```{figure} figures/65_points_picked.png
:name: fig-65-points-picked
:width: 100%

A simulated scan of single molecules: Auto-pick has added the molecules (numbered
rings) and one point was clicked by hand; the Points table lists them.
```

While a point records, **Trace** shows its count rate per detector, the bleach
threshold and the moment the rule called the molecule bleached, and under it the
FRET efficiency and the mean arrival time per bin.

```{figure} figures/65_points_running.png
:name: fig-65-points-running
:width: 100%

Point 3 of 3 recording: its live trace with the bleach threshold; the points done
already carry their results.
```

Each point is a recording of its own in Datasets (SymPhoTime's point header:
`ImgHdr_Dimensions` 1, `ImgHdr_Ident` 6, the stage position) and is analysed when
it ends with ChiSurf's shared tools -- the intensity-trace tool's binning
({doc}`guide 74 </guides/74_intensity_traces_and_file_tools>`) and the shared
Gaussian HMM ({doc}`guide 92 </guides/92_hmm_binned_traces>`) with the state
count the BIC prefers. Its row then holds the photons, the bleach time, the
number of bleaching steps (each drop to a level dimmer than all before), the FRET
efficiency of the first level (background-corrected proximity ratio), S (only with
alternating excitation) and a fast lifetime. Selecting a row shows that molecule's
trace and HMM path. When the sequence ends the table of all molecules is written
into the image dataset's container (`molecules.table`, one row per molecule).

```{figure} figures/65_points_done.png
:name: fig-65-points-done
:width: 100%

The sequence done: one row per molecule; the selected molecule's trace per
detector with its HMM path (yellow) and the bleach time (red), two steps down.
```

The same from Python, without a window:

```python
from chisurf.plugins.core.acq.gui.record_app import RecordModel

m = RecordModel(realtime=False)
m.mode = "image"; m.load_example()
m.start()
while m.running:
    m.poll()
m.poll(force=True)
m.autopick()            # the spot finder's single_molecule workflow
m.measure_points()
m.wait_points()
for row in m.point_rows():
    print(row["index"], row["steps"], row["bleach_s"], row["efficiency"])
```

### Survey: a larger area, automatically

**Points › Survey** repeats image → Auto-pick → Measure points tile after tile
until **Stop**, a stop condition (tiles, molecules, minutes; in Advanced also a
number of empty tiles in a row) or the whole area is done -- by default the
scanner's whole range (0–100 µm on the E-725, from its driver). Tiles are the
Scan panel's Width × Height, visited in an **outward spiral** from the centre of
the last image, where you focused (a coverslip is rarely flat; the nearest tiles are
the best focused), or in serpentine rows. Tiles with fewer than *Min molecules*
are logged and passed, failed tiles too. An *Edge guard* leaves spots near a
tile's edge to the neighbour that sees them whole and a molecule measured once is
never measured again, so overlapping tiles give no doubles. The shutters open
once at the start and close once at the end or Stop; the laser is not switched.
One table of all molecules (`survey_molecules.table`: tile, stage position, the
per-molecule results) is stored with the first tile's image after every tile, so
a stopped survey keeps what it measured. From Python: `m.survey_start()`, then
`m.wait_survey()`; `m.survey_table()` is the table.

**Scanner learning.** The scanner learns its pattern (linearization, line triggers) before an
image -- 5 s on the MT200 -- and all tiles share one raster. *First tile, re-check line triggers*
(the default) learns once and re-measures only the line triggers per tile; *First tile only* reuses
everything; *Every tile* learns each time, as a single image does (phacq's pi driver setting
`learning` 0/1/2).

```{figure} figures/65_survey_running.png
:name: fig-65-survey-running
:width: 100%

A survey of 4 × 4 tiles running: the map shows the spiral (numbers and path),
tile 5 being measured (orange), measured tiles green with their molecules, an
empty tile dark; the line above it says tile, molecules, elapsed and remaining
time.
```

```{figure} figures/65_survey_done.png
:name: fig-65-survey-done
:width: 100%

The survey done: every tile visited, 26 molecules measured.
```

### Provenance: from a point back to its image and survey, and forward

Every image, tile image and point recording is a dataset of the project, and
each traces both ways, in its file and in the project's provenance:

| Where | What it records |
|---|---|
| point PTU header | `ChiSurf_Point_SourceImage` / `…SourceImageUID` (the image), `…PixelX/Y` and `…ImageX0_um/Y0_um/Pixel_um` (pixel and raster: pixel ↔ stage), `…Origin` (`auto` / `click`), `…PickWorkflow` + `…PickSettingsHash`, `…Brightness`, `ChiSurf_Point_X/Y_um` (aimed at) and `…Reached_X/Y_um` (the stage's answer), `ChiSurf_Survey_ID` / `…Tile` / `…TileX0/Y0_um`; SymPhoTime's `ImgHdr_*` point tags as before |
| tile image PTU header | `ChiSurf_Survey_ID`, `…Tile`, `…Tiles`, `…TileX0/Y0_um`, `ChiSurf_Scanner_LearningMode`, `ChiSurf_Scanner_LearnedBefore` |
| point's container | `point` (`point_measurement`, the image as an external reference), `molecule` (`trace_segmentation`) |
| image's container | `points` (`point_selection`: every point picked on it, each row naming its recording), `molecules.table` |
| tile image's container | `survey_tile` (`survey`, grouped in the survey; the learning count after the tile) |
| first tile's container | `survey_tiles` (every tile, its state and its image), `survey_molecules.table` |

The containers are embedded in the `.cs.pto`, so the record travels with the
project. Strings a numeric table cannot hold (dataset uids, file names) are lookup
lists in a record's settings, indexed by its `point_dataset` / `image_dataset`
column.

```python
from chisurf.plugins.core.acq.live import provenance

back = provenance.backtrace("rec/points_20261029_101500_p003.ptu")
back["image"], back["pixel"], back["survey_id"], back["tile"]
provenance.points_of(back["image_uid"])      # the image's points, each with its dataset
provenance.survey_of(back["image_uid"])      # the survey the tile image belongs to
```

To run the scan on the real instrument, load an MT200 profile (it connects the
HydraHarp, the Sepia II, the shutters and the E-725), set **Source** to *TCSPC
device and scanner* and press **Start**.

## Running one

Its windows (Acquisition, Laser, Analysis, Quality, the plots), sources, laser
program, settings files and measurement types are described in the tool's own
**Help** and walked through by its **Guide**. In short:

1. Open **Setup → Settings → Acquisition** to set the defaults the tool starts
   from: the simulator's scalar parameters (excitation mode, photon counts,
   seeds, geometry, micro time, performance) and the standard **output folder**.
   Set **Acquisition → Mode** to *Pulsed* if you want to see a decay: with CW
   excitation every micro time is zero, so the decay is a single spike at 0 ns
   and the phasor reads (1, 0). Every change is stored at once.

   ```{figure} figures/65_acquisition_settings.png
   :name: fig-65-acquisition-settings
   :width: 70%

   Setup → Settings → Acquisition with the simulator selected and switched to
   pulsed excitation. The per-species table (molecules in the box M, diffusion
   coefficient D, brightness per detector), the kinetics and the decay
   lifetimes are edited in the simulation setup dialog
   ({doc}`guide 18 </guides/18_tttr_simulation>`).
   ```
2. In Record, choose the **source** (simulator, replay, or a phacq device) and,
   for a device, connect it first — nothing touches the hardware before that.
3. Bound the run with a time and/or photon limit. The photon condition is
   checked per chunk, so a run overshoots it by up to one chunk.
4. Press **Start**; **Stop** ends the run early. The run lands in the project as
   a photons dataset with its burst run.

## The Acquisition fit window

The acquisition demo (`open_demo()`, below) simulates a 20 s two-species stream (a donor-dominated species
with a 3.4 ns donor lifetime and a high-FRET species with 1.1 ns, two detection
channels; `chisurf/plugins/core/acq/demo.py`, cached under `<settings>/demos/acq`),
registers it as a dataset and opens a fit window named **Acquisition**. Its model
has no parameters. Its pages are the live plots: **Decay**, **Correlation**,
**Count rate** (with its mean lines), **MCS** and **Macro time**;
they fill while the stream runs.

```{figure} figures/65_acquisition_fit_window.png
:name: fig-65-acquisition-fit-window
:width: 100%

The Acquisition fit window with the demo stream: decay of both detection
channels on a log axis. Each page's controls (decay curves, correlation channel
pairs, MCS bin width and range, macro-time plot type, update rate) are in the
main window's *Plot settings* dock while the page is current.
```

From Python, headless:

```python
from chisurf.plugins.core.acq.dataset import open_demo

dataset = open_demo()            # dataset + "Acquisition" fit, stream running
dataset.refresh()                # newest pipeline snapshot -> dataset.y, dataset.live.series
```

## What the plots show

The live plots (`chisurf/plugins/core/acq/gui/live_plots.py`) are one tab each:
Decay, Correlation, Count rate, MCS and Macrotime. They are the pages of the
Acquisition fit window.

**Fluorescence decays** — one micro-time histogram per routing channel,
identical to a `bincount` of the saved micro times. The x axis is nanoseconds
when the device states its TAC resolution, and TAC channels when it does not; it
is never a guess.

![The Decay tab after a pulsed simulator run of 300 000 photons, with the burst and phasor line under the plot](../images/acq_live_decay.png)

The line under the plot is two quality numbers that come free with the same
photon pass: the **burst count and rate** from a sliding-window burst search, and
the **phasor** (g, s) of all micro times. Both are diagnostics for alignment and
sample quality, not analyses — a phasor that drifts during a measurement is worth
knowing about before the measurement ends.

**Correlation curve** — up to four live FCS curves. Each is a channel pair
(*channel A*, *channel B* on the Correlation tab): the same channel twice is an autocorrelation, two
different channels a cross-correlation with the lag running from the first to the
second, and `-1` means *every* photon. The curve is the multi-tau correlator's,
computed incrementally and agreeing with the offline correlator on the same
photons.

![The Correlation tab: the autocorrelation of every photon (-1 × -1) of the same simulated diffusing species](../images/acq_live_correlation.png)

**MCS trace** — the intensity trace at the configured bin width, showing the last
*Rollaround (s)* seconds. Only that window is kept, and it keeps its absolute
position on the time axis, so the trace scrolls rather than restarting.

![The MCS tab showing the last second of the simulated measurement at 1 ms resolution](../images/acq_live_mcs.png)

**Count rate** — one point per chunk per channel plus their sum, in counts per
second, against macro time.

**Macrotime plot** — inter-photon times; a quick look at whether the stream is
Poissonian or structured.

## Saving

Record writes the measurement while it runs and adds it to the project as a
photons dataset; every recording carries its acquisition settings in its header,
so a measurement can be repeated from the file. The simulator, run on its own
(CLI below or `acq.simulation.run`), writes `mNNN.spc` files plus
`simulation_config.json` and `simulation_info.txt` into its output folder.

## Without a GUI

The pipeline is Qt-free and is the same object the GUI feeds. Push raw device
words at it and read display state back:

```python
import numpy as np
import tttrlib
from chisurf.plugins.core.acq.pipeline import AcquisitionPipeline, PipelineConfig

pipeline = AcquisitionPipeline(PipelineConfig(
    record_type=tttrlib.RECORD_SPC130,   # the device's record format
    macrotime_clock=50e-9,               # seconds per macro-time tick
    channels=(8, 0, 9, 1),               # routing channels, in window order
    correlation_pairs=((0, 8, 8), (1, 8, 0)),   # (curve, channel a, channel b)
    mcs_bin_width_ms=1.0,
    mcs_rollaround_ms=1000.0,
    photon_limit=1_000_000,
))

# uint32 records, as read from the FIFO; with no card, split the simulator's
# words (next block) into chunks: device_chunks = np.array_split(words, 10)
for chunk in device_chunks:
    pipeline.push(chunk)
    if pipeline.stop_reason:
        break

pipeline.flush()                         # the correlators emit their last bin
state = pipeline.snapshot()
tau_ms, g = pipeline.correlation(0)
decay = pipeline.decay(0)
```

`snapshot()` is plain data — histograms, curves, count rates, the burst count and
the phasor — and contains no photon arrays: everything in it is sized by the
configuration rather than by how long the acquisition ran.

To generate a stream to push, the simulator is one call:

```python
from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
    generate_spc132_uint32,
)

words = generate_spc132_uint32({
    "N_ph_max": 50_000,
    "pulsed_exc": 1,
    "decay_lifetimes": [[1.0, 3.5]],     # amplitude, lifetime in ns
    "psf_type": "analytic_gaussian3d",
})
```

`psf_type` is one of `gaussian3d` (default), `analytic_gaussian3d` (the same
Gaussian evaluated on the fly, no voxel grid), `gaussian_lorentzian` (a confocal
detection volume whose waist expands with `psf_zR`) or `radial` (a measured
radially-symmetric focus, read from `psf_file`). The name selects the
constructor and nothing catches it: an unknown name, a `radial` without a
`psf_file`, or a photon library built without that grid all fail the call. None
of them falls back to the plain Gaussian, because a substituted focus changes
the answer without changing anything you can see.

## Using it well

- Check the phasor line before trusting the decay: (1, 0) means every micro
  time is zero — CW excitation, or a card whose TAC is not running.
- A photon stop condition overshoots by up to one chunk; for an exact count,
  cut the saved raw words afterwards.
- Set the output folder deliberately: the standard folder of Setup → Settings →
  Acquisition is where runs are written.

## Known behaviour

- The simulator's **background photons** (`q_bg`) carry micro-time 0, so a decay
  with background shows a spike in its first bin. The demo therefore has no
  background.

## The controls of each tab

The live plots are drawn from `AcquisitionPipeline.snapshot()`
(`chisurf/plugins/core/acq/gui/live_plots.py`, controls in `live_plots.view.json`):

- **Decay**: Curve 0–3 shown or hidden, Log Y scale, Update every (snapshots).
- **Correlation**: channel A / channel B per curve (`-1` = every photon), Log lag axis.
- **Count rate**: channel per curve, **Set to mean** (draws a line at the displayed
  mean), rolling window size, binning (points per bin), Log Y.
- **MCS**: Bin width (ms), Rollaround (s), Manual Y range.
- **Macrotime**: dt or absolute times.

Correlation pairs, MCS bin width and rollaround are fixed when the pipeline is
built, so they apply from the next run; everything else acts on the running plot.

## Related

- {doc}`Streaming analysis </concepts/live_streaming_analysis>` — why the live
  path is incremental, and where it is exactly the batch answer
- {doc}`Simulating photon streams </guides/18_tttr_simulation>` — the simulator
  on its own, for generating test data
- {doc}`Handling TTTR files </guides/12_handling_tttr_files>` — reading what was
  saved
